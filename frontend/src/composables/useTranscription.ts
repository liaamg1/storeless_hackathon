import { onBeforeUnmount, onMounted, ref } from "vue";
import {
  getProcessingJob,
  getTranscript,
  getVideo,
  getVideos,
  uploadVideo,
} from "../services/transcription";
import { processStoredFile } from "../services/uploads";
import { notifyFilesChanged } from "../utils/fileUpdates";
import { recommendedOperations } from "../utils/upload";
import type {
  ProcessingJob,
  VideoRecord,
  VideoTranscript,
  VideoUploadResult,
} from "../types/transcription";

export function useTranscription() {
  const recordings = ref<VideoRecord[]>([]);
  const loadingRecordings = ref(true);
  const recordingsError = ref("");
  const uploading = ref(false);
  const uploadError = ref("");
  const selectedVideo = ref<VideoRecord | null>(null);
  const job = ref<ProcessingJob | null>(null);
  const transcript = ref<VideoTranscript | null>(null);
  const loadingStatus = ref(false);
  const updatingVideo = ref(false);
  const statusError = ref("");
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  let selectionVersion = 0;

  async function loadRecordings(): Promise<void> {
    loadingRecordings.value = true;
    recordingsError.value = "";
    try {
      recordings.value = await getVideos();
    } catch (error) {
      recordingsError.value = error instanceof Error ? error.message : "Could not load saved recordings.";
    } finally {
      loadingRecordings.value = false;
    }
  }

  function clearSelection(): void {
    selectionVersion += 1;
    clearTimeout(pollTimer);
    selectedVideo.value = null;
    job.value = null;
    transcript.value = null;
    statusError.value = "";
    loadingStatus.value = false;
  }

  async function pollJob(jobId: number, version: number): Promise<void> {
    try {
      const savedJob = await getProcessingJob(jobId);
      if (version !== selectionVersion) return;
      job.value = savedJob;
      if (savedJob.status === "completed") {
        const savedTranscript = await getTranscript(savedJob.file_id);
        if (version === selectionVersion) {
          transcript.value = savedTranscript;
          void loadRecordings();
        }
      } else if (savedJob.status === "queued" || savedJob.status === "processing") {
        // Schedule after the response so slow requests cannot overlap or invent progress.
        pollTimer = setTimeout(() => void pollJob(jobId, version), 1500);
      } else {
        void loadRecordings();
      }
    } catch (error) {
      if (version === selectionVersion) {
        statusError.value = error instanceof Error ? error.message : "Could not refresh processing status.";
      }
      // Stop on network failures; the view offers an explicit retry without retranscribing.
    } finally {
      if (version === selectionVersion) loadingStatus.value = false;
    }
  }

  async function selectVideo(fileId: number): Promise<void> {
    clearSelection();
    const version = selectionVersion;
    loadingStatus.value = true;
    try {
      let recording: VideoRecord;
      try {
        recording = await getVideo(fileId);
      } catch {
        await processStoredFile(fileId, recommendedOperations("video"));
        notifyFilesChanged();
        recording = await getVideo(fileId);
      }
      if (version !== selectionVersion) return;
      selectedVideo.value = recording;
      await pollJob(recording.job_id, version);
    } catch (error) {
      if (version === selectionVersion) {
        statusError.value =
          error instanceof Error
            ? error.message
            : "Could not open this recording.";
        loadingStatus.value = false;
      }
    }
  }

  async function runOrUpdateVideo(fileId: number): Promise<void> {
    if (updatingVideo.value) return;
    updatingVideo.value = true;
    statusError.value = "";
    try {
      await processStoredFile(fileId, recommendedOperations("video"));
      notifyFilesChanged();
      await loadRecordings();
      await selectVideo(fileId);
    } catch (error) {
      statusError.value =
        error instanceof Error
          ? error.message
          : "Could not run or update video analysis.";
    } finally {
      updatingVideo.value = false;
    }
  }

  async function uploadRecording(file: File): Promise<VideoUploadResult | null> {
    if (uploading.value) return null;
    uploading.value = true;
    uploadError.value = "";
    try {
      const result = await uploadVideo(file);
      await loadRecordings();
      return result;
    } catch (error) {
      uploadError.value = error instanceof Error ? error.message : "Could not upload this recording.";
      return null;
    } finally {
      uploading.value = false;
    }
  }

  onMounted(loadRecordings);
  onBeforeUnmount(clearSelection);

  return {
    recordings,
    loadingRecordings,
    recordingsError,
    loadRecordings,
    uploading,
    uploadError,
    uploadRecording,
    selectedVideo,
    job,
    transcript,
    loadingStatus,
    updatingVideo,
    statusError,
    selectVideo,
    runOrUpdateVideo,
    clearSelection,
  };
}
