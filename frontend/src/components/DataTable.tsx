// A plain table for evidence rows. Columns come from the rows themselves,
// unless a column list is given. Numbers are right-aligned and formatted.
import type { Row } from "../lib/types";
import { columnLabel, formatCell, isNumericColumn } from "../lib/format";

interface Props {
  rows: Row[];
  columns?: string[];
  caption?: string;
}

export function DataTable({ rows, columns, caption }: Props) {
  if (rows.length === 0) return <p className="muted">No rows.</p>;
  const keys = columns ?? Object.keys(rows[0]);
  return (
    <div className="table-scroll">
      <table className="data-table">
        {caption && <caption>{caption}</caption>}
        <thead>
          <tr>
            {keys.map((key) => (
              <th key={key} className={isNumericColumn(key, rows) ? "num" : undefined}>
                {columnLabel(key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {keys.map((key) => (
                <td key={key} className={typeof row[key] === "number" ? "num" : undefined}>
                  {formatCell(key, row[key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
