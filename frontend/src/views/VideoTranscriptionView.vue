<script setup lang="ts">
import {
  Search,
  RefreshCw,
  Video,
  ChevronLeft,
  ChevronRight,
} from "@lucide/vue";
import { formatDate } from "../utils/files";
import { formatTimestamp } from "../utils/formatTimestamp";
import StatusBadge from "../components/shared/StatusBadge.vue";
import EmptyState from "../components/shared/EmptyState.vue";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import VideoUpload from "../components/transcription/VideoUpload.vue";
import TranscriptionProgress from "../components/transcription/TranscriptionProgress.vue";
import StorageSavings from "../components/storage/StorageSavings.vue";
import TranscriptViewer from "../components/transcription/TranscriptViewer.vue";
import { useTranscription } from "../composables/useTranscription";
import { downloadTranscript } from "../services/transcription";

const route = useRoute();
const router = useRouter();
const {
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
  statusError,
  selectVideo,
  clearSelection,
} = useTranscription();
const selectedSegmentId = computed(() => {
  const value = route.query.segment;
  const id = typeof value === "string" ? Number(value) : 0;
  return Number.isSafeInteger(id) && id > 0 ? id : null;
});
const recordingsQuery = ref("");
const recordingsPage = ref(1);
const filteredRecordings = computed(() =>
  recordings.value.filter((recording) =>
    recording.filename
      .toLocaleLowerCase()
      .includes(recordingsQuery.value.trim().toLocaleLowerCase()),
  ),
);
const pagedRecordings = computed(() =>
  filteredRecordings.value.slice(
    (recordingsPage.value - 1) * 8,
    recordingsPage.value * 8,
  ),
);
const recordingPages = computed(() =>
  Math.max(1, Math.ceil(filteredRecordings.value.length / 8)),
);
watch(recordingsQuery, () => {
  recordingsPage.value = 1;
});
watch(recordingPages, (count) => {
  recordingsPage.value = Math.min(recordingsPage.value, count);
});
const downloading = ref(false);
const downloadError = ref("");
let viewIsActive = true;
onBeforeUnmount(() => {
  viewIsActive = false;
});

watch(
  () => route.query.file,
  (value) => {
    downloadError.value = "";
    const fileId = typeof value === "string" ? Number(value) : 0;
    if (Number.isSafeInteger(fileId) && fileId > 0) void selectVideo(fileId);
    else clearSelection();
  },
  { immediate: true },
);

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
    downloadError.value =
      error instanceof Error ? error.message : "Could not download transcript.";
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <div>
    <div class="page-intro">
      <div>
        <p class="eyebrow">Processing</p>
        <h1>Video Transcription</h1>
        <p>Turn recordings into readable, searchable knowledge.</p>
      </div>
    </div>
    <VideoUpload
      :uploading="uploading"
      :error="uploadError"
      @upload="uploadAndMonitor"
    />
    <p v-if="loadingStatus" role="status">Loading processing status...</p>
    <div v-if="statusError">
      <p class="error" role="alert">{{ statusError }}</p>
      <button type="button" @click="retryStatus">Retry status</button>
    </div>
    <details
      v-if="selectedVideo && job"
      class="processing-summary"
      :open="job.status !== 'completed' || route.query.view === 'status'"
    >
      <summary>Processing status <StatusBadge :status="job.status" /></summary>
      <TranscriptionProgress :video="selectedVideo" :job="job" />
    </details>
    <TranscriptViewer
      v-if="transcript"
      :transcript="transcript"
      :downloading="downloading"
      :download-error="downloadError"
      :selected-segment-id="selectedSegmentId"
      @download="saveTranscript"
    />
    <details v-if="selectedVideo" class="secondary-details">
      <summary>
        Potential storage savings<span class="muted"
          >Original vs optimized</span
        >
      </summary>
      <StorageSavings
        v-if="selectedVideo"
        :file-id="selectedVideo.file_id"
        :refresh-key="job?.status"
      />
    </details>
    <section aria-labelledby="recordings-heading" class="recordings-panel">
      <div class="panel-heading">
        <h2 id="recordings-heading">
          Saved recordings
          <span class="count-chip">{{ recordings.length }}</span>
        </h2>
        <button :disabled="loadingRecordings" @click="loadRecordings">
          <RefreshCw :size="14" />Refresh
        </button>
      </div>
      <div class="recording-controls">
        <div class="input-with-icon">
          <Search :size="16" /><input
            v-model="recordingsQuery"
            type="search"
            aria-label="Search recordings"
            placeholder="Search recordings…"
          />
        </div>
        <span class="muted" style="font-size: 12px"
          >{{ filteredRecordings.length }} recordings</span
        >
      </div>
      <p v-if="loadingRecordings" role="status">Loading recordings…</p>
      <p v-else-if="recordingsError" class="error" role="alert">
        {{ recordingsError }}
      </p>
      <EmptyState
        v-else-if="!filteredRecordings.length"
        :title="recordings.length ? 'No recordings match' : 'No recordings yet'"
        description="Upload an MP4 or try another filename."
      />
      <div v-else class="table-container">
        <table class="recording-table">
          <thead>
            <tr>
              <th class="filename-column">Recording</th>
              <th class="duration-column">Duration</th>
              <th>Status</th>
              <th class="date-column">Uploaded</th>
              <th class="actions-column">
                <span class="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="recording in pagedRecordings" :key="recording.file_id">
              <td>
                <button
                  class="file-name-button"
                  :title="recording.filename"
                  @click="openRecording(recording.file_id)"
                >
                  <span class="file-type-icon video"><Video :size="17" /></span
                  ><span class="truncate">{{ recording.filename }}</span>
                </button>
              </td>
              <td class="duration-column nowrap">
                {{
                  recording.duration_ms == null
                    ? "Unknown"
                    : formatTimestamp(recording.duration_ms).split(".")[0]
                }}
              </td>
              <td><StatusBadge :status="recording.status" /></td>
              <td class="date-column nowrap">
                {{ formatDate(recording.uploaded_at) }}
              </td>
              <td>
                <button @click="openRecording(recording.file_id)">
                  {{
                    recording.status === "completed"
                      ? "Open transcript"
                      : "View status"
                  }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <footer class="pagination">
          <span>Page {{ recordingsPage }} of {{ recordingPages }}</span>
          <div>
            <button
              class="icon-button"
              aria-label="Previous recordings page"
              :disabled="recordingsPage <= 1"
              @click="recordingsPage--"
            >
              <ChevronLeft :size="16" /></button
            ><button
              class="icon-button"
              aria-label="Next recordings page"
              :disabled="recordingsPage >= recordingPages"
              @click="recordingsPage++"
            >
              <ChevronRight :size="16" />
            </button>
          </div>
        </footer>
      </div>
    </section>
  </div>
</template>
