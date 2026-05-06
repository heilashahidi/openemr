/**
 * Recent Vitals card — same DOM shape as the Labs and Medications cards.
 *
 * No exact legacy Twig template; vitals live in the per-encounter form
 * on the legacy stack. The widget surfaces the most recent vital-signs
 * Observations (BP, HR, temp, weight, height, BMI, …) so the dashboard
 * shows them at-a-glance without needing to drill into an encounter.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchRecentVitals, VitalRow } from "../api/fhir/vital";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function VitalsCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["vitals", patientId],
    queryFn: ({ signal }) => fetchRecentVitals(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "recent-vitals";

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
            Recent Vitals
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
            <VitalsBody
              isLoading={isLoading}
              isError={isError}
              error={error}
              list={data}
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
  list: VitalRow[] | undefined;
}

function VitalsBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
  if (isLoading) {
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1 text-muted">Loading…</div>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1 text-danger">
          {error instanceof Error ? error.message : "Failed to load vitals"}
        </div>
      </div>
    );
  }
  if (!list || list.length === 0) {
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1">No vitals documented</div>
      </div>
    );
  }
  return (
    <div className="list-group list-group-flush pami-list">
      {list.map((v) => (
        <div
          key={v.id}
          className="list-group-item p-0 pl-1"
          title={v.date ? `Recorded ${v.date}` : undefined}
        >
          <span className="font-weight-normal">{v.title}</span>{" "}
          <span>{v.value_with_unit}</span>
        </div>
      ))}
    </div>
  );
}
