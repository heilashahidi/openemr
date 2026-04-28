# OpenEMR Integration Audit

**System:** OpenEMR 8.1.1-dev (`master` @ `d752953a6`)
**Verified:** 2026-04-28, via live `curl`, source inspection, and DB seeding
**Scope:** Determine whether OpenEMR's APIs support the agent in [USERS.md](USERS.md), and surface constraints that shape [ARCHITECTURE.md](ARCHITECTURE.md). Findings address the case study's required audit categories: security, performance, architecture, data quality, and compliance — tagged inline below.

## Executive Summary

OpenEMR exposes two OAuth2-protected surfaces — **FHIR R4** at `/apis/{site}/fhir/*` and a **Standard REST API** at `/apis/{site}/api/*`. The web UI is session-bound and not for agent use. The capability statement reports FHIR `4.0.1`, 34 resources.

**1. "US Core 8.0 conformance" is per-resource, not uniform.** *(Architecture; data quality)* The runtime supports US Core 3.1.1 / 7.0.0 / 8.0.0 with a global ceiling (default 8.0.0, [library/globals.inc.php:3325](library/globals.inc.php#L3325)). Each FHIR service overrides `getSupportedVersions()` independently. Captured live: Patient → `[3.1.1, 8.0.0]` (skips 7.0.0 — breaking change); Condition → includes a hardcoded `6.1.0` not gated by the global; Observation (patient-derived) → `[7.0.0, 8.0.0]`. **Two confirmed bugs:** **MedicationRequest** ([FhirMedicationRequestService.php:518-528](src/Services/FHIR/FhirMedicationRequestService.php#L518-L528)) and **AllergyIntolerance** ([FhirAllergyIntoleranceService.php:104-111](src/Services/FHIR/FhirAllergyIntoleranceService.php#L104-L111)) emit no `meta.profile` array at all — both import `VersionedProfileTrait` but never invoke its profile injector. The capability statement claims conformance; the payloads don't.

**2. Read coverage is excellent; FHIR write coverage is thin.** *(Architecture)* All 35 readable resources work. But FHIR POST/PUT exists only for Patient, Practitioner, Organization, and `DocumentReference/$docref` (CCD generation, not generic create). **No FHIR writes for Condition, Observation, Encounter, MedicationRequest, AllergyIntolerance, Appointment.** The Standard REST API closes the gap (medical_problem, allergy, medication, vital, prescription POSTs) but accepts only `user_role=users` tokens. Architectural consequence: **read via FHIR, write via Standard REST**, single user-role token.

**3. UC1 visit-reason has a real, observed path.** *(Data quality; architecture)* `form_encounter.reason` → `Encounter.reasonCode[0].text` via [FhirEncounterService.php:228-239](src/Services/FHIR/FhirEncounterService.php#L228-L239). Round-trip verified on 3 seeded encounters. Free-text only — no SNOMED/ICD coding. Agent quotes it; agent cannot route on a coded category.

**4. OAuth2 clients are disabled by default after registration.** *(Security; operational)* Dynamic Client Registration is open, but `oauth_clients.is_enabled=0` after registration — a registered client cannot obtain tokens until an admin (or a manual `UPDATE oauth_clients SET is_enabled=1`) flips the flag. A 15-minute gotcha that wedges the integration silently if missed. Tokens themselves are 1-hour Bearer.

**5. Vital-signs Observations did not surface from seeded data.** *(Data quality; flagged for re-verification)* Patient, Condition, MedicationRequest, AllergyIntolerance, Encounter, and laboratory Observations all returned with stable UUIDs suitable for citations. Vital-signs Observations did *not* surface from seeded `form_vitals` rows — additional service-layer wiring is not yet traced. **UC1's "recent vitals" tool depends on this path; flagged as a hard re-verification item before committing to the capability.**


**Most important finding.** US Core conformance is per-resource. MedicationRequest and AllergyIntolerance silently emit no `meta.profile` — caught only by reading actual responses, not the capability statement. So the agent treats `meta.profile` as advisory, not a contract.

**Missed without the audit.** (1) Both bug-resources would have broken silent profile-checking. (2) FHIR alone can't write clinical data — would have hit a wall mid-build. (3) Standard REST rejects patient-context tokens — would have forced a token-strategy refactor. (4) `reasonCode` is free text, not coded — would have over-engineered a SNOMED matcher. (5) The `is_enabled=0` registration gotcha would have blocked the first end-to-end run.

**How the plan changed.** Hybrid API posture (read FHIR, write Standard REST). Single user-role token. `meta.profile` treated as advisory. UC1 quotes reason text verbatim and lets the LLM classify, no coded matching layer. Vital-signs surfacing is a hard pre-build verification, not assumed.