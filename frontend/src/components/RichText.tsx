// Renders the small amount of formatting used in answers and policy text:
// paragraphs, "- " bullet lists, **bold**, and markdown pipe tables (policy §3).
// Deliberately tiny, so the frontend needs no markdown library.
import type { ReactNode } from "react";

function inline(text: string): ReactNode[] {
  // Split on **bold** markers: odd parts are bold.
  return text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 === 1 ? <strong key={i}>{part}</strong> : part));
}

function PipeTable({ lines }: { lines: string[] }) {
  const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  const [header, ...rest] = lines;
  const body = rest.filter((line) => !/^\|?\s*:?-{2,}/.test(line.trim())); // drop the |---| separator row
  return (
    <table className="mini-table">
      <thead>
        <tr>{cells(header).map((c, i) => <th key={i}>{inline(c)}</th>)}</tr>
      </thead>
      <tbody>
        {body.map((line, r) => (
          <tr key={r}>{cells(line).map((c, i) => <td key={i}>{inline(c)}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

export function RichText({ text }: { text: string }) {
  const blocks = text.trim().split(/\n\s*\n/);
  return (
    <div className="rich-text">
      {blocks.map((block, b) => {
        const lines = block.split("\n").filter((line) => line.trim() !== "");
        if (lines.length > 0 && lines.every((line) => line.trim().startsWith("|"))) {
          return <PipeTable key={b} lines={lines} />;
        }
        if (lines.length > 0 && lines.every((line) => /^\s*[-•*]\s+/.test(line))) {
          return (
            <ul key={b}>
              {lines.map((line, i) => <li key={i}>{inline(line.replace(/^\s*[-•*]\s+/, ""))}</li>)}
            </ul>
          );
        }
        return (
          <p key={b}>
            {lines.map((line, i) => (
              <span key={i}>
                {i > 0 && <br />}
                {inline(line)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
