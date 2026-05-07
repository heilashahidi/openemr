/**
 * Recent labs fetcher.
 *
 * OpenEMR's FHIR Observation projection doesn't surface our
 * procedure_result rows — even a direct GET on a known result UUID
 * returns []. The agent reads procedure_order/report/result directly
 * and exposes them at /labs/<uuid>, pre-shaped for this widget.
 *
 * Display contract (unchanged):
 *   title           = lab test name
 *   value_with_unit = "5.4 10^3/uL" / "8.2 %"
 *   flag            = "H" / "L" / "A" / ""
 *   date            = YYYY-MM-DD
 *   is_abnormal     = highlight row when true
 */
import { fetchJson } from "../client";

export interface LabRow {
  id: string;
  title: string;
  value_with_unit: string;
  flag: string;
  date: string;
  is_abnormal: boolean;
}

export async function fetchRecentLabs(
  patientId: string,
  signal?: AbortSignal,
): Promise<LabRow[]> {
  const path = `/labs/${encodeURIComponent(patientId)}`;
  return fetchJson<LabRow[]>(path, { signal, flavor: "agent" });
}
