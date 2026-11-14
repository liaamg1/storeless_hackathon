<script setup lang="ts">
import {
  Search,
  RefreshCw,
  Video,
  ChartNoAxesColumn,
  ChevronLeft,
  ChevronRight,
} from "@lucide/vue";
import { formatDate } from "../utils/files";
import { formatBytes } from "../utils/formatBytes";
import { formatTimestamp } from "../utils/formatTimestamp";
import StatusBadge from "../components/shared/StatusBadge.vue";
import EmptyState from "../components/shared/EmptyState.vue";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import UploadEntry from "../components/uploads/UploadEntry.vue";
import TranscriptionProgress from "../components/transcription/TranscriptionProgress.vue";
import StorageSavings from "../components/storage/StorageSavings.vue";
import TranscriptViewer from "../components/transcription/TranscriptViewer.vue";
import VisualTranscriptViewer from "../components/transcription/VisualTranscriptViewer.vue";
import { useFileUpdates } from "../composables/useFileUpdates";
import { useTranscription } from "../composables/useTranscription";
import { downloadTranscript } from "../services/transcription";

const route = useRoute();
const router = useRouter();
const {
  recordings,
  loadingRecordings,
  recordingsError,
  loadRecordings,
  selectedVideo,
  job,
  transcript,
  loadingStatus,
  updatingVideo,
  statusError,
  selectVideo,
  runOrUpdateVideo,
  clearSelection,
} = useTranscription();
useFileUpdates(async () => {
  await loadRecordings();
  if (
    !recordingsError.value &&
    selectedVideo.value &&
    !recordings.value.some(
      (video) => video.file_id === selectedVideo.value?.file_id,
    )
  )
    clearSelection();
});
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
const readingMode = ref<"transcript" | "visual">("transcript");
const visualStatus = ref("");
const showTimestamps = ref(false);
const downloadError = ref("");
const updateFeedback = ref("");

function setReadingMode(mode: "transcript" | "visual"): void {
  readingMode.value = mode;
  if (route.query.file) {
    const nextQuery: Record<string, string> = {
      file: String(route.query.file),
    };
    if (mode === "visual") nextQuery.view = "visual";
    if (typeof route.query.segment === "string")
      nextQuery.segment = route.query.segment;
    void router.replace({ name: "transcription", query: nextQuery });
  }
}

watch(
  () => [route.query.file, route.query.view],
  ([value, view], [oldValue]) => {
    readingMode.value = view === "visual" ? "visual" : "transcript";
    if (value !== oldValue) {
      downloadError.value = "";
      visualStatus.value = "";
      updateFeedback.value = "";
      const fileId = typeof value === "string" ? Number(value) : 0;
      if (Number.isSafeInteger(fileId) && fileId > 0) void selectVideo(fileId);
      else clearSelection();
    }
  },
  { immediate: true },
);

function openRecording(fileId: number, view?: "visual"): void {
  void router.push({
    name: "transcription",
    query: { file: String(fileId), ...(view ? { view } : {}) },
  });
}

function openStorageComparison(fileId: number): void {
  void router.push({
    name: "storage",
    query: { file: String(fileId) },
  });
}

