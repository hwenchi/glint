import { memo } from "react";
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

// An entry never changes once it arrives, so it renders once, not on every keystroke.
export const EntryView = memo(function EntryView({ entry }: { entry: Entry }) {
  switch (entry.kind) {
    case "user":
      return (
        <div className="user">
          <Markdown text={entry.text} />
        </div>
      );
    case "assistant": {
      // A reply that only calls the tool has no text, or only whitespace; its
      // queries show as their own entries, after its model.
      const hasText = Boolean(entry.text?.trim());
      return hasText || entry.model ? (
        <div className="assistant">
          {entry.model && (
            <p className="byline">
              <span className="model">{entry.model}</span>
              {entry.usage && (
                <span className="tokens">
                  <span title="Tokens sent to the model">
                    <Arrow up />
                    {entry.usage.prompt_tokens.toLocaleString()}
                  </span>
                  <span title="Tokens the model wrote">
                    <Arrow up={false} />
                    {entry.usage.completion_tokens.toLocaleString()}
                  </span>
                </span>
              )}
            </p>
          )}
          {entry.reasoning?.trim() && (
            <details className="reasoning">
              <summary>Reasoning</summary>
              <div>
                <Markdown text={entry.reasoning} />
              </div>
            </details>
          )}
          {hasText && <Markdown text={entry.text!} />}
        </div>
      ) : null;
    }
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
});

// The model's Markdown. Links and images become their text: a click or a load would send a request out.
function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      disallowedElements={["a", "img"]}
      unwrapDisallowed
      components={MARKDOWN_COMPONENTS}
    >
      {text}
    </ReactMarkdown>
  );
}

// Drawn rather than typed: the bundled fonts may not have arrows.
function Arrow({ up }: { up: boolean }) {
  return (
    <svg className="arrow" viewBox="0 0 8 14" aria-hidden="true">
      <path d={up ? "M1 1h6M4 13V4M1 7l3-3 3 3" : "M1 13h6M4 1v9M1 7l3 3 3-3"} />
    </svg>
  );
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
      {run.result ? <ResultTable result={run.result} /> : <pre className="error">{run.error}</pre>}
      {run.spec && <Code code={JSON.stringify(run.spec, null, 2)} language="json" />}
    </details>
  );
}

function formatTime(at: string): string {
  return new Date(at).toLocaleTimeString();
}

// Columns per printed table: on paper, a wide result prints as stacked tables
// of a few columns each. CSS can't tell how many fit, so the number is fixed.
const PRINT_COLUMNS = 5;

function ResultTable({ result }: { result: Result }) {
  const all = result.columns.map((_, i) => i);
  return (
    <>
      <div className="table-scroll screen-only">
        <Table result={result} columns={all} />
      </div>
      <div className="print-only">
        {chunks(all, PRINT_COLUMNS).map((columns, i) => (
          <Table key={i} result={result} columns={columns} />
        ))}
      </div>
    </>
  );
}

function chunks<T>(items: T[], size: number): T[][] {
  const result = [];
  for (let i = 0; i < items.length; i += size) {
    result.push(items.slice(i, i + size));
  }
  return result;
}

// The result's columns at the given indexes, in that order.
function Table({ result, columns }: { result: Result; columns: number[] }) {
  return (
    <table>
      <thead>
        <tr>
          {columns.map((j) => (
            <th key={j}>{result.columns[j]}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {result.rows.map((row, i) => (
          <tr key={i}>
            {columns.map((j) => (
              <td key={j}>{cell(row[j])}</td>
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
