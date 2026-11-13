export interface FileRecord {
  id: number;
  filename: string;
  size_bytes: number;
  sha256: string;
  uploaded_at: string | null;
}
