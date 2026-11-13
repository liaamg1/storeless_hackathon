import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { getFiles } from "../services/api";
import { listPresentations } from "../services/presentations";
import type { PresentationRecord } from "../types/presentation";
import { getVideos } from "../services/transcription";
import type { FileRecord } from "../types/file";
import type { VideoRecord } from "../types/transcription";
import { mergeFiles } from "../utils/files";
import { getProcessingFiles } from "../services/uploads";
import type { ProcessingFile } from "../types/upload";
import { useUnifiedUpload } from "./useUnifiedUpload";

/** File metadata and video statuses come from their existing, independent APIs. */
export function useWorkspace() {
  const rawFiles = ref<FileRecord[]>([]);
  const recordings = ref<VideoRecord[]>([]);
  const presentations = ref<PresentationRecord[]>([]);
  const processingFiles = ref<ProcessingFile[]>([]);
  const loading = ref(true);
  const error = ref("");
  const statusError = ref("");
  let version = 0;
  async function refresh(): Promise<void> {
    const current = ++version;
    loading.value = true;
    error.value = "";
    statusError.value = "";
    const [files, videos, slides, processing] = await Promise.allSettled([
      getFiles(),
      getVideos(),
      listPresentations(),
      getProcessingFiles(),
    ]);
    if (current !== version) return;
    if (files.status === "fulfilled") rawFiles.value = files.value;
    else {
      rawFiles.value = [];
      error.value =
        files.reason instanceof Error
          ? files.reason.message
          : "Could not load files.";
    }
    if (videos.status === "fulfilled") recordings.value = videos.value;
    else {
      recordings.value = [];
      statusError.value =
        "Recording statuses are unavailable. You can still browse your files.";
    }
    presentations.value = slides.status === "fulfilled" ? slides.value : [];
    processingFiles.value =
      processing.status === "fulfilled" ? processing.value : [];
    if (processing.status === "rejected")
      statusError.value =
        "Unified processing statuses are unavailable. Other file details remain accessible.";
    loading.value = false;
  }
  const files = computed(() =>
    mergeFiles(
      rawFiles.value,
      recordings.value,
      presentations.value,
      processingFiles.value,
    ),
  );
  onMounted(refresh);
  const { history: uploadHistory } = useUnifiedUpload();
  watch(uploadHistory, () => void refresh());
  onBeforeUnmount(() => {
    version += 1;
  });
  return { files, recordings, loading, error, statusError, refresh };
}
