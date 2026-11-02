import { useEffect, useRef, useState } from "react";
import { loader } from "vega";
import embed, { type VisualizationSpec } from "vega-embed";
import { expressionInterpreter } from "vega-interpreter";

import type { Result } from "./types";

// Vega asks its loader before loading data or images and before following
// links. Refusing every URL here means no spec can make a request.
const refusingLoader = loader();
refusingLoader.sanitize = () => Promise.reject(new Error("URLs are not allowed"));
refusingLoader.load = () => Promise.reject(new Error("URLs are not allowed"));

const OPTIONS = {
  mode: "vega-lite" as const,
  actions: false, // no export menu: its "Open in Vega Editor" would send the spec and data off-site
  ast: true, // expressions are evaluated by the interpreter, not compiled with eval, which the CSP forbids
  expr: expressionInterpreter,
  loader: refusingLoader,
  renderer: "svg" as const,
};

export function Chart({ spec, result }: { spec: Record<string, unknown>; result: Result }) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const values = result.rows.map((row) => Object.fromEntries(result.columns.map((column, i) => [column, row[i]])));
    // A single chart or layer without its own width fills the card.
    const fillsCard = !("width" in spec) && ("mark" in spec || "layer" in spec);
    const specWithData = { ...(fillsCard && { width: "container" }), ...spec, data: { values } } as VisualizationSpec;
    const chart = embed(container.current!, specWithData, OPTIONS);
    chart.catch((e: Error) => setError(e.message));
    return () => {
      // Stop the chart's listeners and timers once it has been drawn. A failed
      // chart is already shown as an error, so it's ignored here.
      chart.then((c) => c.finalize()).catch(() => {});
    };
  }, [spec, result]);

  return error ? <p className="chart-error">Couldn't draw the chart: {error}</p> : <div ref={container} />;
}
