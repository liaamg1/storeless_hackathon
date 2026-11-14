<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  X,
  FileText,
  Video,
  Copy,
  ArrowUpRight,
  ChartNoAxesColumn,
  Activity,
} from "@lucide/vue";
import type { WorkspaceFile } from "../../utils/files";
import { fileDestination, formatDate } from "../../utils/files";
import { formatBytes } from "../../utils/formatBytes";
import { getDocumentPages } from "../../services/api";
import StatusBadge from "../shared/StatusBadge.vue";
import ProcessingFileCard from "../uploads/ProcessingFileCard.vue";
import { getFileProcessing } from "../../services/uploads";
import type { ProcessingFile } from "../../types/upload";
const props = defineProps<{ file: WorkspaceFile }>();
const emit = defineEmits<{ close: [] }>();
const router = useRouter();
const dialog = ref<HTMLDialogElement | null>(null);
const copyMessage = ref("");
const pdfStatus = ref("");
const processing = ref<ProcessingFile | null>(props.file.processing ?? null);
watch(
  () => props.file.processing,
  (value) => {
    if (value) processing.value = value;
  },
);
let active = true;
onMounted(async () => {
  dialog.value?.showModal();
  if (props.file.type !== "other") {
    void getFileProcessing(props.file.id)
      .then((result) => {
        if (active) processing.value = result;
      })
      .catch(() => {});
  }
  if (props.file.type === "pdf") {
    pdfStatus.value = "Checking extraction…";
    try {
      const result = await getDocumentPages(props.file.id);
      if (active)
        pdfStatus.value =
          result.status === "completed"
            ? `${result.page_count} extracted pages`
            : "No extracted pages stored";
    } catch {
      if (active) pdfStatus.value = "Extraction status unavailable";
    }
  }
});
onBeforeUnmount(() => {
  active = false;
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
function openResult(): void {
  void router.push(fileDestination(props.file));
  emit("close");
}
function openProcessing(): void {
  void router.push({
    name: "transcription",
    query: { file: String(props.file.id), view: "status" },
  });
  emit("close");
}
function openSlides(): void {
  void router.push({ name: "slides", query: { file: String(props.file.id) } });
  emit("close");
}
function openStorage(): void {
  void router.push({ name: "storage", query: { file: String(props.file.id) } });
  emit("close");
}
function chooseProcessing(): void {
  void router.push({ name: "upload", query: { file: String(props.file.id) } });
  emit("close");
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
      <p class="eyebrow">File details</p>
      <button
        class="icon-button"
        aria-label="Close file details"
        @click="$emit('close')"
      >
        <X :size="19" />
      </button>
    </header>
    <span class="file-type-icon drawer-file-icon" :class="file.type"
      ><component :is="file.type === 'video' ? Video : FileText" :size="28"
    /></span>
    <h2 id="file-drawer-heading" class="break-word">{{ file.filename }}</h2>
    <StatusBadge :status="file.status" />
    <div v-if="processing?.steps.length" class="drawer-actions">
      <button class="button-primary" @click="openResult">
        <ArrowUpRight :size="16" />{{
          file.type === "video" ? "Open transcript" : "Open slides"
        }}
      </button>
    </div>
    <dl class="drawer-metadata">
      <dt>File type</dt>
      <dd>
        {{
          file.type === "video"
            ? "MP4 recording"
            : file.type === "pdf"
              ? "PDF document"
              : file.type === "pptx"
                ? "PPTX presentation"
                : "File"
        }}
      </dd>
      <dt>Size</dt>
      <dd>
        {{ formatBytes(file.size_bytes)
        }}<small>{{ file.size_bytes.toLocaleString() }} bytes</small>
      </dd>
      <dt>Uploaded</dt>
      <dd>{{ formatDate(file.uploaded_at) }}</dd>
      <dt>File ID</dt>
      <dd>#{{ file.id }}</dd>
      <template v-if="pdfStatus"
        ><dt>Extraction</dt>
        <dd>{{ pdfStatus }}</dd></template
      ><template v-if="file.video?.duration_ms != null"
        ><dt>Duration</dt>
        <dd>
          {{ Math.round(file.video.duration_ms / 1000) }} seconds
        </dd></template
      >
    </dl>
    <div class="drawer-block">
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
    </div>
    <ProcessingFileCard
      v-if="processing?.steps.length"
      :file="processing"
      detail
    />
    <div v-if="processing?.steps.length" class="drawer-actions">
      <button
        v-if="file.type === 'pdf' && !processing.operations.includes('slides')"
        @click="openSlides"
      >
        <FileText :size="16" />Compare slides
      </button>
      <button
        v-if="
          file.type === 'video' && !processing.operations.includes('storage')
        "
        @click="openStorage"
      >
        <ChartNoAxesColumn :size="16" />View storage comparison
      </button>
    </div>
    <button
      v-if="file.type !== 'other'"
      class="button-primary"
      @click="chooseProcessing"
    >
      Analyze this file
    </button>
    <div v-if="!processing?.steps.length" class="drawer-block">
      <h3>Available results</h3>
      <div class="drawer-actions">
        <button class="button-primary" @click="openResult">
          <component
            :is="file.type === 'video' ? Video : FileText"
            :size="16"
          />{{
            file.type === "video"
              ? "View transcript"
              : file.type === "pptx"
                ? "View slides"
                : "View slides"
          }}<ArrowUpRight :size="15" /></button
        ><button v-if="file.type === 'video'" @click="openProcessing">
          <Activity :size="16" />View processing status</button
        ><button v-if="file.type === 'pdf'" @click="openSlides">
          <FileText :size="16" />Compare slides</button
        ><button @click="openStorage">
          <ChartNoAxesColumn :size="16" />View storage comparison
        </button>
      </div>
    </div>
    <p class="drawer-retained">
      <span class="live-dot" />Original file retained
    </p>
  </dialog>
</template>
