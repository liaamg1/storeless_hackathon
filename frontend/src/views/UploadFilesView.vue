<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, RouterLink } from "vue-router";
import {
  UploadCloud,
  FileText,
  Video,
  Presentation,
  X,
  RefreshCw,
} from "@lucide/vue";
import { useUnifiedUpload } from "../composables/useUnifiedUpload";
import { detectUploadKind, operationOptions } from "../utils/upload";
import { getFileProcessing } from "../services/uploads";
import { formatBytes } from "../utils/formatBytes";
import ProcessingFileCard from "../components/uploads/ProcessingFileCard.vue";
import SmartOverview from "../components/uploads/SmartOverview.vue";

const route = useRoute();
const {
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
} = useUnifiedUpload();
const tab = ref<"upload" | "review" | "activity">(
  route.query.file ? "upload" : "review",
);
watch(
  () => route.query.tab,
  (value) => {
    if (value === "upload" || value === "review" || value === "activity")
      tab.value = value;
  },
  { immediate: true },
);
watch(busy, (value, previous) => {
  if (previous && !value && !pending.value.length) tab.value = "review";
});
const dragging = ref(false),
  existingError = ref("");
const pending = computed(() =>
  items.value.filter((item) => item.status !== "accepted"),
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
      busy.value ||
        history.value.some(
          (file) => file.status === "queued" || file.status === "processing",
        )
        ? 2500
        : 10000,
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
        addStored(file);
        tab.value = "upload";
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
      <p class="eyebrow">Upload · Analyze · Take action</p>
      <h1>Your workspace</h1>
      <p>
        Add files, let analysis finish, then review your storage opportunities.
      </p>
    </div>
    <button class="button-primary" @click="tab = 'upload'">Add files</button>
  </div>
  <nav class="analysis-tabs" aria-label="Analysis views">
    <button :aria-pressed="tab === 'upload'" @click="tab = 'upload'">
      Add files</button
    ><button :aria-pressed="tab === 'review'" @click="tab = 'review'">
      Recommendations
      <span>{{
        history.filter((file) => file.status === "completed").length
      }}</span></button
    ><button :aria-pressed="tab === 'activity'" @click="tab = 'activity'">
      Activity
      <span
        >{{
          history.filter(
            (file) => file.status === "processing" || file.status === "queued",
          ).length
        }}
        in progress</span
      >
    </button>
  </nav>
  <section
    v-show="tab === 'upload'"
    class="central-upload"
    aria-labelledby="select-files-heading"
  >
    <h2 id="select-files-heading">Select files</h2>
    <label
      class="upload-dropzone"
      :class="{ dragging }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="drop"
      ><UploadCloud :size="30" /><strong>Choose files or drop them here</strong
      ><span>PDF documents, PPTX presentations and MP4 recordings</span
      ><input
        type="file"
        multiple
        accept=".pdf,.pptx,.mp4,application/pdf,video/mp4,application/vnd.openxmlformats-officedocument.presentationml.presentation"
        aria-label="Choose files to process"
        :disabled="busy"
        @change="select"
    /></label>
    <p v-if="limits" class="upload-limits">
      Current limits: PDF {{ formatBytes(limits.pdf) }} · PPTX
      {{ formatBytes(limits.pptx) }} · MP4 {{ formatBytes(limits.video) }}
    </p>
    <p v-else-if="limitsError" class="error" role="alert">
      {{ limitsError }} <button @click="loadLimits">Retry limits</button>
    </p>
    <p v-else role="status">Loading current upload limits…</p>
    <p v-if="existingError" class="error" role="alert">{{ existingError }}</p>
    <div v-if="pending.length" class="selected-files">
      <h2>Ready to analyze</h2>
      <p class="muted">
        All supported checks run automatically for each file type. Review the
        results before deciding what to remove.
      </p>
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
          </div>
          <button
            class="icon-button"
            :aria-label="`Remove ${item.filename}`"
            :disabled="busy"
            @click="items = items.filter((row) => row.key !== item.key)"
          >
            <X :size="17" />
          </button>
        </header>
        <p v-if="item.stored" class="stored-note">
          Uses the stored original. Completed analysis is reused and missing
          checks are run automatically.
        </p>
        <p v-if="detectUploadKind(item.filename)" class="automatic-recipe">
          {{
            operationOptions[detectUploadKind(item.filename)!]
              .map((option) => option.label)
              .join(" · ")
          }}
        </p>
        <p v-if="validation(item)" class="error" role="alert">
          {{ validation(item) }}
        </p>
        <p v-if="item.error" class="error" role="alert">{{ item.error }}</p>
        <p v-if="item.status === 'uploading'" role="status">
          {{
            item.stored
              ? "Starting analysis…"
              : "Uploading and preparing this file…"
          }}
        </p>
      </article>
      <button
        class="button-primary start-processing"
        :disabled="!canStart"
        @click="start"
      >
        <UploadCloud :size="16" />{{
          busy ? "Uploading selected files…" : "Upload & Analyze"
        }}
      </button>
      <p class="upload-note">
        Files upload one at a time. Processing continues in the background;
        originals are retained.
      </p>
    </div>
    <p
      v-for="item in items.filter((row) => row.status === 'accepted')"
      :key="item.key"
      class="accepted-upload"
      role="status"
    >
      {{ item.filename }} —
      {{ item.stored?.reused ? "Existing file reused" : "Upload accepted" }}.
      <RouterLink
        :to="{ name: 'files', query: { file: String(item.stored?.file_id) } }"
        >Open file</RouterLink
      >
    </p>
  </section>
  <SmartOverview v-show="tab === 'review'" :files="history" />
  <section
    v-show="tab === 'activity'"
    class="processing-monitor"
    aria-labelledby="processing-files-heading"
  >
    <header class="panel-heading">
      <h2 id="processing-files-heading">Processing Files</h2>
      <button @click="refresh"><RefreshCw :size="15" />Refresh status</button>
    </header>
    <p class="muted">
      Actual analysis status. Open a file for its results and recommendations.
    </p>
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
      Your processing files will appear here after upload.
    </p>
  </section>
</template>
<style scoped>
.analysis-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 16px;
  margin-bottom: 20px;
  border-bottom: 1px solid #dce5ef;
}
.analysis-tabs button {
  background: transparent;
  border-color: transparent;
  padding: 10px 14px;
}
.analysis-tabs button[aria-pressed="true"] {
  background: #e7f1fc;
  color: #175ac6;
  border-color: #cadff7;
}
.analysis-tabs span {
  font-size: 11px;
  color: #66768c;
}

