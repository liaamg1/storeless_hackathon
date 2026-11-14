<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  X,
  FileText,
  Video,
  Presentation,
  Copy,
  ArrowUpRight,
  ChartNoAxesColumn,
  RefreshCw,
} from "@lucide/vue";
import type { WorkspaceFile } from "../../utils/files";
import { fileDestination, formatDate } from "../../utils/files";
import { formatBytes } from "../../utils/formatBytes";
import { getDocumentPages } from "../../services/api";
import { getStorageSavings } from "../../services/storage";
import { getTranscript } from "../../services/transcription";
import { getFileProcessing, processStoredFile } from "../../services/uploads";
import { notifyFilesChanged } from "../../utils/fileUpdates";
import { recommendedOperations } from "../../utils/upload";
import type { DocumentDetails } from "../../types/document";
import type { StorageSavings } from "../../types/storage";
import type { VideoTranscript } from "../../types/transcription";
import type { ProcessingFile, UploadKind } from "../../types/upload";
import StatusBadge from "../shared/StatusBadge.vue";
import ProcessingFileCard from "../uploads/ProcessingFileCard.vue";

const props = defineProps<{ file: WorkspaceFile }>();
const emit = defineEmits<{ close: [] }>();
const router = useRouter();
const dialog = ref<HTMLDialogElement | null>(null);
const copyMessage = ref("");
const pdfDetails = ref<DocumentDetails | null>(null);
const pdfStatus = ref("");
const transcriptPreview = ref<VideoTranscript | null>(null);
const storagePreview = ref<StorageSavings | null>(null);
const processing = ref<ProcessingFile | null>(props.file.processing ?? null);
const runningAnalysis = ref(false);
const actionFeedback = ref("");
const actionError = ref("");

watch(
  () => props.file.processing,
  (value) => {
    if (value) processing.value = value;
  },
);

const effectiveStatus = computed(
  () => processing.value?.status ?? props.file.status,
);
const isBusy = computed(
  () =>
    runningAnalysis.value ||
    effectiveStatus.value === "queued" ||
    effectiveStatus.value === "processing",
);
const transcriptWordCount = computed(() =>
  (transcriptPreview.value?.segments ?? []).reduce(
    (sum, s) => sum + (s.text.trim().match(/\S+/g)?.length ?? 0),
    0,
  ),
);
const transcriptExcerpt = computed(() => {
  const text = (transcriptPreview.value?.segments ?? [])
    .map((s) => s.text.trim())
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ");
  return text.length > 260 ? text.slice(0, 260) + "…" : text;
});
const pdfExcerpt = computed(() => {
  const firstWithText = pdfDetails.value?.pages.find((p) =>
    p.text.trim().length > 0,
  );
  if (!firstWithText) return "";
  const text = firstWithText.text.trim().replace(/\s+/g, " ");
  return text.length > 260 ? text.slice(0, 260) + "…" : text;
});

let active = true;
let pollTimer: ReturnType<typeof setTimeout> | undefined;

async function loadInlinePreviews(): Promise<void> {
  if (!active) return;
  if (props.file.type === "pdf") {
    pdfStatus.value = "Checking extraction…";
    try {
      const result = await getDocumentPages(props.file.id);
      if (active) {
        pdfDetails.value = result;
        pdfStatus.value =
          result.status === "completed"
            ? `${result.page_count} extracted pages`
            : "No extracted pages stored";
      }
    } catch {
      if (active) pdfStatus.value = "Extraction status unavailable";
    }
  }
  if (props.file.type === "video") {
    try {
      const result = await getTranscript(props.file.id);
      if (active) transcriptPreview.value = result;
    } catch {
      // Transcript may still be processing or not yet generated
    }
  }
  if (props.file.type === "video" || props.file.type === "pdf") {
    try {
      const savings = await getStorageSavings(props.file.id);
      if (active) storagePreview.value = savings;
    } catch {
      // Storage measurement unavailable
    }
  }
}

async function pollProcessing(): Promise<void> {
  clearTimeout(pollTimer);
  if (!active || props.file.type === "other") return;
  try {
    const result = await getFileProcessing(props.file.id);
    if (!active) return;
    const wasActive =
      processing.value?.status === "queued" ||
      processing.value?.status === "processing";
    processing.value = result;
    if (result.status === "queued" || result.status === "processing") {
      pollTimer = setTimeout(() => void pollProcessing(), 1500);
    } else if (wasActive) {
      actionFeedback.value =
        result.status === "completed"
          ? "Analysis completed."
          : "Analysis finished with errors.";
      notifyFilesChanged();
      void loadInlinePreviews();
    }
  } catch {
    // Keep existing processing state if polling fails
  }
}

onMounted(() => {
  dialog.value?.showModal();
  void pollProcessing();
  void loadInlinePreviews();
});

onBeforeUnmount(() => {
  active = false;
  clearTimeout(pollTimer);
  dialog.value?.close();
});

async function copyHash(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.file.sha256);
    copyMessage.value = "Hash copied";
  } catch {
    copyMessage.value =
      "Copy unavailable. You can select and copy the hash below.";
  }
}

