"""
Evidence Retriever for Clinical Co-Pilot (Week 2).
Indexes clinical guidelines with hybrid keyword + dense retrieval.
Reranks results using combined scoring.

Corpus: agent/external_corpus/*.md  (FDA drug labels + PubMed abstracts,
fetched from the OpenFDA and NCBI E-utilities APIs by
fetch_external_guidelines.py — no hand-written internal docs).
"""

import os
import re
import math
import hashlib
from collections import Counter
from pathlib import Path
import chromadb

GUIDELINES_DIR = os.path.join(os.path.dirname(__file__), "external_corpus")
COLLECTION_NAME = "clinical_guidelines"

# Module-level ChromaDB client
_client = chromadb.Client()
_collection = None
_chunks = []  # In-memory store for keyword search


class GuidelineChunk:
    """A chunk of a clinical guideline with metadata."""
    def __init__(self, text, source_file, section, guideline_title, chunk_id):
        self.text = text
        self.source_file = source_file
        self.section = section
        self.guideline_title = guideline_title
        self.chunk_id = chunk_id

    def to_citation(self):
        return {
            "source_type": "clinical_guideline",
            "source_id": self.source_file,
            "page_or_section": self.section,
            "field_or_chunk_id": self.chunk_id,
            "quote_or_value": self.text[:200],
        }


# Minimum useful content for a search chunk. The corpus has a lot of
# `## Source` sections containing only a "FDA / OpenFDA API. Public domain."
# citation line and `Introduction` chunks containing only the file's `#`
# title. These outrank substantive chunks under BM25's length normalization
# (a 6-word chunk hitting two query terms scores ~1.0) so they crowd out
# the actual content. 20 words is enough to keep all real section bodies
# while dropping the metadata stubs.
_MIN_CHUNK_WORDS = 20


def _is_substantive(text: str) -> bool:
    """True when a chunk's body has enough non-heading content to be worth
    indexing. Drops markdown-only chunks (just `# Title`) and bibliographic
    stubs (`Source: URL. Public domain.`)."""
    if not text or not text.strip():
        return False
    # Strip leading markdown headings before counting words so a chunk
    # that's just `# FDA Drug Label: Foo` doesn't sneak past on its title.
    stripped = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    ).strip()
    return len(stripped.split()) >= _MIN_CHUNK_WORDS


def _chunk_markdown(filepath: str) -> list[GuidelineChunk]:
    """Split a markdown guideline into section-level chunks.

    Filters out chunks whose body is only a title line or a citation URL
    (see _is_substantive) so they don't pollute the BM25 / dense candidate
    pool with high-scoring but content-free results.
    """
    filename = Path(filepath).name
    with open(filepath, "r") as f:
        content = f.read()

    # Extract title from first heading
    title_match = re.match(r"^#\s+(.*)", content)
    title = title_match.group(1) if title_match else filename

    chunks = []
    current_section = "Introduction"
    current_text = ""

    def _flush():
        if not _is_substantive(current_text):
            return
        chunk_id = hashlib.md5(f"{filename}:{current_section}".encode()).hexdigest()[:8]
        chunks.append(GuidelineChunk(
            text=current_text.strip(),
            source_file=filename,
            section=current_section,
            guideline_title=title,
            chunk_id=chunk_id,
        ))

    for line in content.split("\n"):
        if line.startswith("## "):
            _flush()
            current_section = line.lstrip("# ").strip()
            current_text = ""
        else:
            current_text += line + "\n"

    _flush()
    return chunks


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer for BM25 scoring."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return [w for w in text.split() if len(w) > 2]


def _compute_idf(corpus_tokens: list[list[str]]) -> dict:
    """Compute IDF scores for BM25."""
    N = len(corpus_tokens)
    df = Counter()
    for doc_tokens in corpus_tokens:
        unique = set(doc_tokens)
        for token in unique:
            df[token] += 1
    return {token: math.log((N - freq + 0.5) / (freq + 0.5) + 1) for token, freq in df.items()}


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], idf: dict, avg_dl: float, k1=1.5, b=0.75) -> float:
    """BM25 score for a single document."""
    dl = len(doc_tokens)
    tf = Counter(doc_tokens)
    score = 0.0
    for qt in query_tokens:
        if qt in tf:
            f = tf[qt]
            numerator = f * (k1 + 1)
            denominator = f + k1 * (1 - b + b * dl / avg_dl)
            score += idf.get(qt, 0) * numerator / denominator
    return score


