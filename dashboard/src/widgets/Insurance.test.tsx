/**
 * DOM-shape parity tests for InsuranceCard.
 *
 * Asserts that the React widget produces the same structural DOM the
 * legacy Twig template (templates/patient/card/insurance.html.twig)
 * generates: nav-tabs at the top, tab-content beneath, and inside each
 * pane the same two-column .list-group-flush layout for the policy
 * details.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { InsuranceCard } from "./Insurance";
import * as coverageApi from "../api/fhir/coverage";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("InsuranceCard", () => {
  it("renders the empty state when the patient has no coverages", async () => {
    vi.spyOn(coverageApi, "fetchCoverages").mockResolvedValueOnce([]);

    renderWithClient(<InsuranceCard patientId="abc" />);

    expect(await screen.findByText("Nothing Recorded")).toBeInTheDocument();
  });

  it("renders the legacy nav-tabs + policy-details list-group layout", async () => {
    vi.spyOn(coverageApi, "fetchCoverages").mockResolvedValueOnce([
      {
        id: "c1",
        type: "primary",
        insurer_name: "BlueCross BlueShield of California PPO",
        plan_name: "PPO 2024",
        policy_number: "BCB-XX-887421",
        group_number: "GRP-44321",
        copay: "$25",
        accept_assignment: "TRUE",
        date: "2024-01-01",
        date_end: "",
      },
    ]);

    const { container } = renderWithClient(<InsuranceCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelector("ul.nav.nav-tabs.insurance-nav-tabs")).not.toBeNull();
    });

    // Tab list contains the active "Primary" tab
    const activeTab = container.querySelector(".nav-link.active");
    expect(activeTab).toHaveTextContent("Primary");

    // Two-column policy details block — matches the legacy
    // <div class="d-flex justify-content-between policy-details">.
    const policyDetails = container.querySelector(".policy-details");
    expect(policyDetails).not.toBeNull();
    const lgs = policyDetails!.querySelectorAll(".list-group.list-group-flush");
    expect(lgs).toHaveLength(2);

    // Expected fields in their expected positions
    expect(container.textContent).toContain("Plan Name:");
    expect(container.textContent).toContain("PPO 2024");
    expect(container.textContent).toContain("Policy Number:");
    expect(container.textContent).toContain("BCB-XX-887421");
    expect(container.textContent).toContain("Copay:");
    expect(container.textContent).toContain("$25");
    expect(container.textContent).toContain("Accepts Assignment:");
    expect(container.textContent).toContain("Yes");
  });

  it("switches active pane when a different tab is clicked", async () => {
    vi.spyOn(coverageApi, "fetchCoverages").mockResolvedValueOnce([
      {
        id: "c1", type: "primary",
        insurer_name: "Aetna", plan_name: "Aetna PPO",
        policy_number: "P1", group_number: "G1",
        copay: "", accept_assignment: "",
        date: "", date_end: "",
      },
      {
        id: "c2", type: "secondary",
        insurer_name: "Medicare Part B", plan_name: "Part B",
        policy_number: "M1", group_number: "",
        copay: "", accept_assignment: "",
        date: "", date_end: "",
      },
    ]);

    const { container } = renderWithClient(<InsuranceCard patientId="abc" />);

    // Wait for the Primary tab to render
    await waitFor(() => {
      expect(container.textContent).toContain("Aetna PPO");
    });
    expect(container.textContent).not.toContain("Part B");

    // Click the Secondary tab
    const secondaryTab = await screen.findByText("Secondary");
    fireEvent.click(secondaryTab);

    await waitFor(() => {
      expect(container.textContent).toContain("Part B");
    });
  });
});
