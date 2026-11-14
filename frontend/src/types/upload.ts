export type UploadKind = "pdf" | "pptx" | "video";
export type Operation =
  "pdf_text" | "slides" | "transcribe" | "visuals" | "storage" | "duplicates";
export type ProcessingStatus = "queued" | "processing" | "completed" | "failed";
export interface ProcessingStep {
  operation: Operation;
  status: ProcessingStatus | "unavailable";
  progress_percent?: number | null;
  progress_current?: number | null;
  progress_total?: number | null;
  progress_unit?: string | null;
  current_step: string;
  error_message: string | null;
}
export interface ProcessingFile {
  file_id: number;
  filename: string;
  file_type: UploadKind;
  size_bytes: number;
  operations: Operation[];
  status: ProcessingStatus;
  progress_percent?: number | null;
  progress_current?: number | null;
  progress_total?: number | null;
  progress_unit?: string | null;
  current_step: string;
  error_message: string | null;
  steps: ProcessingStep[];
  reused?: boolean;
}
export type UploadLimits = Record<UploadKind, number>;
