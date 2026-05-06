/**
 * FHIR R4 Observation fetcher (vital-signs category) for the dashboard.
 *
 * The legacy patient summary doesn't have a vitals card — vitals live
 * in the per-encounter form. This widget surfaces recent vitals using
 * the same DOM the Labs card uses, so the row visually lines up with
 * the rest of the dashboard.
 *
 * Filter: category=vital-signs is the canonical FHIR R4 way to scope
 * to vital observations (LOINC codes 85354-9 BP panel, 8867-4 heart
 * rate, 8310-5 body temp, 29463-7 weight, 8302-2 height, 39156-5 BMI,
 * etc.). Blood pressure is reported as a single Observation with
 * `component[]` carrying systolic + diastolic — the fetcher composes
 * those into "120/80 mmHg" for display.
 */
import type { Bundle, Observation } from "fhir/r4";
import { fetchJson } from "../client";

const BP_PANEL_CODES = new Set(["85354-9", "55284-4"]);

export interface VitalRow {
  id: string;
  /** Vital name. */
  title: string;
  /** Value + unit, e.g. "120/80 mmHg", "98.6 °F", "70 kg". */
  value_with_unit: string;
  /** YYYY-MM-DD or "". */
  date: string;
}

function vitalTitle(o: Observation): string {
  const cc = o.code;
  if (cc?.text) return cc.text;
  if (cc?.coding?.[0]?.display) return cc.coding[0].display;
  return "Unknown vital";
}

function quantityToString(
  value: number | undefined,
  unit: string | undefined,
): string {
  if (value === undefined) return "";
  return `${value}${unit ? " " + unit : ""}`;
}

function vitalValue(o: Observation): string {
  // Blood pressure → compose systolic/diastolic from component entries.
  const code = o.code?.coding?.[0]?.code ?? "";
  if (BP_PANEL_CODES.has(code) && o.component && o.component.length >= 2) {
    const sys = o.component.find((c) => c.code?.coding?.[0]?.code === "8480-6");
    const dia = o.component.find((c) => c.code?.coding?.[0]?.code === "8462-4");
    const sysV = sys?.valueQuantity?.value;
    const diaV = dia?.valueQuantity?.value;
    const unit = sys?.valueQuantity?.unit ?? dia?.valueQuantity?.unit ?? "mmHg";
    if (sysV !== undefined && diaV !== undefined) {
      return `${sysV}/${diaV} ${unit}`;
    }
  }

  const q = o.valueQuantity;
  if (q && q.value !== undefined) return quantityToString(q.value, q.unit);
  if (o.valueString) return o.valueString;
  return "";
}

function vitalDate(o: Observation): string {
  const d = o.effectiveDateTime ?? o.effectivePeriod?.start;
  return d ? d.slice(0, 10) : "";
}

export async function fetchRecentVitals(
  patientId: string,
  signal?: AbortSignal,
  limit = 20,
): Promise<VitalRow[]> {
  const path =
    `/Observation?patient=${encodeURIComponent(patientId)}` +
    `&category=vital-signs&_count=${limit}&_sort=-date`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as Observation | undefined)
    .filter((o): o is Observation => o?.resourceType === "Observation")
    .map((o): VitalRow => ({
      id: o.id ?? `v_${Math.random().toString(36).slice(2, 10)}`,
      title: vitalTitle(o),
      value_with_unit: vitalValue(o),
      date: vitalDate(o),
    }));
}