.upload-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  padding: 0;
  list-style: none;
  margin: 0 0 24px;
}
.upload-steps li {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 13px;
  font-weight: 500;
  color: #53677f;
}
.upload-steps span {
  display: grid;
  place-items: center;
  width: 27px;
  height: 27px;
  background: #e7f1fc;
  border-radius: 50%;
  color: #175ac6;
}
.central-upload,
.processing-monitor {
  padding: clamp(18px, 3vw, 28px);
}
.upload-limits,
.upload-note {
  font-size: 12px;
  color: #66768c;
  line-height: 1.7;
}
.selected-files > p {
  font-size: 13px;
  line-height: 1.7;
}
.selection-card {
  border: 1px solid #dce5ef;
  padding: 18px;
  border-radius: 10px;
  margin: 16px 0;
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
  margin: 0 0 5px;
  overflow-wrap: anywhere;
}
.selection-card small {
  color: #66768c;
  font-size: 12px;
}
.automatic-recipe {
  font-size: 12px;
  color: #66768c;
  line-height: 1.8;
}
.operation-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 20px;
}
.operation-options label {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin: 0;
}
.operation-options input {
  margin: 3px 0 0;
  flex-shrink: 0;
}
.operation-options strong {
  font-size: 13px;
  font-weight: 500;
}
.operation-options small {
  display: block;
  margin-top: 4px;
  line-height: 1.6;
}
.stored-note {
  font-size: 12px;
  color: #315978;
  line-height: 1.7;
}
.accepted-upload {
  color: #23634b;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.start-processing {
  margin-top: 6px;
}
@media (max-width: 650px) {
  .operation-options {
    grid-template-columns: 1fr;
  }
  .upload-steps {
    gap: 10px;
  }
  .upload-steps li {
    font-size: 11px;
  }
}
</style>
