<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import {
  UploadCloud,
  FileText,
  Video,
  Presentation,
  X,
  RefreshCw,
  Copy,
} from "@lucide/vue";
import { useFileUpdates } from "../composables/useFileUpdates";
import { useUnifiedUpload } from "../composables/useUnifiedUpload";
import {
  detectUploadKind,
  operationOptions,
  uploadResultMessage,
} from "../utils/upload";
import { getFileProcessing } from "../services/uploads";
import { formatBytes } from "../utils/formatBytes";
import FileProgress from "../components/shared/FileProgress.vue";
import ProcessingFileCard from "../components/uploads/ProcessingFileCard.vue";
import SmartOverview from "../components/uploads/SmartOverview.vue";

const route = useRoute();
const router = useRouter();
const {
  items,
  limits,
  autoStart,
  history,
  historyLoading,
  busy,
  historyError,
  limitsError,
  loadLimits,
  refresh,
  addFiles,
  addStored,
  toggleOperation,
  dismissItem,
  validation,
  canStart,
  start,
} = useUnifiedUpload();
useFileUpdates(refresh);

type WorkspaceTab = "upload" | "review" | "activity";
const tab = ref<WorkspaceTab>(route.query.file ? "upload" : "review");

function setTab(next: WorkspaceTab): void {
  tab.value = next;
  if (route.query.tab !== next || route.query.file) {
    void router.replace({ name: "upload", query: { tab: next } });
  }
}

watch(
  () => route.query.tab,
  (value) => {
    if (value === "upload" || value === "review" || value === "activity")
      tab.value = value;
  },
  { immediate: true },
);
watch(busy, (value, previous) => {
  if (previous && !value && !pending.value.length) setTab("review");
});
const dragging = ref(false),
  existingError = ref("");
const pending = computed(() =>
  items.value.filter((item) => item.status !== "accepted"),
);
const accepted = computed(() =>
  items.value.filter((item) => item.status === "accepted"),
);
const completedCount = computed(
  () => history.value.filter((file) => file.status === "completed").length,
);
const activeCount = computed(
  () =>
    history.value.filter(
      (file) => file.status === "processing" || file.status === "queued",
    ).length,
);

let active = true,
  timer: ReturnType<typeof setTimeout> | undefined,
  existingVersion = 0;
