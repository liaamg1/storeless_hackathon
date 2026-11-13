interface SearchResultBase {
  file_id: number;
  filename: string;
  snippet: string;
  relevance: number;
}

export type SearchResult = SearchResultBase & (
  | { file_type: "pdf"; page_number: number }
  | { file_type: "video"; segment_id: number; start_ms: number; end_ms: number }
);

export interface SearchResponse {
  query: string;
  returned_count: number;
  results: SearchResult[];
}
