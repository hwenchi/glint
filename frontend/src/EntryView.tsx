import type { Entry } from "./types";

export function EntryView({ entry }: { entry: Entry }) {
  switch (entry.kind) {
    case "user":
      return <p>[user] {entry.text}</p>;
    case "assistant":
      // A reply that only calls the tool has no text; its queries show as their own entries.
      return entry.text ? <p>[assistant] {entry.text}</p> : null;
    case "query_result":
      return <p>[query] {entry.run.description}</p>;
    case "invalid_call":
      return <p>[invalid call] {entry.error}</p>;
  }
}
