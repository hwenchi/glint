import type { components } from "./api";

type Schemas = components["schemas"];
type Entry = Schemas["UserMessage"] | Schemas["AssistantMessage"] | Schemas["QueryResult"] | Schemas["InvalidCall"];

const history = document.getElementById("history")!;

const response = await fetch("/api/history");
const entries: Entry[] = await response.json();
for (const entry of entries) {
  const line = document.createElement("p");
  line.textContent = entry.kind;
  history.append(line);
}
