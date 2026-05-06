/**
 * Immunizations card — verbatim React port of
 * templates/patient/card/immunizations.html.twig.
 *
 * Twig structure (preserved):
 *   <div class="list-group list-group-flush imz">
 *     <div class="list-group-item d-flex w-100 p-1">
 *       <a href="#" class="link" onclick="...">{{ i.cvx_text }}</a>
 *     </div>
 *   </div>
 *
 * The legacy template wires each row's <a> to a JS load_location() call
 * that opens the immunization detail. We render the same anchor with the
 * vaccine name; the click handler is a no-op for now (the immunization
 * detail page is a legacy full-page route — out of scope for the card).
 */
import { useQuery } from "@tanstack/react-query";
import { fetchImmunizations, ImmunizationRow } from "../api/fhir/immunization";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function ImmunizationsCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["immunizations", patientId],
    queryFn: ({ signal }) => fetchImmunizations(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "immunizations";

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
            Immunizations
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
            <ImmunizationsBody
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
  list: ImmunizationRow[] | undefined;
}

function ImmunizationsBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
  if (isLoading) {
    return (
      <div className="list-group list-group-flush imz">
        <div className="list-group-item d-flex w-100 p-1 text-muted">Loading…</div>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="list-group list-group-flush imz">
        <div className="list-group-item d-flex w-100 p-1 text-danger">
          {error instanceof Error ? error.message : "Failed to load immunizations"}
        </div>
      </div>
    );
  }
  if (!list || list.length === 0) {
    // Legacy "None" empty branch.
    return (
      <div className="list-group list-group-flush imz">
        <div className="list-group-item d-flex w-100">None</div>
      </div>
    );
  }
  return (
    <div className="list-group list-group-flush imz">
      {list.map((i) => (
        <div key={i.id} className="list-group-item d-flex w-100 p-1">
          <a
            href="#"
            className="link"
            onClick={(e) => e.preventDefault()}
            title={i.date ? `Administered ${i.date}` : undefined}
          >
            {i.cvx_text}
          </a>
        </div>
      ))}
    </div>
  );
}
