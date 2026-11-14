<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import {
  FileText,
  Presentation,
  ChartNoAxesColumn,
  RefreshCw,
} from "@lucide/vue";
import UploadEntry from "../components/uploads/UploadEntry.vue";
import DocumentDetails from "../components/files/DocumentDetails.vue";
import StorageSavings from "../components/storage/StorageSavings.vue";
import ExtractedPages from "../components/files/ExtractedPages.vue";
import EmptyState from "../components/shared/EmptyState.vue";
import { useDocument } from "../composables/useDocument";
import { useWorkspace } from "../composables/useWorkspace";
import { processStoredFile } from "../services/uploads";
import { notifyFilesChanged } from "../utils/fileUpdates";
import { recommendedOperations } from "../utils/upload";

const route = useRoute();
const router = useRouter();
const { files } = useWorkspace();
const pdfFiles = computed(() =>
  files.value.filter((file) => file.type === "pdf"),
);
const selectedFileId = computed(() => positiveInteger(route.query.file) ?? 0);
const running = ref(false);
const actionError = ref("");
const {
  document,
  selectedPage,
  loadingDocument,
  documentError,
  selectDocument,
  clearDocument,
} = useDocument();

onBeforeUnmount(() => {
  clearDocument();
});

function positiveInteger(value: unknown): number | undefined {
  if (typeof value !== "string") return undefined;
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : undefined;
}

function choosePdf(event: Event): void {
  const value = (event.target as HTMLSelectElement).value;
  void router.push({
    name: "extract",
    query: value ? { file: value } : {},
  });
}

async function runOrUpdatePdf(): Promise<void> {
  if (!selectedFileId.value || running.value) return;
  running.value = true;
  actionError.value = "";
  try {
    await processStoredFile(
      selectedFileId.value,
      recommendedOperations("pdf"),
    );
    notifyFilesChanged();
    await selectDocument(
      selectedFileId.value,
      positiveInteger(route.query.page),
    );
  } catch (error) {
    actionError.value =
      error instanceof Error
        ? error.message
        : "Could not run or update PDF analysis.";
  } finally {
    running.value = false;
  }
}

// Watch query changes as well as initial navigation so back/forward restores results.
watch(
  () => [route.query.file, route.query.page],
  () => {
    if (route.name !== "extract") return;
    const fileId = positiveInteger(route.query.file);
    if (fileId) {
      void selectDocument(fileId, positiveInteger(route.query.page));
    } else {
      clearDocument();
    }
  },
  { immediate: true },
);
</script>

<template>
  <div>
    <div class="page-intro">
      <div>
        <p class="eyebrow">Processing</p>
        <h1>Document text</h1>
        <p>Inspect extracted PDF pages and search matches.</p>
      </div>
    </div>
    <UploadEntry
      v-if="!document"
      description="Upload PDFs in the workspace to extract page text, index for search, and compare slides."
    />
    <section v-if="pdfFiles.length || selectedFileId">
      <div class="storage-picker">
        <FileText :size="20" class="muted" />
        <label for="pdf-file-picker">Document</label>
        <select
          id="pdf-file-picker"
          :value="selectedFileId || ''"
          @change="choosePdf"
        >
          <option value="">Select a saved PDF…</option>
          <option v-for="file in pdfFiles" :key="file.id" :value="file.id">
            {{ file.filename }}
          </option>
        </select>
        <template v-if="selectedFileId">
          <RouterLink
            class="picker-btn"
            :to="{ name: 'slides', query: { file: String(selectedFileId) } }"
          >
            <Presentation :size="15" />Compare Slides
          </RouterLink>
          <RouterLink
            class="picker-btn"
            :to="{ name: 'storage', query: { file: String(selectedFileId) } }"
          >
            <ChartNoAxesColumn :size="15" />View Storage Comparison
          </RouterLink>
          <button
            type="button"
            :disabled="running"
            @click="runOrUpdatePdf"
          >
            <RefreshCw :size="15" :class="{ spin: running }" />
            {{ running ? "Running…" : "Run or Update" }}
          </button>
        </template>
      </div>
      <p v-if="actionError" class="error" role="alert" style="margin-top: 8px">
        {{ actionError }}
      </p>
    </section>
    <p v-if="loadingDocument" role="status">Loading saved results...</p>
    <p v-else-if="documentError" class="error" role="alert">
      {{ documentError }}
    </p>
    <template v-else-if="document">
      <DocumentDetails :document="document" />
      <ExtractedPages
        v-if="document.pages.length"
        :pages="document.pages"
        :selected-page="selectedPage"
      />
      <details class="secondary-details">
        <summary>
          Potential storage savings<span class="muted"
            >Original vs extracted text</span
          >
        </summary>
        <StorageSavings :file-id="document.file_id" />
      </details>
    </template>
    <EmptyState
      v-else
      title="Select a PDF document"
      description="Choose a saved PDF above or open one from Files or Search to inspect its extracted page text."
    />
  </div>
</template>
<style scoped>
.picker-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: 5px;
  border: 1px solid #d7dee8;
  background: #fff;
  color: #33445b;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}
.picker-btn:hover {
  background: #f1f5fa;
  border-color: #b5c7da;
  text-decoration: none;
}
</style>
