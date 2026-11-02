import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Chart } from "./Chart";
import { Code } from "./Code";
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
      // A reply that only calls the tool has no text, or only whitespace; its
      // queries show as their own entries.
      return entry.text?.trim() ? (
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

// A query with a chart is a finding: a card showing the chart, with its SQL,
// table and spec a click away. Any other query is a step: one line that opens
// to its SQL and result.
function QueryRunView({ run }: { run: QueryRun }) {
  return run.spec && run.result ? (
    <FindingView run={run} spec={run.spec} result={run.result} />
  ) : (
    <StepView run={run} />
  );
}

function FindingView({ run, spec, result }: { run: QueryRun; spec: Record<string, unknown>; result: Result }) {
  return (
    <section className="finding">
      <header>
        <h3>{run.description}</h3>
        <time>{formatTime(run.at)}</time>
      </header>
      <Chart spec={spec} result={result} />
      <details>
        <summary>SQL</summary>
        <Code code={run.sql} language="sql" />
      </details>
      <details>
        <summary>Table ({result.rows.length} rows)</summary>
        <ResultTable result={result} />
      </details>
      <details>
        <summary>Spec</summary>
        <Code code={JSON.stringify(spec, null, 2)} language="json" />
      </details>
    </section>
  );
}

function StepView({ run }: { run: QueryRun }) {
  return (
    <details className={run.error ? "step failed" : "step"}>
      <summary>
        <span title={run.description}>{run.description}</span>
        <time>{formatTime(run.at)}</time>
      </summary>
      <Code code={run.sql} language="sql" />
      {run.result ? <ResultTable result={run.result} /> : <p className="error">{run.error}</p>}
      {run.spec && <Code code={JSON.stringify(run.spec, null, 2)} language="json" />}
    </details>
  );
}

function formatTime(at: string): string {
  return new Date(at).toLocaleTimeString();
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
