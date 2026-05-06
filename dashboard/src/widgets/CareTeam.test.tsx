import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { CareTeamCard } from "./CareTeam";
import * as ctApi from "../api/fhir/careteam";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("CareTeamCard", () => {
  it("renders the empty state with the standard list-group structure", async () => {
    vi.spyOn(ctApi, "fetchCareTeam").mockResolvedValueOnce([]);
    const { container } = renderWithClient(<CareTeamCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Care Team")).toBeInTheDocument();

    const empty = await screen.findByText("Nothing Recorded");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one row per participant with role + name spans", async () => {
    vi.spyOn(ctApi, "fetchCareTeam").mockResolvedValueOnce([
      { id: "ct1_0", name: "Dr. Anjali Rao", role: "Primary Care Physician" },
      { id: "ct1_1", name: "Dr. Marcus Lee", role: "Cardiologist" },
    ]);
    const { container } = renderWithClient(<CareTeamCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.p-0.pl-1")).toHaveLength(2);
    });

    const rows = container.querySelectorAll(".list-group-item.p-0.pl-1");
    rows.forEach((row) => {
      expect(row.querySelector("span.font-weight-normal")).not.toBeNull();
      expect(row.querySelectorAll("span")).toHaveLength(2);
    });

    expect(rows[0].textContent).toContain("Primary Care Physician:");
    expect(rows[0].textContent).toContain("Dr. Anjali Rao");
    expect(rows[1].textContent).toContain("Cardiologist:");
    expect(rows[1].textContent).toContain("Dr. Marcus Lee");
  });

  it("falls back to 'Provider' when a participant has no role", async () => {
    vi.spyOn(ctApi, "fetchCareTeam").mockResolvedValueOnce([
      { id: "ct1_0", name: "Dr. Solo", role: "" },
    ]);
    const { container } = renderWithClient(<CareTeamCard patientId="abc" />);

    await waitFor(() => {
      const row = container.querySelector(".list-group-item.p-0.pl-1") as HTMLElement;
      expect(row).not.toBeNull();
      expect(row.textContent).toContain("Provider:");
      expect(row.textContent).toContain("Dr. Solo");
    });
  });
});
