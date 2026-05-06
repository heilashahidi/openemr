/**
 * FHIR R4 FamilyMemberHistory fetcher.
 *
 * The legacy patient summary doesn't have a family-history card; that
 * data lives on the History form. This widget surfaces FHIR
 * FamilyMemberHistory entries so the dashboard shows them at-a-glance
 * alongside the other clinical context.
 */
import type { Bundle, FamilyMemberHistory } from "fhir/r4";
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

function relationOf(f: FamilyMemberHistory): string {
  const r = f.relationship;
  if (!r) return "";
  return r.text ?? r.coding?.[0]?.display ?? "";
}

function conditionsOf(f: FamilyMemberHistory): string {
  const cs = f.condition ?? [];
  return cs
    .map((c) => c.code?.text ?? c.code?.coding?.[0]?.display ?? "")
    .filter(Boolean)
    .join(", ");
}

function statusOf(f: FamilyMemberHistory): string {
  const parts: string[] = [];
  // FHIR distinguishes deceasedBoolean / deceasedAge / deceasedDate.
  const dec =
    f.deceasedBoolean !== undefined
      ? f.deceasedBoolean
        ? "deceased"
        : "alive"
      : f.deceasedAge?.value
        ? `deceased age ${f.deceasedAge.value}`
        : f.deceasedDate
          ? `deceased ${f.deceasedDate.slice(0, 10)}`
          : "";
  if (dec) parts.push(dec);
  if (f.ageAge?.value && !parts.length) parts.push(`age ${f.ageAge.value}`);
  return parts.join(", ");
}

export async function fetchFamilyHistory(
  patientId: string,
  signal?: AbortSignal,
): Promise<FamilyHistoryRow[]> {
  const path = `/FamilyMemberHistory?patient=${encodeURIComponent(patientId)}`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as FamilyMemberHistory | undefined)
    .filter(
      (f): f is FamilyMemberHistory => f?.resourceType === "FamilyMemberHistory",
    )
    .map((f): FamilyHistoryRow => ({
      id: f.id ?? `f_${Math.random().toString(36).slice(2, 10)}`,
      relation: relationOf(f),
      conditions: conditionsOf(f) || "(no conditions reported)",
      status: statusOf(f),
    }));
}
