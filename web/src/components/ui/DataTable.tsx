import type { ReactNode } from "react";
import { colors, fontFamily, space, typeScale } from "./tokens";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  sortable?: boolean;
  render: (row: T) => ReactNode;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  sortKey?: string | null;
  sortDirection?: "asc" | "desc";
  onSort?: (key: string) => void;
}

const headerCellStyle = {
  padding: `${space.sm}px ${space.md}px`,
  borderBottom: `1px solid ${colors.border}`,
  color: colors.textMuted,
  fontSize: typeScale.xs,
  textTransform: "uppercase" as const,
  letterSpacing: 0.4,
};

function cellStyle(align: "left" | "right" | undefined) {
  return {
    padding: `${space.sm}px ${space.md}px`,
    borderBottom: `1px solid ${colors.border}`,
    textAlign: align === "right" ? ("right" as const) : ("left" as const),
  };
}

/** Renders rows whose interactive element (a real Link/button passed in via
 * a column's render fn) is what's keyboard-focusable — DataTable itself
 * never attaches a click handler to the <tr>, since a div/tr onClick isn't
 * reachable by keyboard. */
export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  sortKey,
  sortDirection,
  onSort,
}: DataTableProps<T>) {
  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily,
        fontSize: typeScale.base,
        color: colors.text,
      }}
    >
      <thead>
        <tr>
          {columns.map((col) => (
            <th
              key={col.key}
              style={{
                ...headerCellStyle,
                textAlign: col.align === "right" ? "right" : "left",
              }}
              aria-sort={
                col.sortable
                  ? sortKey === col.key
                    ? sortDirection === "asc"
                      ? "ascending"
                      : "descending"
                    : "none"
                  : undefined
              }
            >
              {col.sortable ? (
                <button
                  onClick={() => onSort?.(col.key)}
                  style={{
                    background: "none",
                    border: "none",
                    color: sortKey === col.key ? colors.text : colors.textMuted,
                    cursor: "pointer",
                    font: "inherit",
                    textTransform: "inherit",
                    letterSpacing: "inherit",
                    padding: 0,
                  }}
                >
                  {col.header}
                  {sortKey === col.key ? (sortDirection === "asc" ? " ▲" : " ▼") : ""}
                </button>
              ) : (
                col.header
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr
            key={getRowKey(row)}
            style={{ background: i % 2 === 1 ? colors.surface : "transparent" }}
          >
            {columns.map((col) => (
              <td key={col.key} style={cellStyle(col.align)}>
                {col.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
