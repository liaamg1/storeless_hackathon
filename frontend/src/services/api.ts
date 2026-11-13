import type { FileRecord } from "../types/file";
import type { DocumentDetails, UploadResult } from "../types/document";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = typeof body?.detail === "string"
      ? body.detail
      : `Request failed (${response.status}).`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function getFiles(): Promise<FileRecord[]> {
  return request<FileRecord[]>("/files");
}

export function uploadPdf(file: File): Promise<UploadResult> {
  const body = new FormData();
  body.append("file", file);
  // The browser supplies the multipart boundary; do not set Content-Type manually.
  return request<UploadResult>("/files/upload", { method: "POST", body });
}

export function getDocumentPages(fileId: number): Promise<DocumentDetails> {
  return request<DocumentDetails>(`/files/${fileId}/pages`);
}
