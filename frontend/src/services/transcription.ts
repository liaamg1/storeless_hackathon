import { API_URL, request } from "./api";
import type {
  ProcessingJob,
  VideoRecord,
  VideoTranscript,
  VideoUploadResult,
} from "../types/transcription";

export function uploadVideo(file: File): Promise<VideoUploadResult> {
  const body = new FormData();
  body.append("file", file);
  return request<VideoUploadResult>("/videos/upload", { method: "POST", body });
}

export function getVideos(): Promise<VideoRecord[]> {
  return request<VideoRecord[]>("/videos");
}

export function getVideo(fileId: number): Promise<VideoRecord> {
  return request<VideoRecord>(`/videos/${fileId}`);
}

export function getProcessingJob(jobId: number): Promise<ProcessingJob> {
  return request<ProcessingJob>(`/jobs/${jobId}`);
}

export function getTranscript(fileId: number): Promise<VideoTranscript> {
  return request<VideoTranscript>(`/videos/${fileId}/transcript`);
}

export async function downloadTranscript(fileId: number): Promise<Blob> {
  const response = await fetch(
    `${API_URL}/videos/${fileId}/transcript/download`,
  );
  if (!response.ok)
    throw new Error("Could not download the transcript. Please try again.");
  return response.blob();
}

export function getVisualTranscript(
  fileId: number,
): Promise<import("../types/transcription").VisualTranscript> {
  return request(`/videos/${fileId}/visual-transcript`);
}

export function analyzeVisuals(fileId: number): Promise<{ status: string }> {
  return request(`/videos/${fileId}/visual-transcript`, { method: "POST" });
}

export function visualImageUrl(fileId: number, frameId: number): string {
  return `${API_URL}/videos/${fileId}/visuals/${frameId}/image`;
}

export async function downloadVisualTranscript(
  fileId: number,
  timestamps: boolean,
): Promise<Blob> {
  const response = await fetch(
    `${API_URL}/videos/${fileId}/visual-transcript/download?timestamps=${timestamps}`,
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "Could not download the visual transcript. Make sure visual analysis has completed.",
    );
  }
  return response.blob();
}
