<script setup lang="ts">
import { FileText, Video, Presentation, ArrowUpRight } from "@lucide/vue";
import { visualImageUrl } from "../../services/transcription";
import { ref } from "vue";
const failedImages = ref(new Set<number>());
import { formatTimestamp } from "../../utils/formatTimestamp";
import type { SearchResponse } from "../../types/search";
import EmptyState from "../shared/EmptyState.vue";
defineProps<{ response: SearchResponse }>();
defineEmits<{
  openPage: [fileId: number, pageNumber: number, fileType?: "pdf" | "pptx"];
  openSegment: [fileId: number, segmentId: number, visual?: boolean];
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
          <figure
            v-if="
              result.file_type === 'video' &&
              result.visual &&
              !failedImages.has(result.visual.id)
            "
            class="search-visual"
          >
            <img
              :src="visualImageUrl(result.file_id, result.visual.id)"
              :alt="`Visual shown during the matching passage in ${result.filename}`"
              loading="lazy"
              @error="failedImages.add(result.visual.id)"
            />
            <figcaption>
              Shown {{ formatTimestamp(result.visual.start_ms) }} –
              {{ formatTimestamp(result.visual.end_ms) }}
            </figcaption>
          </figure>
          <!-- Interpolation keeps uploaded content inert, even if it contains HTML. -->
          <p class="result-snippet">{{ result.snippet }}</p>
          <button
            v-if="result.file_type !== 'video'"
            @click="
              $emit(
                'openPage',
                result.file_id,
                result.page_number,
                result.file_type,
              )
            "
          >
            {{
              result.file_type === "pptx"
                ? "View presentation slides"
                : "View extracted page"
            }}
            <ArrowUpRight :size="13" /></button
          ><button
            v-else
            @click="
              $emit(
                'openSegment',
                result.file_id,
                result.segment_id,
                !!result.visual,
              )
            "
          >
            {{
              result.visual
                ? "View visual and matching passage"
                : "View transcript passage"
            }}
            <ArrowUpRight :size="13" />
          </button>
        </div>
      </article>
    </template>
  </div>
</template>

<style scoped>
.search-visual {
  margin: 14px 0;
  max-width: 520px;
}
.search-visual img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid #dce5ef;
  border-radius: 8px;
}
.search-visual figcaption {
  font-size: 12px;
  color: #66768c;
  margin-top: 6px;
}
</style>
