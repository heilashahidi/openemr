/**
 * DOM-shape parity tests for LabsCard.
 *
 * Verifies the React widget produces the same DOM patterns the other
 * dashboard cards use: card_base wrapper, list-group-flush rows,
 * font-weight-normal title span, and bg-warning highlight for abnormal
 * results (mirrors how the allergy card flags severe entries).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { LabsCard } from "./Labs";
import * as labApi from "../api/fhir/lab";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("LabsCard", () => {
  it("renders the empty state with the standard list-group structure", async () => {
    vi.spyOn(labApi, "fetchRecentLabs").mockResolvedValueOnce([]);

    const { container } = renderWithClient(<LabsCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Recent Labs")).toBeInTheDocument();

    const empty = await screen.findByText("No laboratory results documented");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one row per lab and highlights abnormal flags", async () => {
    vi.spyOn(labApi, "fetchRecentLabs").mockResolvedValueOnce([
      {
        id: "l1",
        title: "Hemoglobin A1c",
        value_with_unit: "8.2 %",
        flag: "H",
        date: "2026-04-21",
        is_abnormal: true,
      },
      {
        id: "l2",
        title: "Sodium",
        value_with_unit: "138 mmol/L",
        flag: "",
        date: "2026-04-21",
        is_abnormal: false,
      },
    ]);

    const { container } = renderWithClient(<LabsCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.p-0.pl-1")).toHaveLength(2);
    });

    const rows = container.querySelectorAll(".list-group-item.p-0.pl-1");
    rows.forEach((row) => {
      expect(row.querySelector("span.font-weight-normal")).not.toBeNull();
      expect(row.querySelectorAll("span")).toHaveLength(2);
    });

    // Abnormal lab gets the bg-warning highlight on its value span;
    // normal lab does not.
    const valueSpan0 = rows[0].querySelectorAll("span")[1];
    const valueSpan1 = rows[1].querySelectorAll("span")[1];
    expect(valueSpan0).toHaveClass("bg-warning", "font-weight-bold", "px-1");
    expect(valueSpan1).not.toHaveClass("bg-warning");

    // Flag display: "(H)" appears for abnormal, no flag for normal.
    expect(rows[0].textContent).toContain("8.2 %");
    expect(rows[0].textContent).toContain("(H)");
    expect(rows[1].textContent).toContain("138 mmol/L");
    expect(rows[1].textContent).not.toContain("(");
  });

  it("includes the collection date in the row title attribute", async () => {
    vi.spyOn(labApi, "fetchRecentLabs").mockResolvedValueOnce([
      {
        id: "l3",
        title: "Glucose",
        value_with_unit: "108 mg/dL",
        flag: "H",
        date: "2026-04-15",
        is_abnormal: true,
      },
    ]);

    const { container } = renderWithClient(<LabsCard patientId="abc" />);

    await waitFor(() => {
      const row = container.querySelector(".list-group-item.p-0.pl-1") as HTMLElement;
      expect(row).not.toBeNull();
      expect(row.getAttribute("title")).toBe("Collected 2026-04-15");
    });
  });
});
