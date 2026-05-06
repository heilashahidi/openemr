/**
 * DOM-shape parity tests for ConditionsCard vs the Twig template
 * (templates/patient/card/medical_problems.html.twig).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { ConditionsCard } from "./Conditions";
import * as conditionApi from "../api/fhir/condition";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("ConditionsCard", () => {
  it("renders the Twig empty state structure", async () => {
    vi.spyOn(conditionApi, "fetchActiveConditions").mockResolvedValueOnce([]);

    const { container } = renderWithClient(<ConditionsCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Medical Problems")).toBeInTheDocument();

    const empty = await screen.findByText("Nothing Recorded");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one row per condition with the legacy py-1 px-1 padding", async () => {
    vi.spyOn(conditionApi, "fetchActiveConditions").mockResolvedValueOnce([
      { id: "c1", title: "Essential hypertension" },
      { id: "c2", title: "Hyperlipidemia" },
      { id: "c3", title: "Atrial fibrillation" },
    ]);

    const { container } = renderWithClient(<ConditionsCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.py-1.px-1")).toHaveLength(3);
    });

    const rows = container.querySelectorAll(".list-group-item.py-1.px-1");
    expect(rows[0]).toHaveTextContent("Essential hypertension");
    expect(rows[1]).toHaveTextContent("Hyperlipidemia");
    expect(rows[2]).toHaveTextContent("Atrial fibrillation");

    // Twig version has no inner span — just the title text. Verify the
    // React render also has no span/div children inside the row.
    rows.forEach((row) => {
      expect(row.children).toHaveLength(0);
    });
  });

  it("shows an error row when the FHIR fetch fails", async () => {
    vi.spyOn(conditionApi, "fetchActiveConditions").mockRejectedValueOnce(
      new Error("502 Bad Gateway"),
    );

    renderWithClient(<ConditionsCard patientId="abc" />);

    expect(await screen.findByText(/502 Bad Gateway/)).toBeInTheDocument();
  });
});
