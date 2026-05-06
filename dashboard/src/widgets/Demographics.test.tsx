/**
 * DOM-shape parity tests for DemographicsCard.
 *
 * The legacy demographics.html.twig delegates to a PHP-side
 * tabRow('DEM', ...) helper — there's no static Twig HTML to mirror.
 * What we CAN assert is that the React card uses the same card_base
 * frame and the standard list-group-flush + p-0 pl-1 row pattern as
 * the other ports, so visually it slots in alongside them.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { DemographicsCard } from "./Demographics";
import * as patientApi from "../api/fhir/patient";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("DemographicsCard", () => {
  it("renders the card frame and the Demographics title", async () => {
    vi.spyOn(patientApi, "fetchDemographics").mockResolvedValueOnce({
      name: "James Whitaker",
      dob: "1958-11-03",
      age: 67,
      sex: "Male",
      address: "812 Rio Grande Blvd NW, Albuquerque NM 87107",
      phone: "(505) 555-0193",
      email: "",
      mrn: "100011",
    });

    const { container } = renderWithClient(<DemographicsCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Demographics")).toBeInTheDocument();
  });

  it("emits one labeled row per non-empty field", async () => {
    vi.spyOn(patientApi, "fetchDemographics").mockResolvedValueOnce({
      name: "James Whitaker",
      dob: "1958-11-03",
      age: 67,
      sex: "Male",
      address: "812 Rio Grande Blvd NW, Albuquerque NM 87107",
      phone: "(505) 555-0193",
      email: "",
      mrn: "100011",
    });

    const { container } = renderWithClient(<DemographicsCard patientId="abc" />);

    await waitFor(() => {
      // 6 of the 7 candidate rows are populated (email is empty); the
      // empty-value filter should keep email out.
      expect(container.querySelectorAll(".list-group-item.p-0.pl-1")).toHaveLength(6);
    });

    const rows = container.querySelectorAll(".list-group-item.p-0.pl-1");
    rows.forEach((row) => {
      expect(row.querySelector("span.font-weight-normal")).not.toBeNull();
      expect(row.querySelectorAll("span")).toHaveLength(2);
    });

    expect(rows[0].textContent).toContain("Name:");
    expect(rows[0].textContent).toContain("James Whitaker");
    // DOB row composes "<dob> (age <n>)"
    const dobRow = Array.from(rows).find((r) => r.textContent?.startsWith("DOB:"));
    expect(dobRow?.textContent).toContain("1958-11-03 (age 67)");
  });

  it("shows the empty state when every field is blank", async () => {
    vi.spyOn(patientApi, "fetchDemographics").mockResolvedValueOnce({
      name: "", dob: "", age: null, sex: "", address: "", phone: "", email: "", mrn: "",
    });

    const { container } = renderWithClient(<DemographicsCard patientId="abc" />);

    const empty = await screen.findByText("Nothing Recorded");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(container.querySelectorAll(".list-group-item")).toHaveLength(1);
  });
});
