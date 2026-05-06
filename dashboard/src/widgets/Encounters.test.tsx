/**
 * DOM-shape parity tests for EncountersCard.
 *
 * No exact Twig template to mirror — the legacy summary page does not
 * have an encounter card. We assert the React widget produces the same
 * card_base.html.twig + medication.html.twig DOM patterns so it slots
 * cleanly into the dashboard alongside the other ports.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { EncountersCard } from "./Encounters";
import * as encounterApi from "../api/fhir/encounter";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("EncountersCard", () => {
  it("renders the empty state in the standard list-group structure", async () => {
    vi.spyOn(encounterApi, "fetchRecentEncounters").mockResolvedValueOnce([]);

    const { container } = renderWithClient(<EncountersCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Recent Encounters")).toBeInTheDocument();

    const empty = await screen.findByText("Nothing Recorded");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one row per encounter with date + reason spans", async () => {
    vi.spyOn(encounterApi, "fetchRecentEncounters").mockResolvedValueOnce([
      { id: "e1", date: "2026-04-22", reason: "Annual physical" },
      { id: "e2", date: "2026-01-15", reason: "Diabetes follow-up" },
    ]);

    const { container } = renderWithClient(<EncountersCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.p-0.pl-1")).toHaveLength(2);
    });

    const rows = container.querySelectorAll(".list-group-item.p-0.pl-1");
    rows.forEach((row) => {
      expect(row.querySelector("span.font-weight-normal")).not.toBeNull();
      expect(row.querySelectorAll("span")).toHaveLength(2);
    });

    expect(rows[0].textContent).toContain("2026-04-22");
    expect(rows[0].textContent).toContain("Annual physical");
    expect(rows[1].textContent).toContain("2026-01-15");
    expect(rows[1].textContent).toContain("Diabetes follow-up");
  });

  it("shows an error row when the FHIR fetch fails", async () => {
    vi.spyOn(encounterApi, "fetchRecentEncounters").mockRejectedValueOnce(
      new Error("503 Service Unavailable"),
    );

    renderWithClient(<EncountersCard patientId="abc" />);

    expect(await screen.findByText(/503 Service Unavailable/)).toBeInTheDocument();
  });
});
