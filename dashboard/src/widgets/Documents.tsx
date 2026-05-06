/**
 * Documents card — modeled on the immunization card's anchored-row
 * pattern (each document is a clickable filename link). No exact legacy
 * Twig template exists for the patient summary; documents are managed
 * via a separate tree panel. This widget exposes recent DocumentReferences
 * inline so attached intake forms / lab PDFs are visible at a glance.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchDocuments, DocumentRow } from "../api/fhir/document";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function DocumentsCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["documents", patientId],
    queryFn: ({ signal }) => fetchDocuments(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "documents";

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
            Documents
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
            <DocumentsBody
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
  list: DocumentRow[] | undefined;
}

function DocumentsBody({ isLoading, isError, error, list }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load documents"}
        </div>
      </div>
    );
  }
  if (!list || list.length === 0) {
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1">No documents on file</div>
      </div>
    );
  }
  return (
    <div className="list-group list-group-flush pami-list">
      {list.map((d) => (
        <div
          key={d.id}
          className="list-group-item p-0 pl-1"
          title={[d.category, d.date && `Uploaded ${d.date}`].filter(Boolean).join(" · ")}
        >
          {d.href ? (
            <a className="link" href={d.href} target="_blank" rel="noreferrer">
              {d.title}
            </a>
          ) : (
            <span>{d.title}</span>
          )}
          {d.category && (
            <>
              {" "}
              <span className="text-muted small">— {d.category}</span>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
