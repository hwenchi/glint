import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Chart } from "./Chart";
import type { Entry, QueryRun, Result } from "./types";

export function EntryView({ entry }: { entry: Entry }) {
  switch (entry.kind) {
    case "user":
      return <p>[user] {entry.text}</p>;
    case "assistant":
      // A reply that only calls the tool has no text; its queries show as their own entries.
      return entry.text ? (
        <div>
          [assistant]
          {/* Links and images become their text: a click or a load would send a request out. */}
          <ReactMarkdown remarkPlugins={[remarkGfm]} disallowedElements={["a", "img"]} unwrapDisallowed>
            {entry.text}
          </ReactMarkdown>
        </div>
      ) : null;
    case "query_result":
      return <QueryRunView run={entry.run} />;
    case "invalid_call":
      return (
        <details>
          <summary>Invalid call</summary>
          <p>{entry.error}</p>
        </details>
      );
  }
}

function QueryRunView({ run }: { run: QueryRun }) {
  return (
    <section>
      <p>[query] {run.description}</p>
      <p>{new Date(run.at).toLocaleString()}</p>
      <details>
        <summary>SQL</summary>
        <pre>{run.sql}</pre>
      </details>
      {run.spec && run.result && <Chart spec={run.spec} result={run.result} />}
      {run.result ? (
        <details>
          <summary>Table ({run.result.rows.length} rows)</summary>
          <ResultTable result={run.result} />
        </details>
      ) : (
        <details>
          <summary>Error</summary>
          <p>{run.error}</p>
        </details>
      )}
    </section>
  );
}

function ResultTable({ result }: { result: Result }) {
  return (
    <table>
      <thead>
        <tr>
          {result.columns.map((column, i) => (
            <th key={i}>{column}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {result.rows.map((row, i) => (
          <tr key={i}>
            {row.map((value, j) => (
              <td key={j}>{cell(value)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function cell(value: unknown): string {
  if (value === null) return "NULL";
  if (typeof value === "object") return JSON.stringify(value); // arrays and JSON columns
  return String(value);
}
