/**
 * FHIR R4 Patient fetcher for the demographics card.
 *
 * The legacy Twig (templates/patient/card/demographics.html.twig)
 * delegates to a PHP-side tabRow('DEM', ...) helper that renders the
 * full multi-tab demographics view. The "DEM" tab itself is a key-
 * value display of the patient record's basic identifying fields —
 * which is what we project out of the FHIR Patient resource here.
 *
 * Insurance (the "INS" tab) is its own card and lives in a separate
 * fetcher (api/fhir/coverage.ts when ported).
 */
import type { Patient } from "fhir/r4";
import { fetchJson } from "../client";

export interface DemographicsRow {
  /** Composed full name. */
  name: string;
  /** YYYY-MM-DD or "". */
  dob: string;
  /** Computed integer age, or null when DOB is missing. */
  age: number | null;
  /** "Male" | "Female" | "Other" | "Unknown" — capitalized for display. */
  sex: string;
  /** Single-line composed address ("street, city, state postal"). */
  address: string;
  /** Primary phone (telecom.use=home || first phone). */
  phone: string;
  /** Primary email if present. */
  email: string;
  /** Medical record number (identifier with use=usual or first ID). */
  mrn: string;
}

function fullName(p: Patient): string {
  const n = p.name?.[0];
  if (!n) return "";
  const given = (n.given ?? []).join(" ");
  return [given, n.family].filter(Boolean).join(" ");
}

function ageFrom(dob: string | undefined): number | null {
  if (!dob) return null;
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  let years = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) years -= 1;
  return years;
}

function capitalSex(g: string | undefined): string {
  if (!g) return "";
  return g.charAt(0).toUpperCase() + g.slice(1);
}

function singleLineAddress(p: Patient): string {
  const a = p.address?.[0];
  if (!a) return "";
  const street = (a.line ?? []).join(" ");
  const cityStateZip = [a.city, a.state, a.postalCode].filter(Boolean).join(" ");
  return [street, cityStateZip].filter(Boolean).join(", ");
}

function pickPhone(p: Patient): string {
  const tel = p.telecom ?? [];
  const home = tel.find((t) => t.system === "phone" && t.use === "home");
  if (home?.value) return home.value;
  const anyPhone = tel.find((t) => t.system === "phone");
  return anyPhone?.value ?? "";
}

function pickEmail(p: Patient): string {
  const tel = p.telecom ?? [];
  const e = tel.find((t) => t.system === "email");
  return e?.value ?? "";
}

function pickMrn(p: Patient): string {
  const ids = p.identifier ?? [];
  const usual = ids.find((i) => i.use === "usual");
  if (usual?.value) return usual.value;
  return ids[0]?.value ?? "";
}

export async function fetchDemographics(
  patientUuid: string,
  signal?: AbortSignal,
): Promise<DemographicsRow> {
  const path = `/Patient/${encodeURIComponent(patientUuid)}`;
  const p = await fetchJson<Patient>(path, { signal });
  return {
    name: fullName(p),
    dob: p.birthDate ?? "",
    age: ageFrom(p.birthDate),
    sex: capitalSex(p.gender),
    address: singleLineAddress(p),
    phone: pickPhone(p),
    email: pickEmail(p),
    mrn: pickMrn(p),
  };
}
