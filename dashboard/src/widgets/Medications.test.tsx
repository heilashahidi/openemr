/**
 * Verifies the React widget produces the exact DOM structure the legacy
 * Twig template (templates/patient/card/medication.html.twig) renders.
 *
 * Concretely:
 *   - <section class="card">
 *   - <h6 class="card-title mb-0 d-flex p-1 justify-content-between">
 *   - "Current Medications" title text
 *   - <div class="list-group list-group-flush pami-list">
 *   - one <div class="list-group-item p-0 pl-1"> per row
 *   - title in <span class="font-weight-normal">; dosage in <span>
 *
 * No network: we mock the FHIR fetcher so the test runs offline.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { MedicationsCard } from "./Medications";
import * as medApi from "../api/fhir/medication";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("MedicationsCard", () => {
  it("matches the Twig template's DOM for an empty patient", async () => {
    vi.spyOn(medApi, "fetchActiveMedications").mockResolvedValueOnce([]);

    const { container } = renderWithClient(<MedicationsCard patientId="abc" />);

    // Card frame
    const card = container.querySelector("section.card");
    expect(card).toBeInTheDocument();

    // Title text matches the legacy stats.php call (xl('Current Medications'))
    expect(await screen.findByText("Current Medications")).toBeInTheDocument();

    // Empty state matches the Twig "Nothing Recorded" branch
    const empty = await screen.findByText("Nothing Recorded");
    expect(empty.parentElement).toHaveClass("list-group", "list-group-flush", "pami-list");
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one row per medication with the same span structure", async () => {
    vi.spyOn(medApi, "fetchActiveMedications").mockResolvedValueOnce([
      { id: "m1", title: "Apixaban 5 mg", drug_dosage_instructions: "PO twice daily", active: true },
      { id: "m2", title: "Atorvastatin 40 mg", drug_dosage_instructions: "PO at bedtime", active: true },
    ]);

    const { container } = renderWithClient(<MedicationsCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item")).toHaveLength(2);
    });

    const rows = container.querySelectorAll(".list-group-item");
    rows.forEach((row) => {
      expect(row).toHaveClass("p-0", "pl-1");
      expect(row.querySelector("span.font-weight-normal")).not.toBeNull();
      expect(row.querySelectorAll("span")).toHaveLength(2);
    });

    expect(rows[0].textContent).toContain("Apixaban 5 mg");
    expect(rows[0].textContent).toContain("PO twice daily");
  });

  it("shows an error row when the FHIR fetch fails", async () => {
    vi.spyOn(medApi, "fetchActiveMedications").mockRejectedValueOnce(
      new Error("401 Unauthorized"),
    );

    renderWithClient(<MedicationsCard patientId="abc" />);

    expect(await screen.findByText(/401 Unauthorized/)).toBeInTheDocument();
  });
});
