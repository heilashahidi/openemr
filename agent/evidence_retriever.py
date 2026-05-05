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


def _chunk_markdown(filepath: str) -> list[GuidelineChunk]:
    """Split a markdown guideline into section-level chunks."""
    filename = Path(filepath).name
    with open(filepath, "r") as f:
        content = f.read()

    # Extract title from first heading
    title_match = re.match(r"^#\s+(.*)", content)
    title = title_match.group(1) if title_match else filename

    chunks = []
    current_section = "Introduction"
    current_text = ""

    for line in content.split("\n"):
        # New section at ## heading
        if line.startswith("## "):
            if current_text.strip():
                chunk_id = hashlib.md5(f"{filename}:{current_section}".encode()).hexdigest()[:8]
                chunks.append(GuidelineChunk(
                    text=current_text.strip(),
                    source_file=filename,
                    section=current_section,
                    guideline_title=title,
                    chunk_id=chunk_id,
                ))
            current_section = line.lstrip("# ").strip()
            current_text = ""
        else:
            current_text += line + "\n"

    # Last section
    if current_text.strip():
        chunk_id = hashlib.md5(f"{filename}:{current_section}".encode()).hexdigest()[:8]
        chunks.append(GuidelineChunk(
            text=current_text.strip(),
            source_file=filename,
            section=current_section,
            guideline_title=title,
            chunk_id=chunk_id,
        ))

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


def search_evidence(query: str, top_k: int = 5) -> list[dict]:
    """
    Hybrid search: combine BM25 keyword + dense vector retrieval, then rerank.

    Returns list of evidence snippets with source metadata and scores.
    """
    # Ensure index exists
    if _collection is None or len(_chunks) == 0:
        index_guidelines()

    if not _chunks:
        return []

    # Get candidates from both methods
    keyword_results = _keyword_search(query, top_k=15)
    dense_results = _dense_search(query, top_k=15)

    # Normalize scores to 0-1 range
    def normalize(results):
        if not results:
            return {}
        max_score = max(s for _, s in results) if results else 1
        min_score = min(s for _, s in results) if results else 0
        range_score = max_score - min_score if max_score > min_score else 1
        return {c.chunk_id: (s - min_score) / range_score for c, s in results}

    kw_scores = normalize(keyword_results)
    dense_scores = normalize(dense_results)

    # Combine: weighted average (keyword 0.4, dense 0.6)
    all_chunk_ids = set(kw_scores.keys()) | set(dense_scores.keys())
    chunk_map = {c.chunk_id: c for c in _chunks}

    combined = []
    for cid in all_chunk_ids:
        kw = kw_scores.get(cid, 0)
        dense = dense_scores.get(cid, 0)
        hybrid_score = 0.4 * kw + 0.6 * dense
        if cid in chunk_map:
            combined.append((chunk_map[cid], hybrid_score, kw, dense))

    # Sort by hybrid score (this is the reranking step)
    combined.sort(key=lambda x: x[1], reverse=True)

    # Return top_k with metadata
    results = []
    for chunk, hybrid_score, kw_score, dense_score in combined[:top_k]:
        results.append({
            "text": chunk.text,
            "source": {
                "guideline": chunk.guideline_title,
                "file": chunk.source_file,
                "section": chunk.section,
            },
            "citation": chunk.to_citation(),
            "scores": {
                "hybrid": round(hybrid_score, 4),
                "keyword": round(kw_score, 4),
                "dense": round(dense_score, 4),
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