async function navigateTo(
  name: string,
  extraQuery: Record<string, string> = {},
): Promise<void> {
  dialog.value?.close();
  await router.push({
    name,
    query: { file: String(props.file.id), ...extraQuery },
  });
}

async function openResult(): Promise<void> {
  dialog.value?.close();
  await router.push(fileDestination(props.file));
}

async function runOrUpdate(): Promise<void> {
  if (props.file.type === "other" || runningAnalysis.value) return;
  runningAnalysis.value = true;
  actionFeedback.value = "";
  actionError.value = "";
  try {
    const ops = recommendedOperations(props.file.type as UploadKind);
    const updated = await processStoredFile(props.file.id, ops);
    if (!active) return;
    processing.value = updated;
    notifyFilesChanged();
    if (updated.status === "queued" || updated.status === "processing") {
      actionFeedback.value = "Analysis started — updating progress below…";
      pollTimer = setTimeout(() => void pollProcessing(), 1200);
    } else if (updated.status === "completed") {
      actionFeedback.value = "All checks are complete and up to date.";
      void loadInlinePreviews();
    } else {
      actionError.value =
        updated.error_message || "Analysis could not complete.";
    }
  } catch (error) {
    if (active) {
      actionError.value =
        error instanceof Error
          ? error.message
          : "Could not start or update analysis.";
    }
  } finally {
    if (active) runningAnalysis.value = false;
  }
}

