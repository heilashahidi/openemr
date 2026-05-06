/**
 * FHIR R4 MedicationRequest fetcher for the patient dashboard.
 *
 * The official @types/fhir package gives us full typed access to the
 * MedicationRequest resource and its Bundle wrapper, so this file is mostly
 * pulling out the two display strings the existing Twig template renders:
 *   <span class="font-weight-normal">{title}</span>
 *   <span>{drug_dosage_instructions}</span>
 */
import type { Bundle, MedicationRequest } from "fhir/r4";
import { fetchJson } from "../client";

/** Shape consumed by the React widget — flattened, presentation-ready. */
export interface MedicationRow {
  /** Stable id used for React keys + accessibility. */
  id: string;
  /** Drug name. Maps to the existing Twig `m.title`. */
  title: string;
  /** Dosage line, e.g. "10 mg PO daily". Maps to `m.drug_dosage_instructions`. */
  drug_dosage_instructions: string;
  /** True for status==='active' — used so the React layer can match the
      existing PHP filter (it only shows active prescriptions). */
  active: boolean;
}

/**
 * Pull the human-readable drug name out of a MedicationRequest. FHIR allows
 * the medication to be either an inline CodeableConcept or a reference; the
 * OpenEMR backend uses CodeableConcept.text in practice, so we prefer that.
 */
function drugTitle(r: MedicationRequest): string {
  const cc = r.medicationCodeableConcept;
  if (cc?.text) return cc.text;
  if (cc?.coding?.[0]?.display) return cc.coding[0].display;
  return "Unknown medication";
}

/**
 * Compose the same one-line dosage instruction the existing PHP page shows.
 * FHIR's dosageInstruction is verbose; the legacy UI shows a single trimmed
 * line, so we collapse to a sensible summary.
 */
function dosageLine(r: MedicationRequest): string {
  const di = r.dosageInstruction?.[0];
  if (!di) return "";
  const text = di.text?.trim();
  if (text) return text;

  const dose = di.doseAndRate?.[0]?.doseQuantity;
  const doseStr = dose ? `${dose.value ?? ""} ${dose.unit ?? ""}`.trim() : "";
  const route = di.route?.text ?? di.route?.coding?.[0]?.display ?? "";
  const freq = di.timing?.code?.text ?? di.timing?.code?.coding?.[0]?.display ?? "";
  return [doseStr, route, freq].filter(Boolean).join(" ").trim();
}

/**
 * Fetch active MedicationRequest entries for a patient and return rows
 * shaped exactly like the legacy widget consumed.
 */
export async function fetchActiveMedications(
  patientId: string,
  signal?: AbortSignal,
): Promise<MedicationRow[]> {
  const path = `/MedicationRequest?patient=${encodeURIComponent(patientId)}&status=active`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as MedicationRequest | undefined)
    .filter((r): r is MedicationRequest => r?.resourceType === "MedicationRequest")
    .map((r): MedicationRow => ({
      id: r.id ?? cryptoRandomId(),
      title: drugTitle(r),
      drug_dosage_instructions: dosageLine(r),
      active: r.status === "active",
    }));
}

function cryptoRandomId(): string {
  // Stable enough for React keys when the FHIR resource is missing an id
  return `m_${Math.random().toString(36).slice(2, 10)}`;
}
