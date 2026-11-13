export interface UploadResult {
  id: number;
  filename: string;
  size_bytes: number;
  page_count: number;
  status: "completed";
}

export interface DocumentPage {
  page_number: number;
  text: string;
}

export interface DocumentDetails {
  file_id: number;
  filename: string;
  size_bytes: number;
  page_count: number;
  status: "completed" | "not_processed";
  pages: DocumentPage[];
}
