/**
 * Family history fetcher.
 *
 * OpenEMR does not expose FamilyMemberHistory as a FHIR resource — the
 * route 404s. The data lives in OpenEMR's history_data table (free-text
 * per-relation columns), and the agent surfaces it through a small JSON
 * endpoint at /family-history/<uuid> that returns rows pre-shaped for
 * this widget. Keeping the React side identical means no widget changes.
 */
import { fetchJson } from "../client";

export interface FamilyHistoryRow {
  id: string;
  /** Mother / Father / Sibling / etc. */
  relation: string;
  /** Comma-joined list of conditions. */
  conditions: string;
  /** Optional age + status (e.g. "deceased age 78"). */
  status: string;
}

export async function fetchFamilyHistory(
  patientId: string,
  signal?: AbortSignal,
): Promise<FamilyHistoryRow[]> {
  // Same-origin agent endpoint, NOT the /apis FHIR proxy. The agent reads
  // history_data directly because no FHIR projection exists for it.
  const path = `/family-history/${encodeURIComponent(patientId)}`;
  return fetchJson<FamilyHistoryRow[]>(path, { signal });
}
