export interface DuplicateFile {
  id: number;
  filename: string;
  size_bytes: number;
  uploaded_at: string | null;
  completed_operations?: string[];
}

export interface DuplicateGroup {
  sha256: string;
  file_size_bytes: number;
  file_count: number;
  potential_savings_bytes: number;
  files: DuplicateFile[];
}

export interface DuplicateSummary {
  duplicate_groups: number;
  redundant_copies: number;
  potential_savings_bytes: number;
}

export interface DuplicateResponse {
  summary: DuplicateSummary;
  groups: DuplicateGroup[];
}
