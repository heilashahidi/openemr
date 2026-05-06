/**
 * FHIR R4 Coverage fetcher for the insurance card.
 *
 * The legacy Twig (templates/patient/card/insurance.html.twig) renders
 * tabs for each coverage type (Primary/Secondary/Tertiary) and per-policy
 * panes that show insurer + subscriber + subscriber-employer addresses
 * plus plan details. FHIR Coverage exposes the policy-level fields
 * directly, but the subscriber/employer addresses are PHP-side
 * compositions (joins against insurance_companies, addresses, etc.) and
 * are NOT part of the FHIR resource. This fetcher therefore returns the
 * subset that the FHIR API actually serves; the React widget renders the
 * same DOM structure for the policy-details list-group, and shows the
 * subscriber/employer columns as "—" with a tooltip when the data isn't
 * exposed via FHIR.
 */
import type { Bundle, Coverage } from "fhir/r4";
import { fetchJson } from "../client";

export type CoverageType = "primary" | "secondary" | "tertiary";

export interface CoverageRow {
  id: string;
  type: CoverageType;
  /** Insurer / payor display name. */
  insurer_name: string;
  plan_name: string;
  /** Membership / policy number — Coverage.subscriberId. */
  policy_number: string;
  /** Group number — pulled from Coverage.class entries. */
  group_number: string;
  /** Copay if available, formatted as "$10.00". */
  copay: string;
  /** "TRUE" | "FALSE" | "" — Coverage doesn't expose this directly so
      the value is rarely populated. */
  accept_assignment: string;
  /** Coverage period start (YYYY-MM-DD). */
  date: string;
  /** Coverage period end (YYYY-MM-DD) or "" if open-ended ("Present"). */
  date_end: string;
}

const TYPE_ORDER_TO_NAME: Record<number, CoverageType> = {
  1: "primary",
  2: "secondary",
  3: "tertiary",
};

function coverageType(c: Coverage): CoverageType {
  // OpenEMR stores rank in Coverage.order (1=primary, 2=secondary, 3=tertiary).
  if (c.order && TYPE_ORDER_TO_NAME[c.order]) return TYPE_ORDER_TO_NAME[c.order];
  // Fall back to Coverage.type code/text — common values are "primary",
  // "secondary", "tertiary", or the SOP coding.
  const t = c.type?.text ?? c.type?.coding?.[0]?.display ?? c.type?.coding?.[0]?.code ?? "";
  const lc = t.toLowerCase();
  if (lc.includes("second")) return "secondary";
  if (lc.includes("tert")) return "tertiary";
  return "primary";
}

function payorName(c: Coverage): string {
  const p = c.payor?.[0];
  return p?.display ?? "";
}

function classByType(c: Coverage, kind: string): string {
  const found = (c.class ?? []).find((cl) => {
    const code = cl.type?.coding?.[0]?.code?.toLowerCase() ?? "";
    return code === kind.toLowerCase();
  });
  return found?.value ?? "";
}

function copayString(c: Coverage): string {
  const cob = c.costToBeneficiary?.[0];
  const q = cob?.valueQuantity;
  if (q && q.value !== undefined) {
    const unit = q.unit ?? q.code ?? "";
    return `${unit === "USD" || unit === "$" ? "$" : ""}${q.value}${
      unit && unit !== "USD" && unit !== "$" ? " " + unit : ""
    }`;
  }
  return "";
}

export async function fetchCoverages(
  patientId: string,
  signal?: AbortSignal,
): Promise<CoverageRow[]> {
  const path = `/Coverage?patient=${encodeURIComponent(patientId)}`;
  const bundle = await fetchJson<Bundle>(path, { signal });
  const entries = bundle.entry ?? [];

  return entries
    .map((e) => e.resource as Coverage | undefined)
    .filter((c): c is Coverage => c?.resourceType === "Coverage")
    .map((c): CoverageRow => ({
      id: c.id ?? `cov_${Math.random().toString(36).slice(2, 10)}`,
      type: coverageType(c),
      insurer_name: payorName(c),
      plan_name: classByType(c, "plan") || c.network?.[0]?.toString() || "",
      policy_number: c.subscriberId ?? "",
      group_number: classByType(c, "group"),
      copay: copayString(c),
      accept_assignment: "",
      date: c.period?.start?.slice(0, 10) ?? "",
      date_end: c.period?.end?.slice(0, 10) ?? "",
    }))
    .sort((a, b) => {
      const order: CoverageType[] = ["primary", "secondary", "tertiary"];
      return order.indexOf(a.type) - order.indexOf(b.type);
    });
}
