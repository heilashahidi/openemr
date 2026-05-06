/**
 * Allergies card — React port of templates/patient/card/allergies.html.twig.
 *
 * Same DOM as the Twig template:
 *   <div class="list-group list-group-flush pami-list">
 *     <div class="list-group-item p-1">
 *       <div class="d-flex w-100 justify-content-between">
 *         <div class="flex-fill" title="<allergen> Reaction: <reaction> - <severity>">
 *           <allergen> (<span class="<warn classes>"><severity></span>)
 *         </div>
 *       </div>
 *     </div>
 *   </div>
 *
 * High-severity rows (severe / life_threatening_severity / fatal) get the
 * Twig-equivalent "bg-warning font-weight-bold px-1" classes on the
 * severity span — same visual highlight as the legacy renderer.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchAllergies, AllergyRow } from "../api/fhir/allergy";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function AllergiesCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["allergies", patientId],
    queryFn: ({ signal }) => fetchAllergies(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "allergies";

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
            Allergies
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
            <AllergiesBody
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
  list: AllergyRow[] | undefined;
}

function AllergiesBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load allergies"}
        </div>
      </div>
    );
  }
  if (!list || list.length === 0) {
    // Twig default empty state ("Nothing Recorded"). The legacy template
    // also has a "No Known Allergies" branch when listTouched is true; we
    // can't tell that from FHIR alone so we use the safer default.
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1">Nothing Recorded</div>
      </div>
    );
  }
  return (
    <div className="list-group list-group-flush pami-list">
      {list.map((a) => (
        <div key={a.id} className="list-group-item p-1">
          <div className="d-flex w-100 justify-content-between">
            <div
              className="flex-fill"
              title={`${a.title} Reaction: ${a.reaction_title || ""} - ${a.severity_display || ""}`.trim()}
            >
              {a.title}
              {a.severity_display && (
                <>
                  {" ("}
                  <span
                    className={
                      a.is_high_severity ? "bg-warning font-weight-bold px-1" : ""
                    }
                  >
                    {a.severity_display}
                  </span>
                  {")"}
                </>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
