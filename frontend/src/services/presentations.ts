import { FILES_CHANGED, FILES_CHANGED_KEY } from "../utils/fileUpdates";
import { API_URL, request } from "./api";
import type {
  PresentationRecord,
  PresentationComparison,
} from "../types/presentation";
export function listPresentations(): Promise<PresentationRecord[]> {
  return request("/presentations");
}
export function getPresentation(id: number): Promise<PresentationRecord> {
  return request(`/presentations/${id}`);
}
export function getSlideComparison(
  id: number,
): Promise<PresentationComparison> {
  return request(`/presentations/${id}/comparison`);
}
export function analyzePresentation(id: number): Promise<PresentationRecord> {
  return request(`/presentations/${id}/analyze`, { method: "POST" });
}
export function uploadPresentation(file: File): Promise<PresentationRecord> {
  const body = new FormData();
  body.append("file", file);
  return request("/presentations/upload", { method: "POST", body });
}
export function slideImageUrl(id: number, thumbnail = true): string {
  return `${API_URL}/presentations/slides/${id}/image?thumbnail=${thumbnail}`;
}

export interface SlideSources {
  status: string;
  slides_compared: number;
  skipped_images: number;
  frames: {
    frame_id: number;
    matches: {
      slide_id: number;
      file_id: number;
      filename: string;
      slide_number: number;
      similarity_percent: number;
    }[];
    candidate_count: number;
  }[];
}
const sourceCache = new Map<
  number,
  { time: number; value: Promise<SlideSources> }
>();
// One invalidation per browser event lets all frame components share the next request.
window.addEventListener(FILES_CHANGED, () => sourceCache.clear());
window.addEventListener("focus", () => sourceCache.clear());
window.addEventListener("storage", (event) => {
  if (event.key === FILES_CHANGED_KEY) sourceCache.clear();
});
export function getSlideSources(
  fileId: number,
  refresh = false,
): Promise<SlideSources> {
  const cached = sourceCache.get(fileId);
  if (!refresh && cached && Date.now() - cached.time < 30000)
    return cached.value;
  const value = request<SlideSources>(`/videos/${fileId}/slide-sources`);
  if (sourceCache.size >= 8)
    sourceCache.delete(sourceCache.keys().next().value!);
  sourceCache.set(fileId, { time: Date.now(), value });
  void value.catch(() => {
    if (sourceCache.get(fileId)?.value === value) sourceCache.delete(fileId);
  });
  return value;
}
