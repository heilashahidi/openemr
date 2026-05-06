import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { DocumentsCard } from "./Documents";
import * as docApi from "../api/fhir/document";

function renderWithClient(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("DocumentsCard", () => {
  it("renders the empty state with the standard list-group structure", async () => {
    vi.spyOn(docApi, "fetchDocuments").mockResolvedValueOnce([]);
    const { container } = renderWithClient(<DocumentsCard patientId="abc" />);

    expect(container.querySelector("section.card")).toBeInTheDocument();
    expect(await screen.findByText("Documents")).toBeInTheDocument();

    const empty = await screen.findByText("No documents on file");
    expect(empty.parentElement).toHaveClass(
      "list-group", "list-group-flush", "pami-list",
    );
    expect(empty).toHaveClass("list-group-item", "p-0", "pl-1");
  });

  it("renders one row per document with link when href is present", async () => {
    vi.spyOn(docApi, "fetchDocuments").mockResolvedValueOnce([
      {
        id: "d1",
        title: "p02-whitaker-intake.pdf",
        category: "Patient Information",
        date: "2026-04-21",
        href: "https://files.example/d/d1",
      },
      {
        id: "d2",
        title: "p02-whitaker-cbc.pdf",
        category: "Lab Report",
        date: "2026-04-21",
        href: "",
      },
    ]);
    const { container } = renderWithClient(<DocumentsCard patientId="abc" />);

    await waitFor(() => {
      expect(container.querySelectorAll(".list-group-item.p-0.pl-1")).toHaveLength(2);
    });

    const rows = container.querySelectorAll(".list-group-item.p-0.pl-1");

    // First row has a clickable link
    const link0 = rows[0].querySelector("a.link") as HTMLAnchorElement;
    expect(link0).not.toBeNull();
    expect(link0.href).toBe("https://files.example/d/d1");
    expect(link0.textContent).toBe("p02-whitaker-intake.pdf");
    expect(rows[0].textContent).toContain("Patient Information");

    // Second row has no link (no href provided) — falls back to plain span
    expect(rows[1].querySelector("a.link")).toBeNull();
    expect(rows[1].textContent).toContain("p02-whitaker-cbc.pdf");
    expect(rows[1].textContent).toContain("Lab Report");
  });

  it("composes the row title attribute from category + upload date", async () => {
    vi.spyOn(docApi, "fetchDocuments").mockResolvedValueOnce([
      {
        id: "d3",
        title: "discharge-summary.pdf",
        category: "Medical Record",
        date: "2026-03-18",
        href: "",
      },
    ]);
    const { container } = renderWithClient(<DocumentsCard patientId="abc" />);
    await waitFor(() => {
      const row = container.querySelector(".list-group-item.p-0.pl-1") as HTMLElement;
      expect(row).not.toBeNull();
      expect(row.getAttribute("title")).toBe("Medical Record · Uploaded 2026-03-18");
    });
  });
});
