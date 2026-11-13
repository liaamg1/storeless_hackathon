<script setup lang="ts">
import { FileText, Video, Presentation, ArrowUpRight } from "@lucide/vue";
import { formatTimestamp } from "../../utils/formatTimestamp";
import type { SearchResponse } from "../../types/search";
import EmptyState from "../shared/EmptyState.vue";
defineProps<{ response: SearchResponse }>();
defineEmits<{
  openPage: [fileId: number, pageNumber: number];
  openSegment: [fileId: number, segmentId: number];
}>();
</script>
<template>
  <div aria-live="polite">
    <EmptyState
      v-if="response.returned_count === 0"
      title="No matching results"
      description="Try different terms or change the result filter."
    />
    <template v-else
      ><p class="muted" style="font-size: 12px">
        {{ response.returned_count }}
        {{ response.returned_count === 1 ? "result" : "results" }} for “{{
          response.query
        }}”
      </p>
      <article
        v-for="result in response.results"
        :key="`${result.file_type}-${result.file_id}-${result.file_type !== 'video' ? result.page_number : result.segment_id}`"
        class="result-card"
      >
        <span class="file-type-icon" :class="result.file_type"
          ><component
            :is="
              result.file_type === 'video'
                ? Video
                : result.file_type === 'pptx'
                  ? Presentation
                  : FileText
            "
            :size="18"
        /></span>
        <div>
          <div class="result-heading">
            <h3>{{ result.filename }}</h3>
            <span class="result-meta">{{
              result.file_type === "video"
                ? "Video recording"
                : result.file_type === "pptx"
                  ? "PowerPoint presentation"
                  : "PDF document"
            }}</span>
          </div>
          <p class="result-meta">
            {{
              result.file_type !== "video"
                ? `${result.file_type === "pptx" ? "Slide" : "Page"} ${result.page_number}`
                : formatTimestamp(result.start_ms) +
                  " – " +
                  formatTimestamp(result.end_ms)
            }}
          </p>
          <!-- Interpolation keeps uploaded content inert, even if it contains HTML. -->
          <p class="result-snippet">{{ result.snippet }}</p>
          <button
            v-if="result.file_type !== 'video'"
            @click="$emit('openPage', result.file_id, result.page_number)"
          >
            View extracted page <ArrowUpRight :size="13" /></button
          ><button
            v-else
            @click="$emit('openSegment', result.file_id, result.segment_id)"
          >
            View transcript passage <ArrowUpRight :size="13" />
          </button>
        </div>
      </article>
    </template>
  </div>
</template>
