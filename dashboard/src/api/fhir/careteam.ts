/**
 * FHIR R4 CareTeam fetcher.
 *
 * Returns participants with role + name. The legacy patient summary
 * doesn't have a CareTeam card on `demographics.php`; the requirement
 * called it out explicitly so we surface FHIR CareTeam directly. Empty
 * patients render the "Nothing recorded" branch — honest per the
 * "live data from the FHIR API" rule.
 */
import type { Bundle, CareTeam } from "fhir/r4";
import { fetchJson } from "../client";

export interface CareTeamRow {
  id: string;
  /** Participant display name (e.g. "Dr. Anjali Rao, MD"). */
  name: string;
  /** Role text — e.g. "Primary Care Physician", "Cardiologist". */
  role: string;
}

function participantName(p: CareTeam["participant"] extends (infer U)[] | undefined ? U : never): string {
  return p?.member?.display ?? "";
}

function participantRole(p: CareTeam["participant"] extends (infer U)[] | undefined ? U : never): string {
  const role = p?.role?.[0];
  return role?.text ?? role?.coding?.[0]?.display ?? "";
}

export async function fetchCareTeam(
  patientId: string,
  signal?: AbortSignal,
): Promise<CareTeamRow[]> {
  const path = `/CareTeam?patient=${encodeURIComponent(patientId)}&status=active`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  const rows: CareTeamRow[] = [];
  for (const e of entries) {
    const ct = e.resource as CareTeam | undefined;
    if (ct?.resourceType !== "CareTeam") continue;
    const participants = ct.participant ?? [];
    for (let i = 0; i < participants.length; i++) {
      const p = participants[i];
      const name = participantName(p);
      const role = participantRole(p);
      if (!name && !role) continue;
      rows.push({
        id: `${ct.id ?? "ct"}_${i}`,
        name: name || "Unnamed provider",
        role,
      });
    }
  }
  return rows;
}
