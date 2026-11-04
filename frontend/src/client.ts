import { EventSourceParserStream } from "eventsource-parser/stream";

import type { Entry } from "./types";

export async function loadHistory(): Promise<Entry[]> {
  const response = await fetch("/api/history");
  return response.json();
}

/** Ends the running turn before its next step. Its stream then ends with the entry saying so. */
export async function interrupt(): Promise<void> {
  await fetch("/api/interrupt", { method: "POST" });
}

/** Sends the user's message and yields the turn's entries as they arrive. */
export async function* sendMessage(text: string): AsyncGenerator<Entry> {
  const response = await fetch("/api/history", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const events = response.body!.pipeThrough(new TextDecoderStream()).pipeThrough(new EventSourceParserStream());
  for await (const event of events) {
    yield JSON.parse(event.data) as Entry;
  }
}