function select(event: Event): void {
  const input = event.target as HTMLInputElement;
  addFiles(Array.from(input.files ?? []));
  input.value = "";
}
function drop(event: DragEvent): void {
  dragging.value = false;
  if (!busy.value) addFiles(Array.from(event.dataTransfer?.files ?? []));
}
async function poll(): Promise<void> {
  await refresh();
  if (active)
    timer = setTimeout(
      () => void poll(),
      busy.value || activeCount.value > 0 ? 2500 : 10000,
    );
}
watch(
  () => route.query.file,
  async (value) => {
    const version = ++existingVersion;
    existingError.value = "";
    const id = typeof value === "string" ? Number(value) : 0;
    if (!Number.isSafeInteger(id) || id <= 0) return;
    try {
      const file = await getFileProcessing(id);
      if (active && version === existingVersion) {
        tab.value = "upload";
        addStored(file, true);
      }
    } catch (error) {
      if (active && version === existingVersion)
        existingError.value =
          error instanceof Error
            ? error.message
            : "Could not open stored file.";
    }
  },
  { immediate: true },
);
onMounted(() => {
  void loadLimits();
  void poll();
});
onBeforeUnmount(() => {
  active = false;
  existingVersion++;
  clearTimeout(timer);
});
</script>
<template>
  <div class="page-intro">
    <div>
      <p class="eyebrow">Workspace</p>
      <h1>Storage Opportunities</h1>
      <p>Upload files, review savings recommendations, and clean up duplicates.</p>
    </div>
    <button
      v-if="tab !== 'upload'"
      class="button-primary"
      aria-label="Add files"
      @click="setTab('upload')"
    >
      <UploadCloud :size="16" /><span>Add files</span>
    </button>
  </div>

  <article
    v-for="item in accepted"
    :key="item.key"
    class="accepted-upload"
    :class="{ 'duplicate-upload': item.stored?.reused }"
    role="status"
  >
    <div class="accepted-upload-body">
      <strong>{{ item.filename }}</strong>
      <p>{{ uploadResultMessage(item.stored) }}</p>
      <div v-if="item.stored" class="accepted-upload-links">
        <template v-if="item.stored.file_type === 'video'">
          <RouterLink
            :to="{
              name: 'transcription',
              query: { file: String(item.stored.file_id) },
            }"
          >
            Open Transcript →
          </RouterLink>
          <RouterLink
            :to="{
              name: 'storage',
              query: { file: String(item.stored.file_id) },
            }"
          >
            View Storage Comparison →
          </RouterLink>
        </template>
        <template v-else-if="item.stored.file_type === 'pdf'">
          <RouterLink
            :to="{
              name: 'extract',
              query: { file: String(item.stored.file_id) },
            }"
          >
            Open Document Text →
          </RouterLink>
          <RouterLink
            :to="{
              name: 'slides',
              query: { file: String(item.stored.file_id) },
            }"
          >
            Compare Slides →
          </RouterLink>
        </template>
        <template v-else-if="item.stored.file_type === 'pptx'">
          <RouterLink
            :to="{
              name: 'slides',
              query: { file: String(item.stored.file_id) },
            }"
          >
            Compare Slides →
          </RouterLink>
        </template>
        <RouterLink
          :to="{
            name: 'files',
            query: { file: String(item.stored.file_id) },
          }"
        >
          File Details →
        </RouterLink>
      </div>
    </div>
    <button
      class="icon-button"
      :aria-label="`Dismiss notice for ${item.filename}`"
      @click="dismissItem(item.key)"
    >
      <X :size="16" />
    </button>
  </article>

  <div class="workspace-bar">
    <nav class="analysis-tabs" aria-label="Analysis views">
      <button :aria-pressed="tab === 'review'" @click="setTab('review')">
        Recommendations <span>{{ completedCount }}</span>
      </button>
      <button :aria-pressed="tab === 'upload'" @click="setTab('upload')">
        Add files
        <span v-if="pending.length">{{ pending.length }}</span>
      </button>
      <button :aria-pressed="tab === 'activity'" @click="setTab('activity')">
        Activity
        <span>{{
          activeCount ? `${activeCount} running` : history.length
        }}</span>
      </button>
    </nav>
    <RouterLink class="cleanup-inline-link" :to="{ name: 'duplicates' }">
      <Copy :size="14" />Review duplicate cleanup →
    </RouterLink>
  </div>

  <section
    v-show="tab === 'upload'"
    class="central-upload"
    aria-labelledby="select-files-heading"
  >
    <h2 id="select-files-heading">Add files to analyze</h2>
    <label
      class="upload-dropzone"
      :class="{ dragging }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="drop"
      ><UploadCloud :size="30" /><strong>Choose files or drop them here</strong
      ><span>PDF documents, PPTX presentations, and MP4 recordings</span
      ><input
        type="file"
        multiple
        accept=".pdf,.pptx,.mp4,application/pdf,video/mp4,application/vnd.openxmlformats-officedocument.presentationml.presentation"
        aria-label="Choose files to process"
        :disabled="busy"
        @change="select"
    /></label>
    <p v-if="limits" class="upload-limits">
      Limits: PDF {{ formatBytes(limits.pdf) }} · PPTX
      {{ formatBytes(limits.pptx) }} · MP4 {{ formatBytes(limits.video) }} ·
      Originals are retained
    </p>
    <p v-else-if="limitsError" class="error" role="alert">
      {{ limitsError }} <button @click="loadLimits">Retry limits</button>
    </p>
    <p v-else class="upload-limits" role="status">
      Loading current upload limits…
    </p>
    <details class="advanced-upload-options">
      <summary>Advanced options</summary>
      <label class="auto-start-toggle">
        <input v-model="autoStart" type="checkbox" />
        Start analysis automatically as soon as files are selected (recommended)
      </label>
      <p class="muted" style="font-size: 12px; margin: 4px 0 0">
        Uncheck to review or customize individual processing operations before
        starting.
      </p>
    </details>
    <p v-if="existingError" class="error" role="alert">{{ existingError }}</p>
    <div v-if="pending.length" class="selected-files">
      <div class="panel-heading" style="margin-top: 20px">
        <h3>Queue ({{ pending.length }})</h3>
        <button
          class="button-primary"
          :disabled="!canStart"
          @click="start"
        >
          <UploadCloud :size="16" />{{
            busy ? "Uploading…" : "Upload & Analyze"
          }}
        </button>
      </div>
      <article v-for="item in pending" :key="item.key" class="selection-card">
        <header>
          <span class="file-type-icon" :class="detectUploadKind(item.filename)"
            ><component
              :is="
                detectUploadKind(item.filename) === 'video'
                  ? Video
                  : detectUploadKind(item.filename) === 'pptx'
                    ? Presentation
                    : FileText
              "
              :size="20"
          /></span>
          <div>
            <h3>{{ item.filename }}</h3>
            <small
              >{{ formatBytes(item.size) }} ·
              {{
                detectUploadKind(item.filename) === "video"
                  ? "MP4"
                  : (detectUploadKind(item.filename)?.toUpperCase() ??
                    "Unsupported")
              }}{{
                item.stored ? " · Stored file #" + item.stored.file_id : ""
              }}</small
            >
            <p
              v-if="detectUploadKind(item.filename) && autoStart"
              class="automatic-recipe"
            >
              {{
                operationOptions[detectUploadKind(item.filename)!]
                  .map((option) => option.label)
                  .join(" · ")
              }}
            </p>
            <div
              v-else-if="detectUploadKind(item.filename)"
              class="operation-checkboxes"
            >
              <label
                v-for="option in operationOptions[
                  detectUploadKind(item.filename)!
                ]"
                :key="option.id"
              >
                <input
                  type="checkbox"
                  :checked="item.operations.includes(option.id)"
                  :disabled="busy"
                  @change="
                    toggleOperation(
                      item,
                      option.id,
                      ($event.target as HTMLInputElement).checked,
                    )
                  "
                />
                {{ option.label }}
              </label>
            </div>
          </div>
          <button
            class="icon-button"
            :aria-label="`Remove ${item.filename}`"
            :disabled="busy"
            @click="dismissItem(item.key)"
          >
            <X :size="17" />
          </button>
        </header>
        <p v-if="item.stored" class="stored-note">
          Reuses stored original and completed checks; runs any missing analysis.
        </p>
        <p v-if="validation(item)" class="error" role="alert">
          {{ validation(item) }}
        </p>
        <p v-if="item.error" class="error" role="alert">{{ item.error }}</p>
        <FileProgress
          v-if="item.status === 'uploading'"
          status="uploading"
          :percent="item.uploadProgress"
          :step="
            item.stored
              ? 'Starting analysis'
              : item.uploadProgress === 100
                ? 'Upload transferred · waiting for server'
                : 'Uploading file'
          "
        />
      </article>
    </div>
  </section>

  <SmartOverview
    v-show="tab === 'review'"
    :files="history"
    :active="tab === 'review'"
    @add-files="setTab('upload')"
  />

  <section
    v-show="tab === 'activity'"
    class="processing-monitor"
    aria-labelledby="processing-files-heading"
  >
    <header class="panel-heading">
      <div>
        <h2 id="processing-files-heading">Processing Activity</h2>
        <p class="muted" style="margin: 4px 0 0; font-size: 13px">
          Live status for each uploaded file and its analysis steps.
        </p>
      </div>
      <button aria-label="Refresh status" @click="refresh">
        <RefreshCw :size="15" /><span>Refresh</span>
      </button>
    </header>
    <p v-if="historyError" class="error" role="alert">{{ historyError }}</p>
    <ProcessingFileCard
      v-for="file in history"
      :key="file.file_id"
      :file="file"
    />
    <p v-if="historyLoading && !history.length" role="status">
      Loading processing files…
    </p>
    <p v-else-if="!history.length && !historyError" class="muted">
      No files processed yet. Add files to start analyzing.
    </p>
  </section>
