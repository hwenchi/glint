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
      return <p>[invalid call] {entry.error}</p>;
  }
}

function QueryRunView({ run }: { run: QueryRun }) {
  return (
    <section>
      <p>[query] {run.description}</p>
      <p>{new Date(run.at).toLocaleString()}</p>
      <pre>{run.sql}</pre>
      {run.spec && run.result && <Chart spec={run.spec} result={run.result} />}
      {run.result ? <ResultTable result={run.result} /> : <p>[error] {run.error}</p>}
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
