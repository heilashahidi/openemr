/**
 * Coverage / insurance fetcher.
 *
 * OpenEMR's FHIR Coverage projection requires insurance_data.provider to
 * be an FK into insurance_companies, but that table is empty in this
 * install — Coverage searches return total=0 even when insurance_data
 * has live rows. The agent reads insurance_data directly and exposes
 * pre-shaped rows at /coverage/<uuid>. Subscriber/employer addresses
 * aren't exposed here (OpenEMR's PHP-side composition); the widget
 * already shows "—" for those columns when missing.
 */
import { fetchJson } from "../client";

export type CoverageType = "primary" | "secondary" | "tertiary";

export interface CoverageRow {
  id: string;
  type: CoverageType;
  insurer_name: string;
  plan_name: string;
  policy_number: string;
  group_number: string;
  copay: string;
  accept_assignment: string;
  date: string;
  date_end: string;
}

export async function fetchCoverages(
  patientId: string,
  signal?: AbortSignal,
): Promise<CoverageRow[]> {
  const path = `/coverage/${encodeURIComponent(patientId)}`;
  return fetchJson<CoverageRow[]>(path, { signal, flavor: "agent" });
}
