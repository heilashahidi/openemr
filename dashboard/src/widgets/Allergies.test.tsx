/**
 * DOM-shape parity tests for AllergiesCard vs the Twig template
 * (templates/patient/card/allergies.html.twig). Same approach as the
 * Medications test — no network, mock the FHIR fetcher, assert the
 * produced DOM structure matches the legacy renderer.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { AllergiesCard } from "./Allergies";
import * as allergyApi from "../api/fhir/allergy";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("AllergiesCard", () => {
  it("renders the empty state with the Twig list-group structure", async () => {
    vi.spyOn(allergyApi, "fetchAllergies").mockResolvedValueOnce([]);

    const { container } = renderWithClient(<AllergiesCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Allergies")).toBeInTheDocument();

    const empty = await screen.findByText("Nothing Recorded");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one row per allergy with the legacy d-flex layout", async () => {
    vi.spyOn(allergyApi, "fetchAllergies").mockResolvedValueOnce([
      {
        id: "a1",
        title: "Penicillin",
        severity_al: "moderate",
        severity_display: "Moderate",
        reaction_title: "Hives",
        is_high_severity: false,
      },
      {
        id: "a2",
        title: "Sulfa drugs",
        severity_al: "severe",
        severity_display: "Severe",
        reaction_title: "Anaphylaxis",
        is_high_severity: true,
      },
    ]);

    const { container } = renderWithClient(<AllergiesCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.p-1")).toHaveLength(2);
    });

    const rows = container.querySelectorAll(".list-group-item.p-1");
    rows.forEach((row) => {
      expect(row.querySelector(".d-flex.w-100.justify-content-between")).not.toBeNull();
      expect(row.querySelector(".flex-fill")).not.toBeNull();
    });

    // First row has plain severity span (no warning highlight)
    expect(rows[0].textContent).toContain("Penicillin");
    expect(rows[0].textContent).toContain("Moderate");
    const sev0 = rows[0].querySelectorAll("span");
    expect(sev0[0]).not.toHaveClass("bg-warning");

    // Second row's severity span gets the bg-warning highlight
    expect(rows[1].textContent).toContain("Sulfa drugs");
    const sev1 = rows[1].querySelectorAll("span")[0];
    expect(sev1).toHaveClass("bg-warning", "font-weight-bold", "px-1");
  });

  it("composes the row's title attribute the same way the Twig does", async () => {
    vi.spyOn(allergyApi, "fetchAllergies").mockResolvedValueOnce([
      {
        id: "a3",
        title: "Codeine",
        severity_al: "mild",
        severity_display: "Mild",
        reaction_title: "Nausea",
        is_high_severity: false,
      },
    ]);

    const { container } = renderWithClient(<AllergiesCard patientId="abc" />);

    await waitFor(() => {
      const flex = container.querySelector(".flex-fill") as HTMLElement;
      expect(flex).not.toBeNull();
      expect(flex.getAttribute("title")).toBe("Codeine Reaction: Nausea - Mild");
    });
  });
});
