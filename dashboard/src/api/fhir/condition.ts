/**
 * FHIR R4 Condition fetcher for the patient dashboard.
 *
 * The legacy Twig (templates/patient/card/medical_problems.html.twig)
 * shows just the condition title in a flat list, so the fetcher is a
 * one-line projection of FHIR Condition.code → text.
 *
 * Filter: clinical-status=active matches the legacy behavior of only
 * showing problems on the active issue list (the OpenEMR PHP page filters
 * to `lists.activity = 1` for type='medical_problem').
 */
import type { Bundle, Condition } from "fhir/r4";
import { fetchJson } from "../client";

export interface ConditionRow {
  id: string;
  /** Condition name. Maps to the existing Twig `l.title`. */
  title: string;
}

function conditionTitle(c: Condition): string {
  const cc = c.code;
  if (cc?.text) return cc.text;
  if (cc?.coding?.[0]?.display) return cc.coding[0].display;
  return "Unknown condition";
}

export async function fetchActiveConditions(
  patientId: string,
  signal?: AbortSignal,
): Promise<ConditionRow[]> {
  const path =
    `/Condition?patient=${encodeURIComponent(patientId)}&clinical-status=active`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as Condition | undefined)
    .filter((c): c is Condition => c?.resourceType === "Condition")
    .map((c): ConditionRow => ({
      id: c.id ?? `c_${Math.random().toString(36).slice(2, 10)}`,
      title: conditionTitle(c),
    }));
}
