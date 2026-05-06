/**
 * FHIR R4 Observation fetcher (laboratory category) for the patient
 * dashboard.
 *
 * Like the encounter card, the legacy patient summary does not have a
 * dedicated labs card — recent labs live on a separate page. For visual
 * consistency inside the React dashboard we reuse the medication card's
 * two-span DOM and the allergy card's bg-warning highlight pattern for
 * abnormal flags.
 *
 * Display contract:
 *   title  = test name              (Observation.code.text || coding.display)
 *   value  = result value + unit    (valueQuantity.value + .unit)
 *   flag   = high/low/abnormal      (Observation.interpretation[0].coding.code)
 *   date   = collection date        (Observation.effectiveDateTime)
 *
 * Filter: category=laboratory matches the AI co-pilot's get_recent_labs
 * tool and the legacy "recent labs" panel on the encounter view.
 */
import type { Bundle, Observation } from "fhir/r4";
import { fetchJson } from "../client";

const HIGH_FLAG_CODES = new Set([
  "H", "HH", "L", "LL", "A", "AA",
  "high", "low", "critical", "abnormal",
]);

export interface LabRow {
  id: string;
  /** Lab test name. */
  title: string;
  /** Result value + unit, e.g. "8.2 %", "158 mg/dL". */
  value_with_unit: string;
  /** Flag display: "H", "L", "A", or empty for normal. */
  flag: string;
  /** YYYY-MM-DD or empty. */
  date: string;
  /** True when the row should render with the abnormal highlight. */
  is_abnormal: boolean;
}

function labTitle(o: Observation): string {
  const cc = o.code;
  if (cc?.text) return cc.text;
  if (cc?.coding?.[0]?.display) return cc.coding[0].display;
  return "Unknown test";
}

function labValue(o: Observation): string {
  const q = o.valueQuantity;
  if (q && (q.value !== undefined || q.unit)) {
    const v = q.value !== undefined ? String(q.value) : "";
    const u = q.unit ?? "";
    return `${v} ${u}`.trim();
  }
  if (o.valueString) return o.valueString;
  if (o.valueCodeableConcept?.text) return o.valueCodeableConcept.text;
  return "";
}

function labFlag(o: Observation): string {
  const interp = o.interpretation?.[0];
  return interp?.coding?.[0]?.code ?? interp?.text ?? "";
}

function labDate(o: Observation): string {
  const d = o.effectiveDateTime ?? o.effectivePeriod?.start;
  if (!d) return "";
  return d.slice(0, 10);
}

export async function fetchRecentLabs(
  patientId: string,
  signal?: AbortSignal,
  limit = 20,
): Promise<LabRow[]> {
  const path =
    `/Observation?patient=${encodeURIComponent(patientId)}` +
    `&category=laboratory&_count=${limit}&_sort=-date`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as Observation | undefined)
    .filter((o): o is Observation => o?.resourceType === "Observation")
    .map((o): LabRow => {
      const flag = labFlag(o);
      return {
        id: o.id ?? `l_${Math.random().toString(36).slice(2, 10)}`,
        title: labTitle(o),
        value_with_unit: labValue(o),
        flag,
        date: labDate(o),
        is_abnormal: HIGH_FLAG_CODES.has(flag),
      };
    });
}
