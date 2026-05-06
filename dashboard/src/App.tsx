/**
 * App shell. The dashboard accepts ?patient=<FHIR uuid> in the URL so the
 * OpenEMR PHP page can iframe us with the current patient context.
 *
 * In production this whole tree is what gets dropped into the existing
 * demographics.php — no chrome (top nav, sidebar) is duplicated here, the
 * SPA only owns the *interior* of the dashboard.
 */
import { useEffect, useState } from "react";
import { AllergiesCard } from "./widgets/Allergies";
import { CareTeamCard } from "./widgets/CareTeam";
import { ConditionsCard } from "./widgets/Conditions";
import { DemographicsCard } from "./widgets/Demographics";
import { DocumentsCard } from "./widgets/Documents";
import { EncountersCard } from "./widgets/Encounters";
import { FamilyHistoryCard } from "./widgets/FamilyHistory";
import { ImmunizationsCard } from "./widgets/Immunizations";
import { InsuranceCard } from "./widgets/Insurance";
import { LabsCard } from "./widgets/Labs";
import { MedicationsCard } from "./widgets/Medications";
import { PatientHeader } from "./widgets/PatientHeader";
import { VitalsCard } from "./widgets/Vitals";

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
      <PatientHeader patientId={patientId} />
      <div className="row">
        {/* Demographics is conventionally the first card on the page. */}
        <div className="col-md-6 col-lg-4 mb-2">
          <DemographicsCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <MedicationsCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <AllergiesCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <ConditionsCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <EncountersCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <LabsCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <VitalsCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <ImmunizationsCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <FamilyHistoryCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <CareTeamCard patientId={patientId} />
        </div>
        <div className="col-md-6 col-lg-4 mb-2">
          <DocumentsCard patientId={patientId} />
        </div>
        {/* Insurance is wider — give it a half-width column so the
            tab/policy-details layout has room to breathe. */}
        <div className="col-md-12 col-lg-8 mb-2">
          <InsuranceCard patientId={patientId} />
        </div>
      </div>
    </div>
  );
}
