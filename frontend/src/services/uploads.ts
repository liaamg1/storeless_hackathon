import { request } from "./api";
import type { Operation, ProcessingFile, UploadLimits } from "../types/upload";
export const getUploadLimits = () => request<UploadLimits>("/uploads/limits");
export const getProcessingFiles = () => request<ProcessingFile[]>("/uploads");
export const getFileProcessing = (id: number) =>
  request<ProcessingFile>(`/uploads/${id}`);
export function uploadAndProcess(
  file: File,
  operations: Operation[],
): Promise<ProcessingFile> {
  const body = new FormData();
  body.append("file", file);
  body.append("operations", JSON.stringify(operations));
  return request("/uploads", { method: "POST", body });
}
export function processStoredFile(
  id: number,
  operations: Operation[],
): Promise<ProcessingFile> {
  return request(`/uploads/${id}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operations }),
  });
}
