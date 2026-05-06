import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { ImmunizationsCard } from "./Immunizations";
import * as imApi from "../api/fhir/immunization";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("ImmunizationsCard", () => {
  it("renders the empty state with the legacy .imz class wrapper", async () => {
    vi.spyOn(imApi, "fetchImmunizations").mockResolvedValueOnce([]);
    const { container } = renderWithClient(<ImmunizationsCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Immunizations")).toBeInTheDocument();

    const empty = await screen.findByText("None");
    expect(empty.parentElement).toHaveClass("list-group", "list-group-flush", "imz");
    expect(empty).toHaveClass("list-group-item", "d-flex", "w-100");
  });

  it("renders one anchored row per immunization (matches Twig DOM)", async () => {
    vi.spyOn(imApi, "fetchImmunizations").mockResolvedValueOnce([
      { id: "i1", cvx_text: "Influenza, seasonal, injectable", date: "2025-10-12" },
      { id: "i2", cvx_text: "Tdap (Tetanus, Diphtheria, Pertussis)", date: "2024-03-04" },
    ]);
    const { container } = renderWithClient(<ImmunizationsCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.d-flex.w-100.p-1")).toHaveLength(2);
    });

    const rows = container.querySelectorAll(".list-group-item.d-flex.w-100.p-1");
    rows.forEach((row) => {
      expect(row.querySelector("a.link")).not.toBeNull();
    });
    expect(rows[0].textContent).toContain("Influenza, seasonal, injectable");
    expect(rows[1].textContent).toContain("Tdap");
  });

  it("shows an error row when the FHIR fetch fails", async () => {
    vi.spyOn(imApi, "fetchImmunizations").mockRejectedValueOnce(
      new Error("503 Service Unavailable"),
    );
    renderWithClient(<ImmunizationsCard patientId="abc" />);
    expect(await screen.findByText(/503 Service Unavailable/)).toBeInTheDocument();
  });
});
