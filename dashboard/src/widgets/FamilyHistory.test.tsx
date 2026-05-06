import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { FamilyHistoryCard } from "./FamilyHistory";
import * as familyApi from "../api/fhir/family";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("FamilyHistoryCard", () => {
  it("renders the empty state with the standard list-group structure", async () => {
    vi.spyOn(familyApi, "fetchFamilyHistory").mockResolvedValueOnce([]);
    const { container } = renderWithClient(<FamilyHistoryCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Family History")).toBeInTheDocument();

    const empty = await screen.findByText("Nothing Recorded");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one labeled row per family entry", async () => {
    vi.spyOn(familyApi, "fetchFamilyHistory").mockResolvedValueOnce([
      { id: "f1", relation: "Father", conditions: "Stroke (CVA)", status: "deceased age 78" },
      { id: "f2", relation: "Mother", conditions: "Type 2 diabetes", status: "alive" },
    ]);
    const { container } = renderWithClient(<FamilyHistoryCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.p-0.pl-1")).toHaveLength(2);
    });

    const rows = container.querySelectorAll(".list-group-item.p-0.pl-1");
    expect(rows[0].textContent).toContain("Father:");
    expect(rows[0].textContent).toContain("Stroke (CVA)");
    expect(rows[0].textContent).toContain("(deceased age 78)");

    expect(rows[1].textContent).toContain("Mother:");
    expect(rows[1].textContent).toContain("Type 2 diabetes");
  });

  it("shows an error row when the FHIR fetch fails", async () => {
    vi.spyOn(familyApi, "fetchFamilyHistory").mockRejectedValueOnce(
      new Error("403 Forbidden"),
    );
    renderWithClient(<FamilyHistoryCard patientId="abc" />);
    expect(await screen.findByText(/403 Forbidden/)).toBeInTheDocument();
  });
});