function formatReduction(percent: number): string {
  const mag = Math.abs(percent);
  if (mag > 0 && mag < 0.01) return "<0.01%";
  return (Math.floor(mag * 100) / 100).toFixed(2) + "%";
}
</script>
<template>
  <dialog
    ref="dialog"
    class="file-drawer"
    aria-labelledby="file-drawer-heading"
    @cancel.prevent="$emit('close')"
    @click="
      (event) => {
        if (event.target === dialog) $emit('close');
      }
    "
  >
    <header class="drawer-header">
      <p class="eyebrow">File #{{ file.id }}</p>
      <button
        class="icon-button"
        aria-label="Close file details"
        @click="$emit('close')"
      >
        <X :size="19" />
      </button>
    </header>

    <div class="drawer-hero">
      <span class="file-type-icon drawer-file-icon" :class="file.type">
        <component
          :is="
            file.type === 'video'
              ? Video
              : file.type === 'pptx'
                ? Presentation
                : FileText
          "
          :size="26"
        />
      </span>
      <div>
        <h2 id="file-drawer-heading" class="break-word">{{ file.filename }}</h2>
        <div class="drawer-badges">
          <StatusBadge :status="effectiveStatus" />
          <span class="muted" style="font-size: 12px">
            {{ formatBytes(file.size_bytes) }} ·
            {{ formatDate(file.uploaded_at) }}
          </span>
        </div>
      </div>
    </div>

    <div class="drawer-actions" style="margin-top: 18px">
      <template v-if="file.type === 'video'">
        <button type="button" class="button-primary" @click="openResult">
          <Video :size="16" />Open Transcript<ArrowUpRight :size="15" />
        </button>
        <button
          type="button"
          @click="navigateTo('transcription', { view: 'visual' })"
        >
          <Presentation :size="16" />Visual Transcript<ArrowUpRight :size="15" />
        </button>
        <button type="button" @click="navigateTo('storage')">
          <ChartNoAxesColumn :size="16" />View Storage Comparison<ArrowUpRight
            :size="15"
          />
        </button>
      </template>

      <template v-else-if="file.type === 'pdf'">
        <button
          type="button"
          class="button-primary"
          @click="navigateTo('extract')"
        >
          <FileText :size="16" />Open Document Text<ArrowUpRight :size="15" />
        </button>
        <button type="button" @click="navigateTo('slides')">
          <Presentation :size="16" />Compare Slides<ArrowUpRight :size="15" />
        </button>
        <button type="button" @click="navigateTo('storage')">
          <ChartNoAxesColumn :size="16" />View Storage Comparison<ArrowUpRight
            :size="15"
          />
        </button>
      </template>

      <template v-else-if="file.type === 'pptx'">
        <button
          type="button"
          class="button-primary"
          @click="navigateTo('slides')"
        >
          <Presentation :size="16" />Compare Slides<ArrowUpRight :size="15" />
        </button>
      </template>

      <button
        v-if="file.type !== 'other'"
        type="button"
        :disabled="runningAnalysis"
        @click="runOrUpdate"
      >
        <RefreshCw :size="16" :class="{ spin: isBusy }" />{{
          runningAnalysis
            ? "Starting analysis…"
            : effectiveStatus === "failed"
              ? "Retry Analysis"
              : "Run or Update"
        }}
      </button>
    </div>

    <p
      v-if="actionFeedback"
      class="notice"
      role="status"
      style="margin-top: 12px"
    >
      {{ actionFeedback }}
    </p>
    <p
      v-if="actionError"
      class="notice error"
      role="alert"
      style="margin-top: 12px"
    >
      {{ actionError }}
    </p>

    <div
      v-if="
        transcriptPreview ||
        (pdfDetails && pdfDetails.status === 'completed') ||
        (storagePreview && storagePreview.status === 'completed')
      "
      class="drawer-summary-grid"
    >
      <div
        v-if="
          storagePreview &&
          storagePreview.status === 'completed' &&
          storagePreview.optimized_size_bytes !== null &&
          storagePreview.reduction_percent !== null
        "
        class="drawer-summary-card"
      >
        <div class="summary-card-head">
          <strong>Storage comparison</strong>
          <span
            class="summary-pill"
            :class="{ positive: (storagePreview.storage_saved_bytes ?? 0) > 0 }"
          >
            {{
              (storagePreview.storage_saved_bytes ?? 0) >= 0
                ? `${formatReduction(storagePreview.reduction_percent)} smaller`
                : `${formatReduction(storagePreview.reduction_percent)} larger`
            }}
          </span>
        </div>
        <p class="muted" style="font-size: 12px; margin: 4px 0 8px">
          Original {{ formatBytes(storagePreview.original_size_bytes) }} →
          Optimized {{ formatBytes(storagePreview.optimized_size_bytes) }}
        </p>
        <button
          type="button"
          class="inline-link-btn"
          @click="navigateTo('storage')"
        >
          Open full storage breakdown →
        </button>
      </div>

      <div v-if="transcriptPreview" class="drawer-summary-card">
        <div class="summary-card-head">
          <strong>Transcript preview</strong>
          <span class="muted" style="font-size: 12px">
            {{ transcriptWordCount }} words ·
            {{ transcriptPreview.segments.length }} segments
          </span>
        </div>
        <p v-if="transcriptExcerpt" class="summary-excerpt">
          “{{ transcriptExcerpt }}”
        </p>
        <p v-else class="muted" style="font-size: 12px">
          No spoken words detected in this recording.
        </p>
        <button type="button" class="inline-link-btn" @click="openResult">
          Read full transcript →
        </button>
      </div>

      <div
        v-if="pdfDetails && pdfDetails.status === 'completed'"
        class="drawer-summary-card"
      >
        <div class="summary-card-head">
          <strong>Extracted document text</strong>
          <span class="muted" style="font-size: 12px">
            {{ pdfDetails.page_count }}
            {{ pdfDetails.page_count === 1 ? "page" : "pages" }}
          </span>
        </div>
        <p v-if="pdfExcerpt" class="summary-excerpt">“{{ pdfExcerpt }}”</p>
        <button
          type="button"
          class="inline-link-btn"
          @click="navigateTo('extract')"
        >
          Read extracted pages →
        </button>
      </div>
    </div>

    <ProcessingFileCard
      v-if="processing?.steps.length"
      :file="processing"
      detail
      @updated="
        processing = $event;
        void loadInlinePreviews();
      "
    />

    <details class="drawer-block">
      <summary style="cursor: pointer; font-weight: 600; font-size: 13px">
        Technical metadata &amp; SHA-256
      </summary>
      <dl class="drawer-metadata" style="margin: 14px 0">
        <dt>Exact size</dt>
        <dd>{{ file.size_bytes.toLocaleString() }} bytes</dd>
        <template v-if="pdfStatus">
          <dt>Extraction</dt>
          <dd>{{ pdfStatus }}</dd>
        </template>
        <template v-if="file.video?.duration_ms != null">
          <dt>Duration</dt>
          <dd>{{ Math.round(file.video.duration_ms / 1000) }} seconds</dd>
        </template>
      </dl>
      <div class="panel-heading">
        <h3>SHA-256 checksum</h3>
        <button
          class="icon-button"
          aria-label="Copy SHA-256 hash"
          @click="copyHash"
        >
          <Copy :size="16" />
        </button>
      </div>
      <code class="full-hash">{{ file.sha256 }}</code>
      <p v-if="copyMessage" class="muted" role="status">{{ copyMessage }}</p>
    </details>

    <p class="drawer-retained">
      <span class="live-dot" />Original file retained
    </p>
  </dialog>
</template>
<style scoped>
.drawer-hero {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.drawer-hero > div {
  flex: 1;
  min-width: 0;
}
.drawer-file-icon {
  margin: 0;
  flex-shrink: 0;
}
.drawer-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}
.drawer-summary-grid {
  display: grid;
  gap: 10px;
  margin: 16px 0;
}
.drawer-summary-card {
  border: 1px solid #dce5ef;
  border-radius: 8px;
  padding: 12px 14px;
  background: #f9fbfe;
}
.summary-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}
.summary-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  background: #edf2f8;
  color: #53677f;
}
.summary-pill.positive {
  background: #eaf7f0;
  color: #23634b;
}
.summary-excerpt {
  font-size: 12px;
  color: #33445b;
  line-height: 1.55;
  margin: 6px 0 8px;
  overflow-wrap: anywhere;
}
.inline-link-btn {
  border: 0;
  background: transparent;
  color: #0065bf;
  padding: 0;
  min-height: 0;
  font-size: 12px;
  font-weight: 600;
}
.inline-link-btn:hover {
  background: transparent;
  text-decoration: underline;
}
</style>
