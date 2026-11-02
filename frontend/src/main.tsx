import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import type { components } from "./api";

type Schemas = components["schemas"];
type Entry = Schemas["UserMessage"] | Schemas["AssistantMessage"] | Schemas["QueryResult"] | Schemas["InvalidCall"];

function App() {
  const [entries, setEntries] = useState<Entry[]>([]);

  useEffect(() => {
    fetch("/api/history")
      .then((response) => response.json())
      .then(setEntries);
  }, []);

  return (
    <main>
      {entries.map((entry, i) => (
        <p key={i}>{entry.kind}</p>
      ))}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
