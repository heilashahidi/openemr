/**
 * Care Team fetcher.
 *
 * OpenEMR's FHIR CareTeam endpoint exists but doesn't read the data we
 * actually populate during ingestion (`patient_data.care_team_provider`,
 * the free-text "Primary Care Physician: Dr. X / Cardiologist: Dr. Y"
 * blob). The agent parses that text into one row per provider and
 * exposes it at /care-team/<uuid>.
 */
import { fetchJson } from "../client";

export interface CareTeamRow {
  id: string;
  /** Participant display name (e.g. "Dr. Anjali Rao, MD"). */
  name: string;
  /** Role text — e.g. "Primary Care Physician", "Cardiologist". */
  role: string;
}

export async function fetchCareTeam(
  patientId: string,
  signal?: AbortSignal,
): Promise<CareTeamRow[]> {
  const path = `/care-team/${encodeURIComponent(patientId)}`;
  return fetchJson<CareTeamRow[]>(path, { signal });
}
