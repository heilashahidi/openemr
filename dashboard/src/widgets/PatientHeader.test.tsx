import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { PatientHeader } from "./PatientHeader";
import * as patientApi from "../api/fhir/patient";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("PatientHeader", () => {
  it("renders identity fields and an Active badge", async () => {
    vi.spyOn(patientApi, "fetchDemographics").mockResolvedValueOnce({
      name: "Margaret Chen",
      dob: "1962-03-14",
      age: 64,
      sex: "Female",
      address: "",
      phone: "",
      email: "",
      mrn: "MRN12345",
      active: true,
    });
    const { container } = renderWithClient(<PatientHeader patientId="abc" />);

    await waitFor(() => {
      expect(screen.getByText("Margaret Chen")).toBeInTheDocument();
    });

    expect(container.querySelector("header.patient-header")).toBeInTheDocument();
    expect(container.querySelector("header.sticky-top")).toBeInTheDocument();

    const badge = screen.getByTestId("patient-active-badge");
    expect(badge).toHaveTextContent("Active");
    expect(badge).toHaveClass("badge-success");

    expect(screen.getByText(/DOB:/)).toBeInTheDocument();
    expect(screen.getByText(/1962-03-14 \(64\)/)).toBeInTheDocument();
    expect(screen.getByText(/Sex:/)).toBeInTheDocument();
    expect(screen.getByText("Female")).toBeInTheDocument();
    expect(screen.getByText(/MRN:/)).toBeInTheDocument();
    expect(screen.getByText("MRN12345")).toBeInTheDocument();
  });

  it("renders Inactive badge when active=false", async () => {
    vi.spyOn(patientApi, "fetchDemographics").mockResolvedValueOnce({
      name: "Test Patient",
      dob: "",
      age: null,
      sex: "",
      address: "",
      phone: "",
      email: "",
      mrn: "",
      active: false,
    });
    renderWithClient(<PatientHeader patientId="abc" />);

    const badge = await screen.findByTestId("patient-active-badge");
    expect(badge).toHaveTextContent("Inactive");
    expect(badge).toHaveClass("badge-secondary");
  });
});
