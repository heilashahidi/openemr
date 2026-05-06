/**
 * Medical Problems card — React port of
 * templates/patient/card/medical_problems.html.twig.
 *
 * The Twig is the simplest of the three: list-group-flush wrapper, one
 * <div class="list-group-item py-1 px-1"> per condition title. Empty
 * state is "Nothing Recorded".
 *
 * Card title text matches the legacy stats.php call site
 * (xl('Medical Problems')).
 */
import { useQuery } from "@tanstack/react-query";
import { fetchActiveConditions, ConditionRow } from "../api/fhir/condition";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function ConditionsCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["conditions", patientId],
    queryFn: ({ signal }) => fetchActiveConditions(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "medical-problems";

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
            Medical Problems
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
            <ConditionsBody
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
  list: ConditionRow[] | undefined;
}

function ConditionsBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load conditions"}
        </div>
      </div>
    );
  }
  if (!list || list.length === 0) {
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1">Nothing Recorded</div>
      </div>
    );
  }
  return (
    <div className="list-group list-group-flush pami-list">
      {list.map((c) => (
        <div key={c.id} className="list-group-item py-1 px-1">
          {c.title}
        </div>
      ))}
    </div>
  );
}
