<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue";
import { useRoute } from "vue-router";
import UploadEntry from "../components/uploads/UploadEntry.vue";
import DocumentDetails from "../components/files/DocumentDetails.vue";
import StorageSavings from "../components/storage/StorageSavings.vue";
import ExtractedPages from "../components/files/ExtractedPages.vue";
import { useDocument } from "../composables/useDocument";

const route = useRoute();
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
</script>

<template>
  <div>
    <div class="page-intro">
      <div>
        <p class="eyebrow">Processing</p>
        <h1>Document text</h1>
        <p>
          Upload documents, inspect extracted pages, and follow search matches.
        </p>
      </div>
    </div>
    <UploadEntry
      description="Add PDFs and choose text extraction, search indexing and optional page comparison in the central upload workflow."
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
