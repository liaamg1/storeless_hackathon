import type {
  Operation,
  ProcessingFile,
  UploadKind,
  UploadLimits,
} from "../types/upload";

export interface OperationOption {
  id: Operation;
  label: string;
  detail: string;
  recommended: boolean;
}
export const operationOptions: Record<UploadKind, OperationOption[]> = {
  pdf: [
    {
      id: "pdf_text",
      label: "Extract text and make searchable",
      detail:
        "Required base operation. Selectable text only; OCR is not available.",
      recommended: true,
    },
    {
      id: "slides",
      label: "Analyze pages and compare slides",
      detail:
        "Requires text extraction. Finds exact and similar slides in analyzed presentations.",
      recommended: true,
    },
    {
      id: "duplicates",
      label: "Check for duplicate files",
      detail: "Compare recorded checksums and file sizes.",
      recommended: true,
    },
  ],
  pptx: [
    {
      id: "slides",
      label: "Extract, compare and index slides",
      detail:
        "Required base operation. Extracted slide text becomes searchable after analysis.",
      recommended: true,
    },
    {
      id: "duplicates",
      label: "Check for duplicate files",
      detail: "Compare recorded checksums and file sizes.",
      recommended: true,
    },
  ],
  video: [
    {
      id: "transcribe",
      label: "Transcribe audio and make searchable",
      detail:
        "Required base operation. Creates a readable, downloadable speech transcript.",
      recommended: true,
    },
    {
      id: "visuals",
      label: "Extract visuals and create visual transcript",
      detail:
        "Requires transcription. Pairs compressed images with matching speech.",
      recommended: true,
    },
    {
      id: "storage",
      label: "Calculate potential storage savings",
      detail:
        "Requires transcription. Uses measured text and image output sizes.",
      recommended: true,
    },
    {
      id: "duplicates",
      label: "Check for duplicate files",
      detail: "Compare recorded checksums and file sizes.",
      recommended: true,
    },
  ],
};
export const baseOperation: Record<UploadKind, Operation> = {
  pdf: "pdf_text",
  pptx: "slides",
  video: "transcribe",
};
export function detectUploadKind(name: string): UploadKind | null {
  return /\.pdf$/i.test(name)
    ? "pdf"
    : /\.pptx$/i.test(name)
      ? "pptx"
      : /\.mp4$/i.test(name)
        ? "video"
        : null;
}
export function recommendedOperations(kind: UploadKind): Operation[] {
  return operationOptions[kind]
    .filter((option) => option.recommended)
    .map((option) => option.id);
}
export function selectOperation(
  kind: UploadKind,
  selected: Operation[],
  operation: Operation,
  enabled: boolean,
): Operation[] {
  const allowed = new Set(operationOptions[kind].map((option) => option.id));
  if (!allowed.has(operation)) return selected;
  const next = new Set(selected.filter((item) => allowed.has(item)));
  if (enabled) {
    next.add(baseOperation[kind]);
    next.add(operation);
  } else if (operation === baseOperation[kind]) next.clear();
  else next.delete(operation);
  return [...next];
}
export function selectionValid(
  kind: UploadKind,
  selected: Operation[],
): boolean {
  return (
    selected.includes(baseOperation[kind]) &&
    selected.every((id) =>
      operationOptions[kind].some((option) => option.id === id),
    )
  );
}
export function uploadError(
  file: Pick<File, "name" | "size">,
  limits: UploadLimits | null,
): string {
  const kind = detectUploadKind(file.name);
  if (!kind) return "Unsupported format. Choose PDF, PPTX or MP4.";
  if (!file.size) return "This file is empty.";
  if (!limits)
    return "Upload limits are not available yet. Retry loading limits.";
  if (file.size > limits[kind])
    return `This file exceeds the current ${(limits[kind] / 1_000_000).toLocaleString()} MB limit.`;
  return "";
}
export function operationLabel(operation: Operation, kind: UploadKind): string {
  return (
    operationOptions[kind].find((option) => option.id === operation)?.label ??
    operation
  );
}
export function processingStepLabel(step: string): string {
  const labels: Record<string, string> = {
    queued: "Queued",
    validating_video: "Validating recording",
    extracting_audio: "Extracting audio",
    transcribing_audio: "Transcribing audio",
    saving_transcript: "Saving transcript",
    rendering_slides: "Rendering slides",
    saving_slides: "Saving slide comparisons",
    extracting_visuals: "Extracting and comparing visuals",
    completed: "Completed",
    waiting_for_output: "Waiting for optimized output",
    storage_measured: "Storage measured",
    text_extracted: "Text extracted and indexed",
    pdf_text: "Extracting text",
    duplicate_check: "Checking duplicate files",
    dependency_failed: "A required operation failed",
    waiting_for_processing: "Waiting for processing",
    waiting_for_text: "Waiting for text extraction",
  };
  return labels[step] ?? step.replace(/_/g, " ");
}

/** Describe transcription readiness separately from unfinished visual/storage work. */
export function uploadResultMessage(file: ProcessingFile | null): string {
  if (!file?.reused)
    return "Upload accepted. Processing continues in the background.";
  if (file.file_type !== "video")
    return "Duplicate file detected. The existing file and its available results were reused.";
  const speech = file.steps.find((step) => step.operation === "transcribe");
  if (speech?.status === "completed")
    return "Duplicate video detected. This file is already transcribed. The existing transcript was reused; no new transcription was started.";
  if (speech?.status === "queued" || speech?.status === "processing")
    return "Duplicate video detected. This file is already queued or being transcribed. The existing job was reused; no second transcription was started.";
  return "Duplicate video detected. The existing recording was reused. Check its processing status for available results.";
}
