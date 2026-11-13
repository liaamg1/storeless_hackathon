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
const filter = ref<"all" | "pdf" | "video">("all");
const filteredResponse = computed(() => {
  if (!response.value) return null;
  const results = response.value.results.filter(
    (result) =>
      filter.value === "all" ||
      (filter.value === "pdf"
        ? result.file_type !== "video"
        : result.file_type === "video"),
  );
  return { ...response.value, results, returned_count: results.length };
});
const response = ref<SearchResponse | null>(null);
const loading = ref(false);
const error = ref("");
const normalizedQuery = computed(() => query.value.trim().replace(/\s+/g, " "));
const canSearch = computed(
  () => normalizedQuery.value.length > 0 && query.value.length <= 200,
);
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
    const results = await fetchDocumentSearchResults(
      normalizedQuery.value,
      controller.signal,
    );
    // Aborting saves work; the version check also protects against late responses.
    if (version === requestVersion) response.value = results;
  } catch (failure) {
    if (version === requestVersion) {
      error.value =
        failure instanceof Error
          ? failure.message
          : "Could not search documents.";
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
  <div class="page-intro">
    <div>
      <p class="eyebrow">Workspace</p>
      <h1>Search</h1>
      <p>Find the knowledge inside your documents and recordings.</p>
    </div>
  </div>
  <section aria-labelledby="search-heading" class="search-page-section">
    <h2 id="search-heading">Search your content</h2>
    <form @submit.prevent="searchDocuments">
      <label for="document-search"
        >Search document text and video transcripts</label
      >
      <div class="search-controls">
        <input
          id="document-search"
          v-model="query"
          type="search"
          maxlength="200"
          placeholder="Search words or phrases across your workspace…"
          autofocus
          aria-describedby="search-help"
        />
        <button
          class="button-primary"
          type="submit"
          :disabled="!canSearch || loading"
        >
          {{ loading ? "Searching…" : "Search" }}
        </button>
        <button type="button" @click="clearSearch">Clear</button>
      </div>
      <p id="search-help">
        Use words, "quoted phrases", OR, or -excluded terms. Shows up to 20
        matching pages or transcript segments.
      </p>
    </form>
    <div class="search-filter-row">
      <div
        class="segmented-control"
        role="group"
        aria-label="Filter search results"
      >
        <button
          v-for="option in [
            ['all', 'All'],
            ['pdf', 'Documents'],
            ['video', 'Recordings'],
          ] as const"
          :key="option[0]"
          :class="{ active: filter === option[0] }"
          :aria-pressed="filter === option[0]"
          @click="filter = option[0]"
        >
          {{ option[1] }}
        </button>
      </div>
      <span v-if="response" class="muted"
        >{{ filteredResponse?.returned_count }} of
        {{ response.returned_count }} returned matches</span
      >
    </div>
    <p v-if="loading" role="status">Searching documents and recordings...</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
    <SearchResults
      v-else-if="filteredResponse"
      :response="filteredResponse"
      @open-page="(fileId, pageNumber) => $emit('openPage', fileId, pageNumber)"
      @open-segment="
        (fileId, segmentId) => $emit('openSegment', fileId, segmentId)
      "
    />
    <p v-if="response && filter !== 'all'" class="muted search-filter-note">
      Filters apply to the current set of up to 20 returned matches.
    </p>
    <p v-if="!response && !loading && !error" class="search-start">
      Enter a query to search your saved PDF text and video transcripts.
    </p>
  </section>
</template>

<style scoped>
.search-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
input {
  flex: 1;
  font-size: 15px;
  min-height: 44px;
  min-width: 180px;
  padding: 8px;
  border: 1px solid #aab7c7;
  border-radius: 4px;
}
#search-help {
  font-size: 12px;
  color: #66768c;
  margin-top: 12px;
}
.search-filter-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  padding: 16px 0;
  border-top: 1px solid #e1e6ed;
  font-size: 12px;
}
.search-start {
  padding: 28px 0;
  color: #66768c;
  text-align: center;
}
.search-filter-note {
  font-size: 12px;
  margin-top: 15px;
}
</style>
