import { request } from "./api";
import type { SearchResponse } from "../types/search";

export function fetchDocumentSearchResults(
  query: string, signal?: AbortSignal,
): Promise<SearchResponse> {
  const parameters = new URLSearchParams({ q: query });
  return request<SearchResponse>(`/search?${parameters}`, { signal });
}
