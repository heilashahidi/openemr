/**
 * Demographics card — projects the FHIR Patient resource into the
 * key-value layout the legacy "DEM" tab presents.
 *
 * The legacy Twig (templates/patient/card/demographics.html.twig)
 * defers all rendering to a PHP-side tabRow('DEM', ...) helper that
 * iterates through every demographics field stored in the database
 * and composes a multi-tab view. Porting the full tab UI is out of
 * scope for a one-card-at-a-time migration; this card mirrors the
 * "DEM" tab — the key-value display the user sees by default — using
 * Bootstrap 4.6's row/col definition-list pattern that already
 * appears elsewhere in the OpenEMR UI.
 *
 * Each row uses the standard list-group-flush + list-group-item-action
 * structure to stay visually consistent with the other dashboard cards.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchDemographics, DemographicsRow } from "../api/fhir/patient";

interface Props {
  patientId: string;
  initiallyCollapsed?: boolean;
}

export function DemographicsCard({
  patientId,
  initiallyCollapsed = false,
}: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["demographics", patientId],
    queryFn: ({ signal }) => fetchDemographics(patientId, signal),
    staleTime: 60_000,
  });

  const cardBodyId = "demographics";

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
            Demographics
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
            <DemographicsBody
              isLoading={isLoading}
              isError={isError}
              error={error}
              data={data}
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
  data: DemographicsRow | undefined;
}

function DemographicsBody({ isLoading, isError, error, data }: BodyProps): JSX.Element {
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
          {error instanceof Error ? error.message : "Failed to load demographics"}
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1">Nothing Recorded</div>
      </div>
    );
  }

  // Compose the rows we want to display in order. Empty values are
  // dropped so the card stays compact for patients with sparse records.
  const rows: Array<[string, string]> = [
    ["Name", data.name],
    ["DOB", data.dob && data.age !== null ? `${data.dob} (age ${data.age})` : data.dob],
    ["Sex", data.sex],
    ["MRN", data.mrn],
    ["Phone", data.phone],
    ["Email", data.email],
    ["Address", data.address],
  ].filter(([, v]) => v && v.toString().trim() !== "") as Array<[string, string]>;

  if (rows.length === 0) {
    return (
      <div className="list-group list-group-flush pami-list">
        <div className="list-group-item p-0 pl-1">Nothing Recorded</div>
      </div>
    );
  }

  return (
    <div className="list-group list-group-flush pami-list">
      {rows.map(([label, value]) => (
        <div key={label} className="list-group-item p-0 pl-1">
          <span className="font-weight-normal">{label}:</span>{" "}
          <span>{value}</span>
        </div>
      ))}
    </div>
  );
}
