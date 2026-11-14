import type { FileRecord } from "../types/file";
import type { DocumentDetails, UploadResult } from "../types/document";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function extractErrorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown } | undefined;
    if (typeof first?.msg === "string" && first.msg.trim()) return first.msg;
  }
  return fallback;
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      extractErrorMessage(body, `Request failed (${response.status}).`),
    );
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
