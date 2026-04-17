import { requestJson } from "@shared/transport/http";

export async function fetchApiRoot() {
  return requestJson<Record<string, unknown>>("/api");
}

