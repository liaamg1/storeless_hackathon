<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import PdfUpload from "../components/files/PdfUpload.vue";
import DocumentDetails from "../components/files/DocumentDetails.vue";
import StorageSavings from "../components/storage/StorageSavings.vue";
import ExtractedPages from "../components/files/ExtractedPages.vue";
import { useDocument } from "../composables/useDocument";

const route = useRoute();
const router = useRouter();
const {
  document,
  selectedPage,
  uploading,
  loadingDocument,
  uploadError,
  documentError,
  uploadSuccess,
  uploadDocument,
  selectDocument,
  clearDocument,
} = useDocument();
let viewIsActive = true;

onBeforeUnmount(() => {
  viewIsActive = false;
  clearDocument();
});

function positiveInteger(value: unknown): number | undefined {
  if (typeof value !== "string") return undefined;
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : undefined;
}

// Watch query changes as well as initial navigation so back/forward restores results.
watch(
  () => [route.query.file, route.query.page],
  () => {
    const fileId = positiveInteger(route.query.file);
    if (fileId) {
      void selectDocument(fileId, positiveInteger(route.query.page));
    } else {
      clearDocument();
    }
  },
  { immediate: true },
);

async function uploadAndOpenDocument(file: File): Promise<void> {
  const result = await uploadDocument(file);
  // A completed upload must not pull users back after they switch to another tab.
  if (result && viewIsActive) {
    await router.push({ name: "extract", query: { file: String(result.id) } });
  }
}
</script>

<template>
  <div>
    <div class="page-intro">
      <div>
        <p class="eyebrow">Processing</p>
        <h1>PDF Extraction</h1>
        <p>
          Upload documents, inspect extracted pages, and follow search matches.
        </p>
      </div>
    </div>
    <PdfUpload
      :uploading="uploading"
      :error="uploadError"
      :success="uploadSuccess"
      @upload="uploadAndOpenDocument"
    />
    <p v-if="loadingDocument" role="status">Loading saved results...</p>
    <p v-else-if="documentError" class="error" role="alert">
      {{ documentError }}
    </p>
    <template v-else-if="document">
      <DocumentDetails :document="document" />
      <StorageSavings :file-id="document.file_id" />
      <ExtractedPages
        v-if="document.pages.length"
        :pages="document.pages"
        :selected-page="selectedPage"
      />
    </template>
    <p v-else>
      Upload a PDF or open a saved file from Files or Document Search to view
      its extracted text.
    </p>
  </div>
</template>
