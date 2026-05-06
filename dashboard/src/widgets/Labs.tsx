/**
 * Recent Labs card — modeled on the medication card's two-span layout
 * (test name on the left, value+unit on the right) with the allergy
 * card's bg-warning highlight pattern for abnormal flags.
 *
 * No exact legacy Twig template exists for a labs card on the patient
 * summary; the legacy summary shows labs on the per-encounter view.
 * The DOM shape here is identical to medication.html.twig so the row
 * lines up visually with the other widgets in the dashboard grid.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchRecentLabs, LabRow } from "../api/fhir/lab";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function LabsCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["labs", patientId],
    queryFn: ({ signal }) => fetchRecentLabs(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "recent-labs";

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
            Recent Labs
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
            <LabsBody
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
  list: LabRow[] | undefined;
}

function LabsBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load labs"}
        </div>
      </div>
    );
  }
  if (!list || list.length === 0) {
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1">
          No laboratory results documented
        </div>
      </div>
    );
  }
  return (
    <div className="list-group list-group-flush pami-list">
      {list.map((l) => (
        <div
          key={l.id}
          className="list-group-item p-0 pl-1"
          title={l.date ? `Collected ${l.date}` : undefined}
        >
          <span className="font-weight-normal">{l.title}</span>{" "}
          <span
            className={
              l.is_abnormal ? "bg-warning font-weight-bold px-1" : ""
            }
          >
            {l.value_with_unit}
            {l.flag ? ` (${l.flag})` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}
