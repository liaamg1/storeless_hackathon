export interface StorageComponent {
  kind: "transcript" | "images" | "other";
  label: string;
  status: "measured" | "not_generated" | "unavailable";
  size_bytes: number | null;
  file_count: number | null;
}

export interface StorageSavings {
  file_id: number;
  filename: string;
  status: "completed" | "processing" | "failed" | "unavailable";
  message: string;
  original_size_bytes: number;
  optimized_size_bytes: number | null;
  artifact_format: "txt" | "html" | null;
  download_url: string | null;
  payload_size_bytes: number | null;
  original_size_mb: number;
  optimized_size_mb: number | null;
  storage_saved_bytes: number | null;
  storage_saved_mb: number | null;
  reduction_percent: number | null;
  components: StorageComponent[];
}
