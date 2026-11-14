/** Shared session queue keeps uploads running when a user visits another page. */
import { computed, ref } from "vue";
import type { Operation, ProcessingFile, UploadLimits } from "../types/upload";
import {
  detectUploadKind,
  recommendedOperations,
  selectionValid,
  uploadError,
} from "../utils/upload";
import {
  getProcessingFiles,
  getUploadLimits,
  processStoredFile,
  uploadAndProcess,
} from "../services/uploads";

export interface UploadItem {
  key: number;
  file: File | null;
  stored: ProcessingFile | null;
  filename: string;
  size: number;
  operations: Operation[];
  status: "selected" | "uploading" | "accepted" | "failed";
  error: string;
  uploadProgress?: number | null;
}
const items = ref<UploadItem[]>([]),
  limits = ref<UploadLimits | null>(null);
const history = ref<ProcessingFile[]>([]),
  historyLoading = ref(false),
  busy = ref(false),
  historyError = ref(""),
  limitsError = ref("");
let nextKey = 1,
  historyVersion = 0;

async function loadLimits(): Promise<void> {
  limitsError.value = "";
  try {
    limits.value = await getUploadLimits();
  } catch (error) {
    limitsError.value =
      error instanceof Error ? error.message : "Upload limits unavailable.";
  }
}
async function refresh(): Promise<void> {
  const version = ++historyVersion;
  historyLoading.value = true;
  try {
    const records = await getProcessingFiles();
    if (version === historyVersion) {
      history.value = records;
      historyError.value = "";
    }
  } catch (error) {
    if (version === historyVersion)
      historyError.value =
        error instanceof Error
          ? error.message
          : "Could not load processing files.";
  } finally {
    if (version === historyVersion) historyLoading.value = false;
  }
}
function addFiles(files: File[]): void {
  for (const file of files) {
    if (
      items.value.some(
        (item) =>
          item.file &&
          item.file.name === file.name &&
          item.file.size === file.size &&
          item.file.lastModified === file.lastModified,
      )
    )
      continue;
    const kind = detectUploadKind(file.name);
    items.value.push({
      key: nextKey++,
      file,
      stored: null,
      filename: file.name,
      size: file.size,
      operations: kind ? recommendedOperations(kind) : [],
      status: "selected",
      error: "",
    });
  }
}
function addStored(file: ProcessingFile): void {
  if (items.value.some((item) => item.stored?.file_id === file.file_id)) return;
  items.value.push({
    key: nextKey++,
    file: null,
    stored: file,
    filename: file.filename,
    size: file.size_bytes,
    operations: recommendedOperations(file.file_type),
    status: "selected",
    error: "",
  });
}
function validation(item: UploadItem): string {
  const kind = detectUploadKind(item.filename);
  if (item.file) {
    const error = uploadError(item.file, limits.value);
    if (error) return error;
  }
  return !kind || !selectionValid(kind, item.operations)
    ? "Select the base processing operation or remove this file from the selection."
    : "";
}
const ready = computed(() =>
  items.value.filter(
    (item) => item.status === "selected" || item.status === "failed",
  ),
);
const canStart = computed(
  () =>
    !busy.value &&
    ready.value.length > 0 &&
    ready.value.every((item) => !validation(item)),
);
async function start(): Promise<void> {
  if (!canStart.value) return;
  busy.value = true;
  // One upload per file, sequentially, keeps large batches from saturating memory/network.
  const batch = [...ready.value];
  try {
    for (const item of batch) {
      const kind = detectUploadKind(item.filename);
      if (kind) item.operations = recommendedOperations(kind);
      item.status = "uploading";
      item.error = "";
      item.uploadProgress = null;
      try {
        const result = item.stored
          ? await processStoredFile(item.stored.file_id, item.operations)
          : await uploadAndProcess(item.file!, item.operations, (percent) => {
              item.uploadProgress = percent;
            });
        item.stored = result;
        item.file = null;
        item.status = "accepted";
        await refresh();
      } catch (error) {
        item.status = "failed";
        item.error =
          error instanceof Error ? error.message : "File upload failed.";
      }
    }
  } finally {
    busy.value = false;
    await refresh();
  }
}
export function useUnifiedUpload() {
  return {
    items,
    limits,
    history,
    historyLoading,
    busy,
    historyError,
    limitsError,
    loadLimits,
    refresh,
    addFiles,
    addStored,
    validation,
    canStart,
    start,
  };
}
