import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Chart } from "./Chart";
import type { Entry, QueryRun, Result } from "./types";

// Tables in replies scroll sideways inside the column, like result tables.
const MARKDOWN_COMPONENTS: Components = {
  table: ({ node, ...props }) => (
    <div className="table-scroll">
      <table {...props} />
    </div>
  ),
};

export function EntryView({ entry }: { entry: Entry }) {
  switch (entry.kind) {
    case "user":
      return <p className="user">{entry.text}</p>;
    case "assistant":
      // A reply that only calls the tool has no text; its queries show as their own entries.
      return entry.text ? (
        <div className="assistant">
          {/* Links and images become their text: a click or a load would send a request out. */}
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            disallowedElements={["a", "img"]}
            unwrapDisallowed
            components={MARKDOWN_COMPONENTS}
          >
            {entry.text}
          </ReactMarkdown>
        </div>
      ) : null;
    case "query_result":
      return <QueryRunView run={entry.run} />;
    case "invalid_call":
      return (
        <details className="invalid-call">
          <summary>Invalid call</summary>
          <p>{entry.error}</p>
        </details>
      );
  }
}

// A query with a chart is a finding: a card with its SQL and table open beside
// the chart. Any other query is a step: a compact line with everything collapsed.
function QueryRunView({ run }: { run: QueryRun }) {
  const charted = Boolean(run.spec && run.result);
  return (
    <section className={charted ? "finding" : run.error ? "step failed" : "step"}>
      <header>
        <h3>{run.description}</h3>
        <time>{new Date(run.at).toLocaleTimeString()}</time>
      </header>
      {run.spec && (
        <details>
          <summary>Spec</summary>
          <pre>{JSON.stringify(run.spec, null, 2)}</pre>
        </details>
      )}
      {run.spec && run.result && <Chart spec={run.spec} result={run.result} />}
      <details open={charted}>
        <summary>SQL</summary>
        <pre>{run.sql}</pre>
      </details>
      {run.result ? (
        <details open={charted}>
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
    <div className="table-scroll">
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
    </div>
  );
}

function cell(value: unknown): string {
  if (value === null) return "NULL";
  if (typeof value === "object") return JSON.stringify(value); // arrays and JSON columns
  return String(value);
}
