import { StrictMode, type SubmitEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import "./style.css";

import { loadHistory, sendMessage } from "./client";
import { EntryView } from "./EntryView";
import type { Entry } from "./types";

function App() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    loadHistory().then(setEntries);
  }, []);

  async function send(event: SubmitEvent) {
    event.preventDefault();
    setSending(true);
    setText("");
    try {
      for await (const entry of sendMessage(text)) {
        setEntries((previous) => [...previous, entry]);
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <main>
      {entries.length === 0 && (
        <div className="empty">
          <h1>Glint</h1>
          <p>Ask a question about your data. Every query run to answer it is shown here, with its SQL and results.</p>
        </div>
      )}
      {entries.map((entry, i) => (
        <EntryView key={i} entry={entry} />
      ))}
      {sending && (
        <div className="working" aria-label="Working">
          <span />
          <span />
          <span />
        </div>
      )}
      <form onSubmit={send}>
        <input value={text} onChange={(event) => setText(event.target.value)} disabled={sending} />
        <button disabled={sending || !text}>Send</button>
      </form>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
