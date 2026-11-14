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
import { useFileUpdates } from "./useFileUpdates";
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
  let version = 0,
    hasLoaded = false,
    progressTimer: number | undefined;
  async function refresh(): Promise<void> {
    const current = ++version;
    // Keep the current table and drawer mounted while polling updates statuses.
    loading.value = !hasLoaded;
    const [files, videos, slides, processing] = await Promise.allSettled([
      getFiles(),
      getVideos(),
      listPresentations(),
      getProcessingFiles(),
    ]);
    if (current !== version) return;
    const warnings: string[] = [];
    if (files.status === "fulfilled") {
      rawFiles.value = files.value;
      hasLoaded = true;
      error.value = "";
    } else if (!hasLoaded) {
      error.value =
        files.reason instanceof Error
          ? files.reason.message
          : "Could not load files.";
    } else {
      warnings.push(
        "File updates are unavailable. Showing the last loaded files.",
      );
    }
    if (videos.status === "fulfilled") recordings.value = videos.value;
    else warnings.push("Recording status updates are unavailable.");
    if (slides.status === "fulfilled") presentations.value = slides.value;
    else warnings.push("Slide status updates are unavailable.");
    if (processing.status === "fulfilled")
      processingFiles.value = processing.value;
    else warnings.push("Processing status updates are unavailable.");
    statusError.value = warnings.join(" ");
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
  onMounted(() => {
    void refresh();
    // Poll only while there are active jobs so measured progress appears live in All files.
    progressTimer = window.setInterval(() => {
      if (files.value.some((file) => ["queued", "processing"].includes(file.status)))
        void refresh();
    }, 1500);
  });
  useFileUpdates(refresh);
  const { history: uploadHistory } = useUnifiedUpload();
  watch(uploadHistory, () => void refresh());
  onBeforeUnmount(() => {
    version += 1;
    if (progressTimer !== undefined) window.clearInterval(progressTimer);
  });
  return { files, recordings, loading, error, statusError, refresh };
}