def index_guidelines():
    """Index all clinical guidelines into ChromaDB and in-memory keyword index."""
    global _collection, _chunks

    if not os.path.isdir(GUIDELINES_DIR):
        print(f"  ⚠ Guidelines directory not found: {GUIDELINES_DIR}")
        return

    # Chunk all guidelines
    _chunks = []
    for filename in sorted(os.listdir(GUIDELINES_DIR)):
        if filename.endswith(".md"):
            filepath = os.path.join(GUIDELINES_DIR, filename)
            file_chunks = _chunk_markdown(filepath)
            _chunks.extend(file_chunks)

    if not _chunks:
        print("  ⚠ No guideline chunks found")
        return

    # Index in ChromaDB for dense retrieval
    try:
        _client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    _collection = _client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    _collection.add(
        ids=[c.chunk_id for c in _chunks],
        documents=[c.text for c in _chunks],
        metadatas=[{
            "source_file": c.source_file,
            "section": c.section,
            "guideline_title": c.guideline_title,
        } for c in _chunks],
    )

    print(f"  ✅ Indexed {len(_chunks)} chunks from {len(set(c.source_file for c in _chunks))} guidelines")
    return _collection


def _keyword_search(query: str, top_k: int = 10) -> list[tuple[GuidelineChunk, float]]:
    """BM25 keyword search over guideline chunks."""
    if not _chunks:
        return []

    query_tokens = _tokenize(query)
    corpus_tokens = [_tokenize(c.text) for c in _chunks]
    idf = _compute_idf(corpus_tokens)
    avg_dl = sum(len(t) for t in corpus_tokens) / len(corpus_tokens) if corpus_tokens else 1

    scored = []
    for i, chunk in enumerate(_chunks):
        score = _bm25_score(query_tokens, corpus_tokens[i], idf, avg_dl)
        if score > 0:
            scored.append((chunk, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _dense_search(query: str, top_k: int = 10) -> list[tuple[GuidelineChunk, float]]:
    """ChromaDB dense vector search."""
    if _collection is None:
        return []

    results = _collection.query(
        query_texts=[query],
        n_results=min(top_k, len(_chunks)),
    )

    scored = []
    chunk_map = {c.chunk_id: c for c in _chunks}
    for i, chunk_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i] if results.get("distances") else 0
        similarity = 1 - distance  # cosine distance → similarity
        if chunk_id in chunk_map:
            scored.append((chunk_map[chunk_id], similarity))

    return scored


def _rerank_candidates(query: str, candidates: list, top_k: int) -> list[tuple]:
    """Re-score (query, chunk) pairs with a cross-encoder reranker.

    Tries Cohere Rerank first (if COHERE_API_KEY is set); falls back to a
    local sentence-transformers cross-encoder; falls back to the input
    order (already sorted by hybrid score) if neither is available.

    `candidates` is a list of (chunk, hybrid_score, kw_score, dense_score)
    tuples. Returns the same shape with an additional `rerank_score` field
    spliced in, sorted by rerank_score desc, truncated to top_k.
    """
    # Try Cohere first.
    cohere_key = os.getenv("COHERE_API_KEY", "").strip()
    if cohere_key:
        try:
            import cohere
            co = cohere.Client(api_key=cohere_key)
            docs = [c[0].text for c in candidates]
            resp = co.rerank(
                query=query,
                documents=docs,
                top_n=min(top_k, len(docs)),
                model="rerank-english-v3.0",
            )
            out = []
            for r in resp.results:
                ch, hybrid, kw, dense = candidates[r.index]
                out.append((ch, hybrid, kw, dense, float(r.relevance_score), "cohere"))
            return out
        except Exception:
            pass  # fall through to next backend

    # Fall back to a local cross-encoder via sentence-transformers — UNLESS
    # the deployment opts out via DISABLE_CROSS_ENCODER=1. The local model
    # (`cross-encoder/ms-marco-MiniLM-L-6-v2`) takes 15-20s on a CPU droplet
    # AND, being trained on generic MS MARCO passages, often promotes FDA
    # drug labels above domain guidelines (e.g. ranks atorvastatin labels
    # above ADA glycemic targets for an HbA1c question). Hybrid fusion is
    # both faster and better-aligned for this corpus when no domain-aware
    # cloud reranker (Cohere) is available.
    disable_local = os.getenv("DISABLE_CROSS_ENCODER", "").strip().lower() in ("1", "true", "yes", "on")
    if not disable_local:
        try:
            from sentence_transformers import CrossEncoder
            model = _local_reranker()
            if model is not None:
                pairs = [(query, c[0].text) for c in candidates]
                scores = model.predict(pairs)
                ranked = sorted(
                    zip(candidates, scores),
                    key=lambda x: float(x[1]),
                    reverse=True,
                )[:top_k]
                return [
                    (ch, h, k, d, float(s), "cross-encoder")
                    for (ch, h, k, d), s in ranked
                ]
        except Exception:
            pass

    # Final fallback: keep the existing hybrid-fusion order. This is what
    # the eval suite exercises in CI (no Cohere key, no transformers).
    return [
        (ch, h, k, d, float(h), "hybrid-fusion")
        for ch, h, k, d in candidates[:top_k]
    ]


_LOCAL_RERANKER_CACHE: list = []


def _local_reranker():
    """Lazy-load a local cross-encoder, cache, return None on failure."""
    if _LOCAL_RERANKER_CACHE:
        return _LOCAL_RERANKER_CACHE[0]
    try:
        from sentence_transformers import CrossEncoder
        m = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        _LOCAL_RERANKER_CACHE.append(m)
        return m
    except Exception:
        _LOCAL_RERANKER_CACHE.append(None)
        return None


# Lightweight synonym groups — when the user's query mentions any term in
# a group, an additional pseudo-query containing the rest of the group is
# issued and unioned into the candidate pool. Helps the BM25 side find
# relevant chunks that don't lexically overlap with the question (e.g. a
# question about "statins" matches an FDA label that only ever says
# "atorvastatin"). Cheap and deterministic — no extra LLM call.
_SYNONYM_GROUPS: list[set[str]] = [
    # Lipid-lowering
    {"statin", "statins", "atorvastatin", "rosuvastatin", "pravastatin",
     "simvastatin", "hmg-coa", "ldl", "hyperlipidemia", "dyslipidemia"},
    # Anticoagulation / AFib
    {"doac", "anticoagulant", "anticoagulation", "blood thinner",
     "apixaban", "rivaroxaban", "dabigatran", "warfarin", "afib",
     "atrial fibrillation", "stroke prevention", "chads", "cha2ds2"},
    # Diabetes
    {"diabetes", "diabetic", "t2dm", "hba1c", "a1c", "glycemic",
     "metformin", "ozempic", "semaglutide", "empagliflozin", "sglt2",
     "glp-1", "insulin"},
    # Hypertension
    {"hypertension", "high blood pressure", "bp", "ace inhibitor",
     "lisinopril", "losartan", "amlodipine", "carvedilol", "arb",
     "thiazide", "beta-blocker", "beta blocker"},
    # Heart failure
    {"heart failure", "hfref", "hfpef", "ejection fraction", "bnp",
     "nt-probnp", "furosemide", "diuretic", "carvedilol"},
    # CKD / labs
    {"ckd", "chronic kidney disease", "egfr", "creatinine", "proteinuria",
     "albuminuria", "renal"},
    # Anemia
    {"anemia", "hemoglobin", "hematocrit", "iron deficiency", "ferritin",
     "mcv"},
    # Liver
    {"alt", "ast", "transaminitis", "hepatic", "liver function",
     "lft", "bilirubin"},
    # Depression / mental health
    {"depression", "ssri", "sertraline", "duloxetine", "phq", "anxiety"},
    # Migraine
    {"migraine", "headache", "sumatriptan", "topiramate", "triptan"},
    # Lupus / autoimmune
    {"lupus", "sle", "hydroxychloroquine", "ana", "autoimmune"},
    # Thyroid
    {"thyroid", "hypothyroid", "levothyroxine", "tsh"},
]


def _expand_query(query: str) -> list[str]:
    """Return the original query plus up to 2 expansion strings derived
    from synonym groups whose terms appear in the query. Short circuits
    on the empty string and dedupes — never returns more than 3 queries
    so the candidate pool doesn't explode.
    """
    q = query or ""
    if not q.strip():
        return []
    qlower = q.lower()
    expansions: list[str] = [q]
    seen_groups: set[int] = set()
    for i, group in enumerate(_SYNONYM_GROUPS):
        if i in seen_groups:
            continue
        if any(term in qlower for term in group):
            seen_groups.add(i)
            # Build a synonym blob excluding terms already in the query
            extras = [t for t in group if t not in qlower]
            if extras:
                expansions.append(q + " " + " ".join(sorted(extras)))
        if len(expansions) >= 3:
            break
    return expansions


def _diversify(
    reranked: list[tuple],
    top_k: int,
    max_per_source: int = 2,
) -> list[tuple]:
    """Greedy pick of top_k items with a hard cap of `max_per_source`
    chunks from any one source_file, so the answer never quotes three
    chunks from a single FDA label when the corpus has 30 docs.

    The reranker's score scale varies dramatically between weak and
    strong matches (positive for clean topical hits, deeply negative
    when no chunk is a great match), so a soft penalty was unreliable.
    A hard cap is predictable and easy to reason about; once the cap
    is reached, the source is removed from the pool. If we run out of
    diverse sources before reaching top_k, we fall back to filling from
    the remaining (capped) pool.
    """
    if not reranked:
        return []
    chosen: list[tuple] = []
    chosen_files: Counter = Counter()
    leftovers: list[tuple] = []
    for item in reranked:
        if len(chosen) >= top_k:
            break
        src = item[0].source_file
        if chosen_files[src] >= max_per_source:
            leftovers.append(item)
            continue
        chosen.append(item)
        chosen_files[src] += 1
    # If we couldn't fill top_k with diverse sources, top up from the
    # leftovers (which preserve rerank order).
    if len(chosen) < top_k:
        for item in leftovers:
            if len(chosen) >= top_k:
                break
            chosen.append(item)
    return chosen


def search_evidence(query: str, top_k: int = 5, candidate_pool: int = 20) -> list[dict]:
    """
    Hybrid search + reranker: BM25 keyword + dense vector candidates,
    then a cross-encoder reranker scores each (query, chunk) pair and
    only the top-k grounded snippets are returned.

    Now also runs synonym-expanded pseudo-queries to find chunks that
    don't lexically match the original question, and applies a same-source
    diversity penalty after reranking so the LLM sees evidence from
    multiple guidelines rather than three chunks from one FDA label.

    Returns list of evidence snippets with source metadata and scores
    (kw, dense, hybrid, rerank, backend).
    """
    # Ensure index exists
    if _collection is None or len(_chunks) == 0:
        index_guidelines()

    if not _chunks:
        return []

    chunk_map = {c.chunk_id: c for c in _chunks}

    # ── Stage 1: candidate generation (sparse + dense), unioned across
    # synonym-expanded pseudo-queries. We keep the BEST score per chunk
    # across the expansions to avoid biasing the candidate pool toward
    # chunks that happened to match every variant.
    queries = _expand_query(query)

    def normalize(results):
        if not results:
            return {}
        max_s = max(s for _, s in results) if results else 1
        min_s = min(s for _, s in results) if results else 0
        rng = max_s - min_s if max_s > min_s else 1
        return {c.chunk_id: (s - min_s) / rng for c, s in results}

    agg_kw: dict[str, float] = {}
    agg_dense: dict[str, float] = {}
    for q in queries:
        kw = normalize(_keyword_search(q, top_k=candidate_pool))
        dn = normalize(_dense_search(q, top_k=candidate_pool))
        for cid, s in kw.items():
            agg_kw[cid] = max(agg_kw.get(cid, 0), s)
        for cid, s in dn.items():
            agg_dense[cid] = max(agg_dense.get(cid, 0), s)

    # Combine: weighted average (keyword 0.4, dense 0.6) for candidate ranking.
    all_chunk_ids = set(agg_kw.keys()) | set(agg_dense.keys())

    candidates = []
    for cid in all_chunk_ids:
        kw = agg_kw.get(cid, 0)
        dense = agg_dense.get(cid, 0)
        hybrid_score = 0.4 * kw + 0.6 * dense
        if cid in chunk_map:
            candidates.append((chunk_map[cid], hybrid_score, kw, dense))

    candidates.sort(key=lambda x: x[1], reverse=True)
    candidates = candidates[:candidate_pool]

    # ── Stage 2: rerank the top candidates with a cross-encoder, then
    # apply a same-source diversity penalty so we don't surface 3 chunks
    # from one FDA label when the corpus has 30 docs.
    reranked = _rerank_candidates(query, candidates, top_k=candidate_pool)
    reranked = _diversify(reranked, top_k=top_k)

    # ── Build the response — only the top reranked snippets reach the LLM ──
    results = []
    for chunk, hybrid_score, kw_score, dense_score, rerank_score, backend in reranked:
        results.append({
            "text": chunk.text,
            "source": {
                "guideline": chunk.guideline_title,
                "file": chunk.source_file,
                "section": chunk.section,
            },
            "citation": chunk.to_citation(),
            "scores": {
                "rerank": round(rerank_score, 4),
                "hybrid": round(hybrid_score, 4),
                "keyword": round(kw_score, 4),
                "dense": round(dense_score, 4),
                "rerank_backend": backend,
            },
        })

    return results


# ── CLI for testing ──
if __name__ == "__main__":
    import sys
    import json

    print("=" * 60)
    print("  Clinical Guideline Evidence Retriever")
    print("=" * 60)

    # Index
    index_guidelines()

    # Default test queries or use CLI arg
    queries = [
        "What is the HbA1c target for a diabetic patient?",
        "How should I manage worsening shortness of breath in a COPD patient?",
        "What are the statin intensity recommendations for hyperlipidemia?",
        "What labs should I monitor for a patient on apixaban with AFib?",
        "How do I evaluate anemia with low hemoglobin and low hematocrit?",
    ]

    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]

    for query in queries:
        print(f"\n📌 Query: {query}")
        results = search_evidence(query, top_k=3)
        for i, r in enumerate(results):
            print(f"\n  [{i+1}] {r['source']['guideline']} → {r['source']['section']}")
            print(f"      Scores: hybrid={r['scores']['hybrid']}, kw={r['scores']['keyword']}, dense={r['scores']['dense']}")
            print(f"      {r['text'][:200]}...")
        print()
