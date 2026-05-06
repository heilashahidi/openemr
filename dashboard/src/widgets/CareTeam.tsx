/**
 * Care Team card — backed by FHIR CareTeam. Two-span DOM that matches
 * the medication card: role on the left, member name on the right.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchCareTeam, CareTeamRow } from "../api/fhir/careteam";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function CareTeamCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["care-team", patientId],
    queryFn: ({ signal }) => fetchCareTeam(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "care-team";

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
            Care Team
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
            <CareTeamBody
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
  list: CareTeamRow[] | undefined;
}

function CareTeamBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load care team"}
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
      {list.map((m) => (
        <div key={m.id} className="list-group-item p-0 pl-1">
          <span className="font-weight-normal">{m.role || "Provider"}:</span>{" "}
          <span>{m.name}</span>
        </div>
      ))}
    </div>
  );
}
