/**
 * FHIR R4 Immunization fetcher.
 *
 * Maps to the legacy Twig (templates/patient/card/immunizations.html.twig)
 * which renders one row per immunization with a CVX-coded vaccine name.
 */
import type { Bundle, Immunization } from "fhir/r4";
import { fetchJson } from "../client";

export interface ImmunizationRow {
  id: string;
  /** Vaccine name. Maps to the legacy `i.cvx_text`. */
  cvx_text: string;
  /** YYYY-MM-DD or "". */
  date: string;
}

function vaccineName(im: Immunization): string {
  const cc = im.vaccineCode;
  if (cc?.text) return cc.text;
  if (cc?.coding?.[0]?.display) return cc.coding[0].display;
  return "Unknown vaccine";
}

export async function fetchImmunizations(
  patientId: string,
  signal?: AbortSignal,
): Promise<ImmunizationRow[]> {
  const path = `/Immunization?patient=${encodeURIComponent(patientId)}&_sort=-date`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as Immunization | undefined)
    .filter((im): im is Immunization => im?.resourceType === "Immunization")
    .map((im): ImmunizationRow => ({
      id: im.id ?? `i_${Math.random().toString(36).slice(2, 10)}`,
      cvx_text: vaccineName(im),
      date: im.occurrenceDateTime?.slice(0, 10) ?? "",
    }));
}
