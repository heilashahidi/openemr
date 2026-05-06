/**
 * Sticky patient identity bar — name, DOB+age, sex, MRN, active status.
 *
 * Promoted out of the card grid because it's the page's identity anchor:
 * scrolls with the user, present on every screen, never collapsible.
 * Reuses the demographics fetcher so we don't double-fetch the Patient
 * resource (TanStack Query caches the result by key).
 */
import { useQuery } from "@tanstack/react-query";
import { fetchDemographics, DemographicsRow } from "../api/fhir/patient";

interface Props {
  patientId: string;
}

export function PatientHeader({ patientId }: Props): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["demographics", patientId],
    queryFn: ({ signal }) => fetchDemographics(patientId, signal),
    staleTime: 60_000,
  });

  return (
    <header className="patient-header sticky-top bg-white border-bottom shadow-sm px-3 py-2 mb-2">
      <HeaderBody isLoading={isLoading} isError={isError} error={error} row={data} />
    </header>
  );
}

interface BodyProps {
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  row: DemographicsRow | undefined;
}

function HeaderBody({ isLoading, isError, error, row }: BodyProps): JSX.Element {
  if (isLoading) {
    return <span className="text-muted">Loading patient…</span>;
  }
  if (isError) {
    return (
      <span className="text-danger">
        {error instanceof Error ? error.message : "Failed to load patient"}
      </span>
    );
  }
  if (!row) {
    return <span className="text-muted">No patient</span>;
  }
  return (
    <div className="d-flex flex-wrap align-items-center">
      <h5 className="mb-0 mr-3 font-weight-bolder">
        {row.name || "Unknown patient"}
      </h5>
      <span
        className={`badge mr-3 ${row.active ? "badge-success" : "badge-secondary"}`}
        data-testid="patient-active-badge"
      >
        {row.active ? "Active" : "Inactive"}
      </span>
      <Field label="DOB">
        {row.dob || "—"}
        {row.age !== null ? ` (${row.age})` : ""}
      </Field>
      <Field label="Sex">{row.sex || "—"}</Field>
      <Field label="MRN">{row.mrn || "—"}</Field>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <span className="mr-3">
      <span className="text-muted small mr-1">{label}:</span>
      <span className="font-weight-normal">{children}</span>
    </span>
  );
}
