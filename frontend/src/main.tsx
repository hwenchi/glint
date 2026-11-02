import { type FormEvent, StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

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

  async function send(event: FormEvent) {
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
      {entries.map((entry, i) => (
        <EntryView key={i} entry={entry} />
      ))}
      <form onSubmit={send}>
        <input value={text} onChange={(event) => setText(event.target.value)} disabled={sending} />
        <button disabled={sending || !text}>Send</button>
        {sending && <span>[working]</span>}
      </form>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
