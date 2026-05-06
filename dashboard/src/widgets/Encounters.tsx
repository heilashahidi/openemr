/**
 * Recent Encounters card — modeled after templates/patient/card/medication.html.twig
 * since there is no dedicated encounter card in the legacy patient summary
 * (encounters are shown on a separate full-page module). The same DOM
 * shape keeps it visually consistent with the rest of the dashboard.
 *
 *   <div class="list-group list-group-flush pami-list">
 *     <div class="list-group-item p-0 pl-1">
 *       <span class="font-weight-normal">{date}</span>
 *       <span>{reason}</span>
 *     </div>
 *   </div>
 */
import { useQuery } from "@tanstack/react-query";
import { fetchRecentEncounters, EncounterRow } from "../api/fhir/encounter";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function EncountersCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["encounters", patientId],
    queryFn: ({ signal }) => fetchRecentEncounters(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "recent-encounters";

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
            Recent Encounters
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
            <EncountersBody
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
  list: EncounterRow[] | undefined;
}

function EncountersBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load encounters"}
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
      {list.map((e) => (
        <div key={e.id} className="list-group-item p-0 pl-1">
          <span className="font-weight-normal">{e.date}</span>{" "}
          <span>{e.reason}</span>
        </div>
      ))}
    </div>
  );
}
