import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { EntryView } from "./EntryView";
import type { Entry } from "./types";

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
        <EntryView key={i} entry={entry} />
      ))}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
