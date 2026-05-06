/**
 * Family History card — modeled on the medication card's two-span DOM
 * (relation on the left, conditions on the right). No exact legacy Twig
 * template exists for the patient summary; family history lives in the
 * History form. The widget surfaces FHIR FamilyMemberHistory so the
 * dashboard shows it at-a-glance.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchFamilyHistory, FamilyHistoryRow } from "../api/fhir/family";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function FamilyHistoryCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["family-history", patientId],
    queryFn: ({ signal }) => fetchFamilyHistory(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "family-history";

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
            Family History
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
            <FamilyHistoryBody
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
  list: FamilyHistoryRow[] | undefined;
}

function FamilyHistoryBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load family history"}
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
      {list.map((f) => (
        <div
          key={f.id}
          className="list-group-item p-0 pl-1"
          title={f.status || undefined}
        >
          <span className="font-weight-normal">{f.relation}:</span>{" "}
          <span>
            {f.conditions}
            {f.status ? ` (${f.status})` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}
