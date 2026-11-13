import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { getFiles } from "../services/api";
import { listPresentations } from "../services/presentations";
import type { PresentationRecord } from "../types/presentation";
import { getVideos } from "../services/transcription";
import type { FileRecord } from "../types/file";
import type { VideoRecord } from "../types/transcription";
import { mergeFiles } from "../utils/files";

/** File metadata and video statuses come from their existing, independent APIs. */
export function useWorkspace() {
  const rawFiles = ref<FileRecord[]>([]);
  const recordings = ref<VideoRecord[]>([]);
  const presentations = ref<PresentationRecord[]>([]);
  const loading = ref(true);
  const error = ref("");
  const statusError = ref("");
  let version = 0;
  async function refresh(): Promise<void> {
    const current = ++version;
    loading.value = true;
    error.value = "";
    statusError.value = "";
    const [files, videos, slides] = await Promise.allSettled([
      getFiles(),
      getVideos(),
      listPresentations(),
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
    loading.value = false;
  }
  const files = computed(() =>
    mergeFiles(rawFiles.value, recordings.value, presentations.value),
  );
  onMounted(refresh);
  onBeforeUnmount(() => {
    version += 1;
  });
  return { files, recordings, loading, error, statusError, refresh };
}
