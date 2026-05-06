/**
 * FHIR R4 Encounter fetcher for the patient dashboard.
 *
 * The legacy summary page does not have a dedicated "encounters" card —
 * the encounter list lives on interface/patient_file/history/encounters.php
 * (a full-page table). The AI co-pilot's get_recent_encounters tool already
 * surfaces this data via FHIR; this widget makes the same view available
 * inside the patient dashboard's card grid.
 *
 * Display contract (one row per encounter):
 *   - date string                 (Encounter.period.start)
 *   - reason / type description   (Encounter.reasonCode.text || type[0].text)
 *
 * The DOM shape matches the existing medication card so the row visually
 * lines up with the other dashboard widgets.
 */
import type { Bundle, Encounter } from "fhir/r4";
import { fetchJson } from "../client";

export interface EncounterRow {
  id: string;
  /** YYYY-MM-DD trimmed off the FHIR period.start. */
  date: string;
  /** Visit reason or type, suitable for one-line display. */
  reason: string;
}

function encounterDate(e: Encounter): string {
  const start = e.period?.start;
  if (!start) return "";
  return start.slice(0, 10);
}

function encounterReason(e: Encounter): string {
  const rc = e.reasonCode?.[0];
  if (rc?.text) return rc.text;
  if (rc?.coding?.[0]?.display) return rc.coding[0].display;

  const t = e.type?.[0];
  if (t?.text) return t.text;
  if (t?.coding?.[0]?.display) return t.coding[0].display;

  return "Visit";
}

export async function fetchRecentEncounters(
  patientId: string,
  signal?: AbortSignal,
  limit = 10,
): Promise<EncounterRow[]> {
  const path =
    `/Encounter?patient=${encodeURIComponent(patientId)}` +
    `&_count=${limit}&_sort=-date`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as Encounter | undefined)
    .filter((e): e is Encounter => e?.resourceType === "Encounter")
    .map((e): EncounterRow => ({
      id: e.id ?? `e_${Math.random().toString(36).slice(2, 10)}`,
      date: encounterDate(e),
      reason: encounterReason(e),
    }))
    .sort((a, b) => (a.date < b.date ? 1 : -1));
}
