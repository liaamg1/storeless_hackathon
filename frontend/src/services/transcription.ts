import { API_URL, request } from "./api";
import type { ProcessingJob, VideoRecord, VideoTranscript, VideoUploadResult } from "../types/transcription";

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
  const response = await fetch(`${API_URL}/videos/${fileId}/transcript/download`);
  if (!response.ok) throw new Error("Could not download the transcript. Please try again.");
  return response.blob();
}
