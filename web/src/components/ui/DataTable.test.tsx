import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataTable, type DataTableColumn } from "./DataTable";

afterEach(cleanup);

interface Row {
  id: string;
  name: string;
  count: number;
}

const columns: DataTableColumn<Row>[] = [
  { key: "name", header: "Name", render: (r) => r.name },
  { key: "count", header: "Count", align: "right", sortable: true, render: (r) => r.count },
];

const rows: Row[] = [
  { id: "1", name: "First", count: 3 },
  { id: "2", name: "Second", count: 7 },
];

describe("DataTable", () => {
  it("renders headers and row cells", () => {
    render(<DataTable columns={columns} rows={rows} getRowKey={(r) => r.id} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("calls onSort with the column key when a sortable header is clicked", () => {
    const onSort = vi.fn();
    render(
      <DataTable columns={columns} rows={rows} getRowKey={(r) => r.id} onSort={onSort} />
    );
    fireEvent.click(screen.getByRole("button", { name: /count/i }));
    expect(onSort).toHaveBeenCalledWith("count");
  });
});
