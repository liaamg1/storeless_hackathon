<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { fetchDocumentSearchResults } from "../../services/search";
import type { SearchResponse } from "../../types/search";
import SearchResults from "./SearchResults.vue";

defineEmits<{
  openPage: [fileId: number, pageNumber: number];
  openSegment: [fileId: number, segmentId: number];
}>();

const query = ref("");
const response = ref<SearchResponse | null>(null);
const loading = ref(false);
const error = ref("");
const normalizedQuery = computed(() => query.value.trim().replace(/\s+/g, " "));
const canSearch = computed(() => normalizedQuery.value.length > 0 && query.value.length <= 200);
let requestVersion = 0;
let controller: AbortController | null = null;

function cancelPendingSearch(): void {
  requestVersion += 1;
  controller?.abort();
  controller = null;
}

async function searchDocuments(): Promise<void> {
  if (!canSearch.value) return;
  cancelPendingSearch();
  const version = requestVersion;
  controller = new AbortController();
  loading.value = true;
  error.value = "";
  response.value = null;
  try {
    const results = await fetchDocumentSearchResults(normalizedQuery.value, controller.signal);
    // Aborting saves work; the version check also protects against late responses.
    if (version === requestVersion) response.value = results;
  } catch (failure) {
    if (version === requestVersion) {
      error.value = failure instanceof Error ? failure.message : "Could not search documents.";
    }
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}

function clearSearch(): void {
  cancelPendingSearch();
  query.value = "";
  response.value = null;
  error.value = "";
  loading.value = false;
}

onBeforeUnmount(cancelPendingSearch);
</script>

<template>
  <section aria-labelledby="search-heading">
    <h2 id="search-heading">Search documents and recordings</h2>
    <form @submit.prevent="searchDocuments">
      <label for="document-search">Search PDF text and video transcripts</label>
      <div class="search-controls">
        <input
          id="document-search" v-model="query" type="search" maxlength="200"
          placeholder="network architecture" aria-describedby="search-help"
        />
        <button type="submit" :disabled="!canSearch">Search</button>
        <button type="button" @click="clearSearch">Clear</button>
      </div>
      <p id="search-help">
        Use words, "quoted phrases", OR, or -excluded terms. Shows up to 20 matching pages or transcript segments.
      </p>
    </form>
    <p v-if="loading" role="status">Searching documents and recordings...</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
    <SearchResults
      v-else-if="response" :response="response"
      @open-page="(fileId, pageNumber) => $emit('openPage', fileId, pageNumber)"
      @open-segment="(fileId, segmentId) => $emit('openSegment', fileId, segmentId)"
    />
    <p v-else>Enter a query to search your saved PDF text and video transcripts.</p>
  </section>
</template>

<style scoped>
.search-controls { display: flex; flex-wrap: wrap; gap: 8px; }
input { flex: 1; min-width: 180px; padding: 8px; border: 1px solid #aab7c7; border-radius: 4px; }
#search-help { font-size: 0.9rem; }
</style>
