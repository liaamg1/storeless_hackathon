<script setup lang="ts">
import type { SearchResponse } from "../../types/search";

defineProps<{ response: SearchResponse }>();
defineEmits<{ openPage: [fileId: number, pageNumber: number] }>();
</script>

<template>
  <div>
    <p v-if="response.returned_count === 0" role="status">
      No matching pages found for “{{ response.query }}”. Try different terms or upload a PDF with selectable text.
    </p>
    <template v-else>
      <p role="status">
        Showing {{ response.returned_count }} matching {{ response.returned_count === 1 ? "page" : "pages" }} for “{{ response.query }}”.
      </p>
      <ol class="search-results">
        <li v-for="result in response.results" :key="`${result.file_id}-${result.page_number}`">
          <h3>{{ result.filename }}</h3>
          <p>Page {{ result.page_number }}</p>
          <!-- Text interpolation keeps even HTML found in PDF text inert. -->
          <p class="snippet">{{ result.snippet }}</p>
          <p class="relevance">Relevance score: {{ result.relevance.toPrecision(3) }}</p>
          <button type="button" @click="$emit('openPage', result.file_id, result.page_number)">View page</button>
        </li>
      </ol>
    </template>
  </div>
</template>

<style scoped>
.search-results { list-style: none; padding: 0; }
li { border-top: 1px solid #dce2e9; padding: 16px 0; }
h3 { margin: 0; overflow-wrap: anywhere; }
.snippet { white-space: pre-wrap; overflow-wrap: anywhere; }
.relevance { font-size: 0.85rem; }
</style>