</template>
<style scoped>
.workspace-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 14px;
  margin-bottom: 20px;
  border-bottom: 1px solid #dce5ef;
}
.analysis-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.analysis-tabs button {
  background: transparent;
  border-color: transparent;
  padding: 8px 14px;
}
.analysis-tabs button[aria-pressed="true"] {
  background: #e7f1fc;
  color: #175ac6;
  border-color: #cadff7;
}
.analysis-tabs span {
  font-size: 11px;
  background: #edf2f8;
  color: #53677f;
  padding: 1px 6px;
  border-radius: 10px;
}
.analysis-tabs button[aria-pressed="true"] span {
  background: #d2e5fb;
  color: #175ac6;
}
.cleanup-inline-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #175ac6;
  padding: 6px 10px;
  border-radius: 6px;
  background: #eef5ff;
  border: 1px solid #cadff7;
}
.cleanup-inline-link:hover {
  background: #e2eeff;
  text-decoration: none;
}
.central-upload,
.processing-monitor {
  padding: clamp(18px, 3vw, 26px);
}
.upload-limits {
  font-size: 12px;
  color: #66768c;
  margin: 0;
}
.selection-card {
  border: 1px solid #dce5ef;
  padding: 16px;
  border-radius: 10px;
  margin: 12px 0;
  background: #fbfcfe;
}
.selection-card header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.selection-card header > div {
  flex: 1;
  min-width: 0;
}
.selection-card h3 {
  font-size: 14px;
  margin: 0 0 4px;
  overflow-wrap: anywhere;
}
.selection-card small {
  color: #66768c;
  font-size: 12px;
}
.automatic-recipe {
  font-size: 12px;
  color: #66768c;
  margin: 6px 0 0;
}
.stored-note {
  font-size: 12px;
  color: #315978;
  margin: 10px 0 0;
}
.accepted-upload {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  margin-bottom: 16px;
  border: 1px solid #cce4d7;
  border-radius: 10px;
  background: #f1faf5;
  color: #23634b;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.accepted-upload-body {
  flex: 1;
  min-width: 0;
}
.accepted-upload p {
  font-size: 13px;
  margin: 4px 0 6px;
}
.duplicate-upload {
  background: #eef5ff;
  border-color: #cadff7;
  color: #173d70;
}
.accepted-upload-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  font-weight: 600;
}
.advanced-upload-options {
  margin-top: 12px;
  font-size: 12px;
  color: #53677f;
}
.advanced-upload-options summary {
  cursor: pointer;
  font-weight: 500;
}
.auto-start-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-weight: 500;
  color: #18283d;
}
.operation-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-top: 8px;
  font-size: 12px;
}
.operation-checkboxes label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
</style>
