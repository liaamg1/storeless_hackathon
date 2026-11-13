export interface SearchResult {
  file_id: number;
  filename: string;
  page_number: number;
  snippet: string;
  relevance: number;
}

export interface SearchResponse {
  query: string;
  returned_count: number;
  results: SearchResult[];
}