async function handleRunOrUpdate(fileId?: number): Promise<void> {
  const targetId =
    fileId ?? selectedVideo.value?.file_id ?? Number(route.query.file);
  if (!Number.isSafeInteger(targetId) || targetId <= 0) return;
  updateFeedback.value = "";
  await runOrUpdateVideo(targetId);
  if (!statusError.value) {
    updateFeedback.value = "Analysis refreshed for this recording.";
  }
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
    <UploadEntry
      v-if="!selectedVideo"
      description="Upload MP4 recordings in the workspace to transcribe speech and extract visual screen content."
    />
    <p v-if="loadingStatus" role="status">Loading processing status...</p>
    <div v-if="statusError" class="status-error-box">
      <p class="error" role="alert">{{ statusError }}</p>
      <div class="recording-action-buttons">
        <button type="button" @click="retryStatus">Retry status</button>
        <button
          v-if="route.query.file"
          type="button"
          class="button-primary"
          :disabled="updatingVideo"
          @click="handleRunOrUpdate()"
        >
          <RefreshCw :size="15" :class="{ spin: updatingVideo }" />
          {{ updatingVideo ? "Running…" : "Run or Update" }}
        </button>
      </div>
    </div>

    <section v-if="selectedVideo" class="selected-recording-bar">
      <div class="selected-recording-info">
        <span class="file-type-icon video"><Video :size="20" /></span>
        <div>
          <h2>{{ selectedVideo.filename }}</h2>
          <p class="muted" style="font-size: 12px; margin: 2px 0 0">
            {{ formatBytes(selectedVideo.size_bytes) }} ·
            {{
              selectedVideo.duration_ms == null
                ? "Unknown duration"
                : formatTimestamp(selectedVideo.duration_ms).split(".")[0]
            }}
            · File #{{ selectedVideo.file_id }}
          </p>
        </div>
        <StatusBadge :status="job?.status ?? selectedVideo.status" />
      </div>
      <div class="recording-action-buttons">
        <button
          type="button"
          :class="{ 'button-primary': readingMode === 'transcript' }"
          @click="setReadingMode('transcript')"
        >
          Open Transcript
        </button>
        <button
          type="button"
          :class="{ 'button-primary': readingMode === 'visual' }"
          @click="setReadingMode('visual')"
        >
          Visual Transcript
        </button>
        <button
          type="button"
          @click="openStorageComparison(selectedVideo.file_id)"
        >
          <ChartNoAxesColumn :size="15" />View Storage Comparison
        </button>
        <button
          type="button"
          :disabled="updatingVideo"
          @click="handleRunOrUpdate(selectedVideo.file_id)"
        >
          <RefreshCw :size="15" :class="{ spin: updatingVideo }" />
          {{
            updatingVideo
              ? "Running…"
              : job?.status === "failed"
                ? "Retry Analysis"
                : "Run or Update"
          }}
        </button>
      </div>
      <p
        v-if="updateFeedback"
        class="notice"
        role="status"
        style="margin: 12px 0 0"
      >
        {{ updateFeedback }}
      </p>
    </section>

    <details
      v-if="selectedVideo && job"
      class="processing-summary"
      :open="job.status !== 'completed' || route.query.view === 'status'"
    >
      <summary>Processing status <StatusBadge :status="job.status" /></summary>
      <TranscriptionProgress :video="selectedVideo" :job="job" />
    </details>
    <VisualTranscriptViewer
      v-if="transcript && readingMode === 'visual'"
      v-model:show-timestamps="showTimestamps"
      :file-id="transcript.file_id"
      :selected-segment-id="selectedSegmentId"
      @status="visualStatus = $event"
    >
      <TranscriptViewer
        v-model:show-timestamps="showTimestamps"
        :transcript="transcript"
        :downloading="downloading"
        :download-error="downloadError"
        :selected-segment-id="selectedSegmentId"
        @download="saveTranscript"
      />
    </VisualTranscriptViewer>
    <TranscriptViewer
      v-if="transcript && readingMode === 'transcript'"
      v-model:show-timestamps="showTimestamps"
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
        :refresh-key="`${job?.status}-${visualStatus}`"
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
                <div class="recording-row-actions">
                  <button
                    type="button"
                    @click="openRecording(recording.file_id)"
                  >
                    {{
                      recording.status === "completed"
                        ? "Open Transcript"
                        : "View Status"
                    }}
                  </button>
                  <button
                    type="button"
                    @click="openStorageComparison(recording.file_id)"
                  >
                    View Storage Comparison
                  </button>
                  <button
                    type="button"
                    :disabled="updatingVideo"
                    @click="handleRunOrUpdate(recording.file_id)"
                  >
                    Run or Update
                  </button>
                </div>
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

<style scoped>
.selected-recording-bar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 20px;
}
.selected-recording-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.selected-recording-info > div {
  flex: 1;
  min-width: 160px;
}
.selected-recording-info h2 {
  margin: 0;
  font-size: 17px;
  overflow-wrap: anywhere;
}
.recording-action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.recording-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.status-error-box {
  background: #fff1f0;
  border: 1px solid #f5d4d0;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
}
</style>
