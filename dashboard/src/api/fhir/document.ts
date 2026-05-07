/**
 * FHIR R4 DocumentReference fetcher.
 *
 * The patient summary doesn't have a documents card; documents live in
 * a separate tree panel. This widget exposes recent DocumentReferences
 * inline on the dashboard, so the user can see attached intake forms,
 * lab PDFs, etc., without leaving the page.
 */
import type { Bundle, DocumentReference } from "fhir/r4";
import { fetchJson } from "../client";

export interface DocumentRow {
  id: string;
  /** Filename or human-readable description. */
  title: string;
  /** Document type (e.g. "Lab Report", "Patient Information"). */
  category: string;
  /** YYYY-MM-DD or "". */
  date: string;
  /** First content URL if FHIR provides one (otherwise empty). */
  href: string;
}

function docTitle(d: DocumentReference): string {
  // Prefer (in order): the attachment filename (the most useful display
  // for our PDFs), description, type.text, type.coding[0].display.
  // OpenEMR's projection leaves description/type empty for our uploads
  // and emits type.coding=[{code:"UNK", display:"unknown"}], so without
  // the attachment.title fallback every link rendered as "unknown".
  const filename = d.content?.[0]?.attachment?.title;
  if (filename) return filename;
  if (d.description) return d.description;
  const t = d.type;
  const display = t?.text ?? t?.coding?.[0]?.display;
  if (display && display.toLowerCase() !== "unknown") return display;
  return "Untitled document";
}

function docCategory(d: DocumentReference): string {
  const cat = d.category?.[0];
  return cat?.text ?? cat?.coding?.[0]?.display ?? "";
}

function docHref(d: DocumentReference): string {
  const url = d.content?.[0]?.attachment?.url;
  if (!url) return "";
  // OpenEMR returns absolute URLs that point at its container's internal
  // address (e.g. https://localhost:9300/apis/default/fhir/Binary/<id>).
  // The browser can't reach localhost:9300 from the dashboard's origin —
  // rewrite to path-only so the link routes through the same-origin
  // /apis proxy on the agent (which has the bearer token attached).
  try {
    const u = new URL(url, window.location.href);
    return u.pathname + u.search;
  } catch {
    return url;
  }
}

export async function fetchDocuments(
  patientId: string,
  signal?: AbortSignal,
  limit = 25,
): Promise<DocumentRow[]> {
  const path =
    `/DocumentReference?patient=${encodeURIComponent(patientId)}` +
    `&_count=${limit}&_sort=-date`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as DocumentReference | undefined)
    .filter(
      (d): d is DocumentReference => d?.resourceType === "DocumentReference",
    )
    .map((d): DocumentRow => ({
      id: d.id ?? `d_${Math.random().toString(36).slice(2, 10)}`,
      title: docTitle(d),
      category: docCategory(d),
      date: d.date?.slice(0, 10) ?? "",
      href: docHref(d),
    }));
}
