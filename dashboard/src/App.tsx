/**
 * App shell. The dashboard accepts ?patient=<FHIR uuid> in the URL so the
 * OpenEMR PHP page can iframe us with the current patient context.
 *
 * In production this whole tree is what gets dropped into the existing
 * demographics.php — no chrome (top nav, sidebar) is duplicated here, the
 * SPA only owns the *interior* of the dashboard.
 */
import { useEffect, useState } from "react";
import { MedicationsCard } from "./widgets/Medications";

export function App(): JSX.Element {
  const [patientId, setPatientId] = useState<string>("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setPatientId(params.get("patient") ?? "");
  }, []);

  if (!patientId) {
    return (
      <div className="container-fluid p-4">
        <div className="alert alert-warning mb-0">
          <strong>No patient selected.</strong> Open this page with{" "}
          <code>?patient=&lt;FHIR Patient UUID&gt;</code>.
        </div>
      </div>
    );
  }

  // The legacy dashboard uses Bootstrap's row/col layout for the cards.
  // We start with one card (Medications) and grow from here — every new
  // widget slots into another col-md-6 / col-lg-4 with no shell change.
  return (
    <div className="container-fluid p-2">
      <div className="row">
        <div className="col-md-6 col-lg-4 mb-2">
          <MedicationsCard patientId={patientId} />
        </div>
        {/* Future widgets land here:
            <div className="col-md-6 col-lg-4 mb-2"><AllergiesCard ... /></div>
            <div className="col-md-6 col-lg-4 mb-2"><ConditionsCard ... /></div>
            ... */}
      </div>
    </div>
  );
}
