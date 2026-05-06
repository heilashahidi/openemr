/**
 * Insurance card — React port of templates/patient/card/insurance.html.twig.
 *
 * Faithful to the legacy structure where it counts:
 *   - <ul class="nav nav-tabs ...">  with one tab per coverage type
 *   - <div class="tab-content">       with a pane per type
 *   - inside each pane, the policy details rendered via the same
 *     two-column list-group layout (Plan Name / Policy Number / Group
 *     on the left; Copay / Accepts Assignment on the right).
 *
 * NOT ported (and intentionally so):
 *   - subscriber + employer addresses — those are PHP-side joins against
 *     additional tables, not part of FHIR Coverage.
 *   - per-coverage policy pagination — not exposed by FHIR; the most
 *     recent policy per type is shown.
 *   - the eligibility tab — that's a separate workflow, not a port-this
 *     widget concern.
 *
 * All the structural classes the legacy stylesheet targets are preserved
 * (.insurance-nav-tabs, .tab-content, .tab-pane, .list-group-flush,
 * .d-flex.justify-content-between, etc.) so any CSS keyed off them keeps
 * working unchanged.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchCoverages, CoverageRow, CoverageType } from "../api/fhir/coverage";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

const TYPE_ORDER: CoverageType[] = ["primary", "secondary", "tertiary"];
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function InsuranceCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["coverage", patientId],
    queryFn: ({ signal }) => fetchCoverages(patientId, signal),
    staleTime: 60_000,
  });

  // Group policies by coverage type and pick the most-recent one per type
  // (matches the "first pane visible" behavior of the legacy template).
  const byType = useMemo(() => {
    const map = new Map<CoverageType, CoverageRow>();
    (data ?? []).forEach((c) => {
      if (!map.has(c.type)) map.set(c.type, c);
    });
    return map;
  }, [data]);

  const presentTypes = TYPE_ORDER.filter((t) => byType.has(t));
  const [activeType, setActiveType] = useState<CoverageType>("primary");
  const effectiveActive = presentTypes.includes(activeType)
    ? activeType
    : presentTypes[0] ?? "primary";

  const cardBodyId = "insurance";

  return (
    <section className="card">
      <div className="card-body p-1">
        <h6 className="card-title mb-0 d-flex p-1 justify-content-between">
          <a
            className="text-left font-weight-bolder"
            href="#"
            data-toggle="collapse"
            data-target={`#${cardBodyId}`}
            aria-expanded={!initiallyCollapsed}
            aria-controls={cardBodyId}
          >
            Insurance
            <i
              className={`ml-1 fa fa-fw ${initiallyCollapsed ? "fa-expand" : "fa-compress"}`}
              data-target={`#${cardBodyId}`}
            />
          </a>
        </h6>
        <div
          id={cardBodyId}
          className={`card-text collapse${initiallyCollapsed ? "" : " show"}`}
        >
          <div className="clearfix pt-2">
            <InsuranceBody
              isLoading={isLoading}
              isError={isError}
              error={error}
              presentTypes={presentTypes}
              active={effectiveActive}
              setActive={setActiveType}
              policyByType={byType}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

interface BodyProps {
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  presentTypes: CoverageType[];
  active: CoverageType;
  setActive: (t: CoverageType) => void;
  policyByType: Map<CoverageType, CoverageRow>;
}

function InsuranceBody(p: BodyProps): JSX.Element {
  if (p.isLoading) {
    return <div className="text-muted px-1">Loading…</div>;
  }
  if (p.isError) {
    return (
      <div className="text-danger px-1">
        {p.error instanceof Error ? p.error.message : "Failed to load coverages"}
      </div>
    );
  }
  if (p.presentTypes.length === 0) {
    return <div className="px-1">Nothing Recorded</div>;
  }

  const policy = p.policyByType.get(p.active)!;

  return (
    <>
      <ul className="nav nav-tabs mb-2 insurance-nav-tabs">
        {p.presentTypes.map((t) => (
          <li key={t} className="nav-item" role="presentation">
            <a
              data-type={t}
              href={`#${t}`}
              id={`${t}-tab`}
              role="tab"
              aria-controls={t}
              aria-selected={t === p.active}
              className={`nav-link${t === p.active ? " active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                p.setActive(t);
              }}
            >
              {cap(t)}
            </a>
          </li>
        ))}
      </ul>
      <div className="tab-content px-1">
        <div className="tab-pane active" id={p.active} role="tabpanel" aria-labelledby={`${p.active}-tab`}>
          <PolicyPane policy={policy} />
        </div>
      </div>
    </>
  );
}

function PolicyPane({ policy }: { policy: CoverageRow }): JSX.Element {
  const dateRange =
    [policy.date && `from ${policy.date}`, `until ${policy.date_end || "Present"}`]
      .filter(Boolean)
      .join(" ");

  return (
    <div>
      <div className="text-primary pb-2 pt-1">
        {cap(policy.type)} Insurance {dateRange}
      </div>
      <div className="d-flex justify-content-between">
        <div className="insurer">
          {policy.insurer_name ? (
            <>
              <em>Insurer</em>
              <address>
                <strong>{policy.insurer_name}</strong>
              </address>
            </>
          ) : (
            <span className="font-weight-bold text-danger">Unassigned</span>
          )}
        </div>
        {/* subscriber + employer columns are PHP-side compositions not in
            FHIR Coverage; we render the labels for visual continuity but
            don't populate them. */}
        <div className="subscriber text-muted">
          <em>Subscriber</em>
          <address className="mb-1">—</address>
        </div>
        <div className="subscriber-employer text-muted">
          <em>Subscriber Employer</em>
          <address className="mb-1">—</address>
        </div>
      </div>
      <div className="d-flex justify-content-between policy-details pt-2">
        <div className="list-group list-group-flush flex-fill mr-4">
          <div className="list-group-item d-flex justify-content-between p-1">
            <strong>Plan Name:</strong>
            <span className="text-right">{policy.plan_name || "—"}</span>
          </div>
          <div className="list-group-item d-flex justify-content-between p-1">
            <strong>Policy Number:</strong>
            <span className="text-right text-monospace">{policy.policy_number || "—"}</span>
          </div>
          <div className="list-group-item d-flex justify-content-between p-1">
            <strong>Group Number:</strong>
            <span className="text-right text-monospace">{policy.group_number || "—"}</span>
          </div>
        </div>
        <div className="list-group list-group-flush flex-fill">
          <div className="list-group-item d-flex justify-content-between p-1">
            <strong>Copay:</strong>
            <span className="text-right">{policy.copay || "—"}</span>
          </div>
          <div className="list-group-item d-flex justify-content-between p-1">
            <strong>Accepts Assignment:</strong>
            <span className="text-right">
              {policy.accept_assignment === "TRUE"
                ? "Yes"
                : policy.accept_assignment === "FALSE"
                  ? "No"
                  : "—"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
