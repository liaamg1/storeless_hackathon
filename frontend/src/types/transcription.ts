export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type ProcessingStep = "queued" | "validating_video" | "extracting_audio" | "transcribing_audio" | "saving_transcript" | "completed";

export interface VideoUploadResult {
  file_id: number;
  job_id: number;
  filename: string;
  status: "queued";
}

export interface ProcessingJob {
  id: number;
  file_id: number;
  status: JobStatus;
  current_step: ProcessingStep;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface VideoRecord {
  file_id: number;
  filename: string;
  size_bytes: number;
  duration_ms: number | null;
  uploaded_at: string | null;
  job_id: number;
  status: JobStatus;
}

export interface TranscriptSegment {
  id: number;
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface VideoTranscript {
  file_id: number;
  filename: string;
  duration_ms: number | null;
  language: string | null;
  status: "completed";
  segments: TranscriptSegment[];
  paragraphs: number[][];
}
