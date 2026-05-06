/**
 * DOM-shape parity tests for VitalsCard.
 *
 * Same approach as the other widgets: no network, mock the FHIR fetcher,
 * assert the DOM structure matches the dashboard's standard list-group
 * layout.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { VitalsCard } from "./Vitals";
import * as vitalApi from "../api/fhir/vital";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("VitalsCard", () => {
  it("renders the empty state in the standard list-group structure", async () => {
    vi.spyOn(vitalApi, "fetchRecentVitals").mockResolvedValueOnce([]);

    const { container } = renderWithClient(<VitalsCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Recent Vitals")).toBeInTheDocument();

    const empty = await screen.findByText("No vitals documented");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one row per vital with the standard two-span DOM", async () => {
    vi.spyOn(vitalApi, "fetchRecentVitals").mockResolvedValueOnce([
      { id: "v1", title: "Blood Pressure",  value_with_unit: "120/80 mmHg", date: "2026-04-21" },
      { id: "v2", title: "Heart Rate",      value_with_unit: "72 bpm",     date: "2026-04-21" },
      { id: "v3", title: "Body Weight",     value_with_unit: "70 kg",      date: "2026-04-21" },
    ]);

    const { container } = renderWithClient(<VitalsCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.p-0.pl-1")).toHaveLength(3);
    });

    const rows = container.querySelectorAll(".list-group-item.p-0.pl-1");
    rows.forEach((row) => {
      expect(row.querySelector("span.font-weight-normal")).not.toBeNull();
      expect(row.querySelectorAll("span")).toHaveLength(2);
    });

    expect(rows[0].textContent).toContain("Blood Pressure");
    expect(rows[0].textContent).toContain("120/80 mmHg");
    expect(rows[1].textContent).toContain("72 bpm");
    expect(rows[2].textContent).toContain("70 kg");
  });

  it("includes the recorded date in the row title attribute", async () => {
    vi.spyOn(vitalApi, "fetchRecentVitals").mockResolvedValueOnce([
      { id: "v4", title: "Body Temperature", value_with_unit: "98.6 °F", date: "2026-04-15" },
    ]);

    const { container } = renderWithClient(<VitalsCard patientId="abc" />);

    await waitFor(() => {
      const row = container.querySelector(".list-group-item.p-0.pl-1") as HTMLElement;
      expect(row).not.toBeNull();
      expect(row.getAttribute("title")).toBe("Recorded 2026-04-15");
    });
  });
});
