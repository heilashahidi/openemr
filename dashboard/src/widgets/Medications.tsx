/**
 * Medications card — React port of templates/patient/card/medication.html.twig.
 *
 * The visual structure is intentionally identical to the existing Twig
 * template so the React render is pixel-indistinguishable from the PHP one.
 * If you diff the produced HTML against the legacy renderer (with auth=false,
 * btnLabel unset) the only differences are React-injected attributes
 * (data-reactroot, etc.) — the class names and DOM structure are the same.
 *
 * Original Twig (for reference):
 *
 *     <div class="list-group list-group-flush pami-list">
 *       {% for m in list %}
 *         <div class="list-group-item p-0 pl-1">
 *           <span class="font-weight-normal">{{ m.title|text }}</span>
 *           <span>{{ m.drug_dosage_instructions|text }}</span>
 *         </div>
 *       {% endfor %}
 *     </div>
 */
import { useQuery } from "@tanstack/react-query";
import { fetchActiveMedications, MedicationRow } from "../api/fhir/medication";

interface MedicationsCardProps {
  patientId: string;
  /** Mirrors the Twig `initiallyCollapsed` flag — only used to set the
      icon and the `show` class on the body. */
  initiallyCollapsed?: boolean;
}

export function MedicationsCard({
  patientId,
  initiallyCollapsed = false,
}: MedicationsCardProps): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["medications", patientId],
    queryFn: ({ signal }) => fetchActiveMedications(patientId, signal),
    staleTime: 60_000,
  });

  // The legacy template uses an HTML id like "current-medications" and a
  // collapse toggle linking to it. We do the same so any sibling CSS or
  // JS that targeted that id keeps working unchanged.
  const cardBodyId = "current-medications";

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
            Current Medications
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
            <MedicationsBody isLoading={isLoading} isError={isError} error={error} list={data} />
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
  list: MedicationRow[] | undefined;
}

function MedicationsBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load medications"}
        </div>
      </div>
    );
  }
  if (!list || list.length === 0) {
    // Match the Twig "Nothing Recorded" empty state.
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
          <span className="font-weight-normal">{m.title}</span>{" "}
          <span>{m.drug_dosage_instructions}</span>
        </div>
      ))}
    </div>
  );
}
