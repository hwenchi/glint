import type { components } from "./api";

type Schemas = components["schemas"];

export type UserMessage = Schemas["UserMessage"];
export type AssistantMessage = Schemas["AssistantMessage"];
export type QueryResult = Schemas["QueryResult"];
export type InvalidCall = Schemas["InvalidCall"];
export type QueryRun = Schemas["QueryRun"];
export type Result = Schemas["Result"];

export type Entry = UserMessage | AssistantMessage | QueryResult | InvalidCall;
