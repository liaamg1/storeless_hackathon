<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import VideoUpload from "../components/transcription/VideoUpload.vue";
import TranscriptionProgress from "../components/transcription/TranscriptionProgress.vue";
import StorageSavings from "../components/storage/StorageSavings.vue";
import TranscriptViewer from "../components/transcription/TranscriptViewer.vue";
import { useTranscription } from "../composables/useTranscription";
import { downloadTranscript } from "../services/transcription";
import { formatBytes } from "../utils/formatBytes";

const route = useRoute();
const router = useRouter();
const {
  recordings, loadingRecordings, recordingsError, loadRecordings,
  uploading, uploadError, uploadRecording, selectedVideo, job, transcript,
  loadingStatus, statusError, selectVideo, clearSelection,
} = useTranscription();
const selectedSegmentId = computed(() => {
  const value = route.query.segment;
  const id = typeof value === "string" ? Number(value) : 0;
  return Number.isSafeInteger(id) && id > 0 ? id : null;
});
const downloading = ref(false);
const downloadError = ref("");
let viewIsActive = true;
onBeforeUnmount(() => { viewIsActive = false; });

watch(() => route.query.file, value => {
  downloadError.value = "";
  const fileId = typeof value === "string" ? Number(value) : 0;
  if (Number.isSafeInteger(fileId) && fileId > 0) void selectVideo(fileId);
  else clearSelection();
}, { immediate: true });

function openRecording(fileId: number): void {
  void router.push({ name: "transcription", query: { file: String(fileId) } });
}

async function uploadAndMonitor(file: File): Promise<void> {
  const result = await uploadRecording(file);
  if (result && viewIsActive) openRecording(result.file_id);
}

function retryStatus(): void {
  const fileId = Number(route.query.file);
  if (Number.isSafeInteger(fileId) && fileId > 0) void selectVideo(fileId);
}

async function saveTranscript(): Promise<void> {
  if (!transcript.value || downloading.value) return;
  const fileId = transcript.value.file_id;
  const filename = `${transcript.value.filename.replace(/\.mp4$/i, "") || `transcript-${fileId}`}.txt`;
  downloading.value = true;
  downloadError.value = "";
  try {
    const blob = await downloadTranscript(fileId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    downloadError.value = error instanceof Error ? error.message : "Could not download transcript.";
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <div>
    <VideoUpload :uploading="uploading" :error="uploadError" @upload="uploadAndMonitor" />
    <section aria-labelledby="recordings-heading">
      <h2 id="recordings-heading">Saved recordings</h2>
      <button type="button" :disabled="loadingRecordings" @click="loadRecordings">Refresh recordings</button>
      <p v-if="loadingRecordings" role="status">Loading recordings...</p>
      <p v-else-if="recordingsError" class="error" role="alert">{{ recordingsError }}</p>
      <p v-else-if="recordings.length === 0">No recordings yet. Upload an MP4 to get started.</p>
      <ul v-else class="recordings">
        <li v-for="recording in recordings" :key="recording.file_id">
          <button type="button" @click="openRecording(recording.file_id)">Open {{ recording.filename }}</button>
          <span>{{ formatBytes(recording.size_bytes) }} · {{ recording.status }}</span>
        </li>
      </ul>
    </section>
    <p v-if="loadingStatus" role="status">Loading processing status...</p>
    <div v-if="statusError">
      <p class="error" role="alert">{{ statusError }}</p>
      <button type="button" @click="retryStatus">Retry status</button>
    </div>
    <TranscriptionProgress v-if="selectedVideo && job && !transcript" :video="selectedVideo" :job="job" />
    <StorageSavings v-if="selectedVideo" :file-id="selectedVideo.file_id" :refresh-key="job?.status" />
    <TranscriptViewer
      v-if="transcript" :transcript="transcript" :downloading="downloading"
      :download-error="downloadError" :selected-segment-id="selectedSegmentId" @download="saveTranscript"
    />
  </div>
</template>

<style scoped>
.recordings { list-style: none; padding: 0; }
li { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 12px; }
li button { overflow-wrap: anywhere; max-width: 100%; text-align: left; }
</style>
