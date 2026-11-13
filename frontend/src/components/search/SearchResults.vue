<script setup lang="ts">
import { formatTimestamp } from "../../utils/formatTimestamp";
import type { SearchResponse } from "../../types/search";

defineProps<{ response: SearchResponse }>();
defineEmits<{
  openPage: [fileId: number, pageNumber: number];
  openSegment: [fileId: number, segmentId: number];
}>();
</script>

<template>
  <div>
    <p v-if="response.returned_count === 0" role="status">
      No matches found for “{{ response.query }}”. Try different terms or upload a PDF with selectable text or transcribe an MP4 recording.
    </p>
    <template v-else>
      <p role="status">
        Showing {{ response.returned_count }} {{ response.returned_count === 1 ? "match" : "matches" }} for “{{ response.query }}”.
      </p>
      <ol class="search-results">
        <li v-for="result in response.results" :key="`${result.file_type}-${result.file_id}-${result.file_type === 'pdf' ? result.page_number : result.segment_id}`">
          <h3>{{ result.filename }}</h3>
          <p v-if="result.file_type === 'pdf'">PDF · Page {{ result.page_number }}</p>
          <p v-else>Video · {{ formatTimestamp(result.start_ms) }} – {{ formatTimestamp(result.end_ms) }}</p>
          <!-- Text interpolation keeps even HTML found in stored text inert. -->
          <p class="snippet">{{ result.snippet }}</p>
          <p class="relevance">Relevance score: {{ result.relevance.toPrecision(3) }}</p>
          <button v-if="result.file_type === 'pdf'" type="button" @click="$emit('openPage', result.file_id, result.page_number)">View page</button>
          <button v-else type="button" @click="$emit('openSegment', result.file_id, result.segment_id)">View transcript segment</button>
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
