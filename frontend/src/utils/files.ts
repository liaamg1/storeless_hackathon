import type { PresentationRecord } from "../types/presentation";
import type { FileRecord } from "../types/file";
import type { VideoRecord, JobStatus } from "../types/transcription";
import type { ProcessingFile } from "../types/upload";

export type FileStatus = JobStatus | "available" | "unknown";
export interface WorkspaceFile extends FileRecord {
  type: "pdf" | "pptx" | "video" | "other";
  status: FileStatus;
  video?: VideoRecord;
  presentation?: PresentationRecord;
  processing?: ProcessingFile;
}
export type FileSort =
  "newest" | "oldest" | "name" | "name-desc" | "size" | "size-asc";

export function fileType(filename: string): WorkspaceFile["type"] {
  return /\.mp4$/i.test(filename)
    ? "video"
    : /\.pdf$/i.test(filename)
      ? "pdf"
      : /\.pptx$/i.test(filename)
        ? "pptx"
        : "other";
}
export function mergeFiles(
  files: FileRecord[],
  recordings: VideoRecord[],
  presentations: PresentationRecord[] = [],
  processingFiles: ProcessingFile[] = [],
): WorkspaceFile[] {
  const videos = new Map(recordings.map((video) => [video.file_id, video]));
  const analyzed = new Map(presentations.map((p) => [p.file_id, p]));
  const processing = new Map(
    processingFiles.map((file) => [file.file_id, file]),
  );
  return files.map((file) => {
    const type = fileType(file.filename);
    const video = videos.get(file.id);
    const presentation = analyzed.get(file.id);
    return {
      ...file,
      type,
      video,
      presentation,
      processing: processing.get(file.id),
      status:
        processing.get(file.id)?.status ??
        video?.status ??
        (presentation && presentation.status !== "not_processed"
          ? presentation.status
          : type === "video" || type === "pptx"
            ? "unknown"
            : "available"),
    };
  });
}
export function filterFiles(
  files: WorkspaceFile[],
  query: string,
  type: string,
  status: string,
  sort: FileSort,
): WorkspaceFile[] {
  const normalized = query.trim().toLocaleLowerCase();
  return files
    .filter(
      (file) =>
        file.filename.toLocaleLowerCase().includes(normalized) &&
        (type === "all" || file.type === type) &&
        (status === "all" || file.status === status),
    )
    .sort((a, b) => {
      const date = (value: string | null) =>
        value ? new Date(value).getTime() || 0 : 0;
      const order =
        sort === "name"
          ? a.filename.localeCompare(b.filename)
          : sort === "name-desc"
            ? b.filename.localeCompare(a.filename)
            : sort === "size"
              ? b.size_bytes - a.size_bytes
              : sort === "size-asc"
                ? a.size_bytes - b.size_bytes
                : sort === "oldest"
                  ? date(a.uploaded_at) - date(b.uploaded_at)
                  : date(b.uploaded_at) - date(a.uploaded_at);
      return order || a.id - b.id;
    });
}
export function fileDestination(file: Pick<WorkspaceFile, "id" | "type">) {
  return {
    name:
      file.type === "video"
        ? "transcription"
        : file.type === "pptx"
          ? "slides"
          : "extract",
    query: { file: String(file.id) },
  };
}
export function formatDate(value: string | null): string {
  if (!value || Number.isNaN(new Date(value).getTime())) return "Unknown date";
  return new Date(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
