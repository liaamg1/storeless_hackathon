import { API_URL, extractErrorMessage, request } from "./api";
import type { Operation, ProcessingFile, UploadLimits } from "../types/upload";
export const getUploadLimits = () => request<UploadLimits>("/uploads/limits");
export const getProcessingFiles = () => request<ProcessingFile[]>("/uploads");
export const getFileProcessing = (id: number) =>
  request<ProcessingFile>(`/uploads/${id}`);
export function uploadAndProcess(
  file: File,
  operations: Operation[],
  onProgress?: (percent: number | null) => void,
): Promise<ProcessingFile> {
  const body = new FormData();
  body.append("file", file);
  body.append("operations", JSON.stringify(operations));
  if (!onProgress) return request("/uploads", { method: "POST", body });
  return new Promise((resolve, reject) => {
    const upload = new XMLHttpRequest();
    upload.open("POST", `${API_URL}/uploads`);
    upload.upload.onprogress = (event) =>
      onProgress(
        event.lengthComputable && event.total > 0
          ? Math.floor((event.loaded * 100) / event.total)
          : null,
      );
    upload.onerror = () =>
      reject(
        new Error("Upload connection failed. Check Files before retrying."),
      );
    upload.onabort = () => reject(new Error("Upload cancelled."));
    upload.onload = () => {
      let result: unknown;
      try {
        result = JSON.parse(upload.responseText);
      } catch {
        reject(
          new Error("Invalid upload response. Check Files before retrying."),
        );
        return;
      }
      if (upload.status >= 200 && upload.status < 300)
        resolve(result as ProcessingFile);
      else
        reject(
          new Error(
            extractErrorMessage(result, `Upload failed (${upload.status}).`),
          ),
        );
    };
    upload.send(body);
  });
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
