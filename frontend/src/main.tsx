import { StrictMode, type SubmitEvent, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/source-code-pro/wght.css";
import "@fontsource-variable/source-sans-3/wght.css";
import "@fontsource-variable/source-serif-4/opsz.css";
import "@fontsource-variable/source-serif-4/opsz-italic.css";
import "./style.css";

import { interrupt, loadHistory, sendMessage } from "./client";
import { EntryView } from "./EntryView";
import type { Entry } from "./types";

function App() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const main = useRef<HTMLElement>(null);
  // Whether the page follows new entries: only while the reader is at the
  // bottom, so scrolling up to read isn't interrupted.
  const following = useRef(true);

  useEffect(() => {
    loadHistory().then(setEntries);
  }, []);

  // Only the reader's own scrolling decides whether the page follows. Scroll
  // events also come from layout changes, like a chart drawing in its card,
  // and from our own scrolling, and must not switch following off.
  useEffect(() => {
    const check = () => {
      const fromEnd = document.documentElement.scrollHeight - (window.innerHeight + window.scrollY);
      following.current = fromEnd < window.innerHeight / 2;
    };
    // After the input has moved the page. Typing in the message box isn't scrolling.
    const onInput = (event: Event) => {
      if (event.target instanceof HTMLInputElement) return;
      requestAnimationFrame(check);
    };
    const inputs = ["wheel", "touchmove", "keydown"] as const;
    inputs.forEach((type) => window.addEventListener(type, onInput, { passive: true }));
    return () => inputs.forEach((type) => window.removeEventListener(type, onInput));
  }, []);

  // Follow growth, not entries, since a chart draws after its card appears. The
  // scroll is instant: a smooth one is still under way when the page grows again,
  // and its scroll events would then read as the reader scrolling up.
  useEffect(() => {
    const observer = new ResizeObserver(() => {
      if (!following.current) return;
      const bottom = document.documentElement.scrollHeight - window.innerHeight;
      window.scrollTo({ top: bottom });
    });
    observer.observe(main.current!);
    return () => observer.disconnect();
  }, []);

  async function send(event: SubmitEvent) {
    event.preventDefault();
    following.current = true; // the answer to a new question is what the reader wants to see
    window.scrollTo({ top: document.documentElement.scrollHeight - window.innerHeight });
    setRunning(true);
    setText("");
    try {
      for await (const entry of sendMessage(text)) {
        setEntries((previous) => [...previous, entry]);
      }
    } finally {
      setRunning(false);
      setStopping(false);
    }
  }

  // The turn's stream keeps going until the server ends it with the entry saying so.
  function stop() {
    setStopping(true);
    interrupt();
  }

  return (
    <main ref={main}>
      {entries.length === 0 && (
        <div className="empty">
          <h1>Glint</h1>
          <p>Ask anything about your data.</p>
        </div>
      )}
      {entries.map((entry, i) => (
        <EntryView key={i} entry={entry} />
      ))}
      {running && (
        <div className="working" aria-label="Working">
          <span />
          <span />
          <span />
        </div>
      )}
      {/* Under the welcome until the first message, then pinned to the bottom. */}
      <form onSubmit={send} className={entries.length === 0 ? "start" : undefined}>
        <input value={text} onChange={(event) => setText(event.target.value)} disabled={running} />
        {running ? (
          <button type="button" onClick={stop} disabled={stopping}>
            Stop
          </button>
        ) : (
          <button disabled={!text}>Send</button>
        )}
      </form>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
