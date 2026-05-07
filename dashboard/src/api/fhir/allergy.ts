/**
 * FHIR R4 AllergyIntolerance fetcher for the patient dashboard.
 *
 * The legacy Twig template (templates/patient/card/allergies.html.twig)
 * needs three things per row:
 *   - title           → allergen name
 *   - severity_al     → severity code, used to decide highlight class
 *   - reaction_title  → reaction text shown in the row's title attribute
 *
 * FHIR AllergyIntolerance maps cleanly:
 *   - code.text / code.coding[0].display     → title
 *   - reaction[0].severity                   → severity_al ("mild"|"moderate"|"severe")
 *     OR criticality ("high" → severe-equivalent)                        ↑
 *   - reaction[0].manifestation[0].text      → reaction_title
 */
import type { AllergyIntolerance, Bundle } from "fhir/r4";
import { fetchJson } from "../client";

/** The codes the legacy Twig flags with bg-warning. */
const HIGH_SEVERITY_CODES = new Set([
  "severe",
  "life_threatening_severity",
  "fatal",
]);

export interface AllergyRow {
  id: string;
  title: string;
  severity_al: string;          // raw severity code (e.g. "mild"|"severe"|"")
  severity_display: string;     // human-readable (e.g. "Severe")
  reaction_title: string;
  is_high_severity: boolean;
}

function allergenTitle(r: AllergyIntolerance): string {
  const cc = r.code;
  if (cc?.text) return cc.text;
  // OpenEMR's FHIR projection only populates AllergyIntolerance.code when
  // `lists.diagnosis` carries a SNOMED/RxNorm code. Our ingest writes the
  // allergen as free text in `lists.title` and leaves `diagnosis` empty,
  // so code.coding[0] comes back as ("unknown", "Unknown") via the
  // data-absent-reason CodeSystem. The actual allergen lives in
  // text.div as XHTML; strip the wrapping <div> and use that.
  const display = cc?.coding?.[0]?.display;
  const isAbsent = display === "Unknown" || cc?.coding?.[0]?.code === "unknown";
  if (display && !isAbsent) return display;
  const div = r.text?.div;
  if (div) {
    const stripped = div.replace(/<[^>]+>/g, "").trim();
    if (stripped) return stripped;
  }
  return display ?? "Unknown allergen";
}

function severityCode(r: AllergyIntolerance): string {
  // Prefer reaction.severity (mild/moderate/severe). Fall back to
  // criticality (low/high/unable-to-assess) — "high" maps to severe.
  const rxn = r.reaction?.[0]?.severity;
  if (rxn) return rxn;
  if (r.criticality === "high") return "severe";
  return "";
}

function severityDisplay(code: string): string {
  if (!code) return "";
  // Capitalize the first letter (severe → Severe).
  return code.charAt(0).toUpperCase() + code.slice(1).replace(/_/g, " ");
}

function reactionText(r: AllergyIntolerance): string {
  const m = r.reaction?.[0]?.manifestation?.[0];
  return m?.text ?? m?.coding?.[0]?.display ?? "";
}

export async function fetchAllergies(
  patientId: string,
  signal?: AbortSignal,
): Promise<AllergyRow[]> {
  const path = `/AllergyIntolerance?patient=${encodeURIComponent(patientId)}`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as AllergyIntolerance | undefined)
    .filter(
      (r): r is AllergyIntolerance => r?.resourceType === "AllergyIntolerance",
    )
    .map((r): AllergyRow => {
      const code = severityCode(r);
      return {
        id: r.id ?? `a_${Math.random().toString(36).slice(2, 10)}`,
        title: allergenTitle(r),
        severity_al: code,
        severity_display: severityDisplay(code),
        reaction_title: reactionText(r),
        is_high_severity: HIGH_SEVERITY_CODES.has(code),
      };
    });
}
