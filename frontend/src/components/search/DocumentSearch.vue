<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useFileUpdates } from "../../composables/useFileUpdates";
import { fetchDocumentSearchResults } from "../../services/search";
import type { SearchResponse } from "../../types/search";
import SearchResults from "./SearchResults.vue";

defineEmits<{
  openPage: [fileId: number, pageNumber: number, fileType?: "pdf" | "pptx"];
  openSegment: [fileId: number, segmentId: number, visual?: boolean];
}>();

const route = useRoute();
const router = useRouter();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
const filter = ref<"all" | "pdf" | "video">(
  route.query.type === "pdf" || route.query.type === "video"
    ? route.query.type
    : "all",
);
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

function syncRouteQuery(): void {
  if (route.name !== "search") return;
  const nextQuery: Record<string, string> = {};
  if (normalizedQuery.value) nextQuery.q = normalizedQuery.value;
  if (filter.value !== "all") nextQuery.type = filter.value;
  if (
    (route.query.q ?? undefined) !== nextQuery.q ||
    (route.query.type ?? undefined) !== nextQuery.type
  ) {
    void router.replace({ name: "search", query: nextQuery });
  }
}

function setFilter(next: "all" | "pdf" | "video"): void {
  filter.value = next;
  syncRouteQuery();
}

async function searchDocuments(syncUrl = true): Promise<void> {
  if (!canSearch.value) return;
  if (syncUrl) syncRouteQuery();
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
  filter.value = "all";
  response.value = null;
  error.value = "";
  loading.value = false;
  if (route.query.q || route.query.type) {
    void router.replace({ name: "search", query: {} });
  }
}

watch(
  () => [route.query.q, route.query.type],
  ([q, type]) => {
    if (route.name !== "search") return;
    filter.value = type === "pdf" || type === "video" ? type : "all";
    const routeQ = typeof q === "string" ? q : "";
    if (routeQ && routeQ !== response.value?.query) {
      query.value = routeQ;
      void searchDocuments(false);
    } else if (!routeQ && response.value) {
      response.value = null;
    }
  },
  { immediate: true },
);

useFileUpdates(() => {
  if (response.value) return searchDocuments(false);
});
onBeforeUnmount(cancelPendingSearch);
</script>

<template>
  <div>
    <div class="page-intro">
      <div>
        <p class="eyebrow">Workspace</p>
        <h1>Search</h1>
        <p>Find the knowledge inside your documents, slides, and recordings.</p>
      </div>
    </div>
    <section aria-labelledby="search-heading" class="search-page-section">
      <h2 id="search-heading">Search your content</h2>
      <form @submit.prevent="searchDocuments(true)">
        <label for="document-search"
          >Search PDFs, presentations, and video transcripts</label
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
          <button v-if="query || response" type="button" @click="clearSearch">
            Clear
          </button>
        </div>
        <p id="search-help">
          Use words, "quoted phrases", OR, or -excluded terms. Shows up to 20
          matching pages, slides, or transcript segments.
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
              ['pdf', 'Documents & slides'],
              ['video', 'Recordings'],
            ] as const"
            :key="option[0]"
            type="button"
            :class="{ active: filter === option[0] }"
            :aria-pressed="filter === option[0]"
            @click="setFilter(option[0])"
          >
            {{ option[1] }}
          </button>
        </div>
        <span v-if="response" class="muted"
          >{{ filteredResponse?.returned_count }} of
          {{ response.returned_count }} matches</span
        >
      </div>
      <p v-if="loading" role="status">Searching documents and recordings...</p>
      <p v-else-if="error" class="error" role="alert">{{ error }}</p>
      <SearchResults
        v-else-if="filteredResponse"
        :response="filteredResponse"
        @open-page="
          (fileId, pageNumber, fileType) =>
            $emit('openPage', fileId, pageNumber, fileType)
        "
        @open-segment="
          (fileId, segmentId, visual) =>
            $emit('openSegment', fileId, segmentId, visual)
        "
      />
      <p v-if="response && filter !== 'all'" class="muted search-filter-note">
        Filters apply to the current set of up to 20 returned matches.
      </p>
      <p v-if="!response && !loading && !error" class="search-start">
        Enter a query to search your saved PDF pages, PowerPoint slides, and video
        transcripts.
      </p>
    </section>
  </div>
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
