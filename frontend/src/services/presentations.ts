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
