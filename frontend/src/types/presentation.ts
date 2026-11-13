export type PresentationStatus =
  "not_processed" | "queued" | "processing" | "completed" | "failed";
export interface PresentationRecord {
  file_id: number;
  filename: string;
  size_bytes: number;
  uploaded_at: string | null;
  job_id: number | null;
  status: PresentationStatus;
  current_step: string | null;
  error_message: string | null;
  slide_count: number;
}
export interface SlidePreview {
  id: number;
  file_id: number;
  filename: string;
  slide_number: number;
  text: string;
  processed_at: string;
}
export type SlideClassification = "exact" | "similar" | "unique";
export interface SlideMatch {
  slide: SlidePreview;
  classification: "exact" | "similar";
  similarity_percent: number;
  hash_distance: number;
}
export interface SlideComparison {
  slide: SlidePreview;
  classification: SlideClassification;
  matches: SlideMatch[];
}
export interface PresentationComparison {
  presentation: PresentationRecord;
  similarity_threshold: number;
  summary: {
    presentations_analyzed: number;
    total_slides_analyzed: number;
    selected_slide_count: number;
    exact_slides: number;
    similar_slides: number;
    unique_slides: number;
    matching_presentations: number;
  };
  slides: SlideComparison[];
}
