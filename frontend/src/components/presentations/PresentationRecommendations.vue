<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import type {
  PresentationComparison,
  PresentationRecord,
} from "../../types/presentation";
import { presentationRecommendations } from "../../utils/recommendations";
import RecommendationPanel from "../shared/RecommendationPanel.vue";

const props = defineProps<{
  comparison: PresentationComparison;
  records: PresentationRecord[];
}>();
const recommendations = computed(() =>
  presentationRecommendations(props.comparison, props.records),
);
const expanded = ref(false);
watch(
  () => props.comparison.presentation.file_id,
  () => {
    expanded.value = false;
  },
);
const visible = computed(() =>
  expanded.value ? recommendations.value : recommendations.value.slice(0, 5),
);
const score = (value: number) =>
  value.toLocaleString(undefined, { maximumFractionDigits: 2 });
</script>
<template>
  <RecommendationPanel
    title="Presentation recommendations"
    description="Recommendations separate whole-presentation coverage from individual slide matches. A visual score measures appearance, not identical file content."
  >
    <div v-if="recommendations.length" class="recommendation-list">
      <article
        v-for="item in visible"
        :key="item.candidate.id"
        class="recommendation-item"
      >
        <span
          class="recommendation-badge"
          :class="
            item.basis === 'exact'
              ? 'exact'
              : item.basis === 'similar'
                ? 'review'
                : ''
          "
          >{{
            item.basis === "exact"
              ? "All slides covered by exact matches"
              : item.basis === "similar"
                ? "High visual similarity · review required"
                : "Partial overlap · retain unmatched content"
          }}</span
        >
        <h3>
          {{
            item.remove
              ? "Review for removal: " + item.remove.filename
              : "Review overlap with " + item.candidate.filename
          }}
        </h3>
        <p v-if="item.remove">
          Suggested copy to retain:
          <span class="recommendation-file">{{ item.keep.filename }}</span>
          (File #{{ item.keep.id }}).
        </p>
        <div class="recommendation-evidence">
          <span
            >{{ item.matchedSlides }} / {{ item.totalSlides }} selected slides
            match this presentation</span
          ><span
            >{{ score(item.coveragePercent) }}% selected-slide coverage</span
          ><span
            >{{ score(item.averageSimilarity) }}% average visual score</span
          >
        </div>
        <p v-if="item.action === 'review_overlap'">
          This pair provides additional overlap evidence. Follow the
          higher-priority keep/removal recommendation above; this comparison
          adds no further deletion candidate.
        </p>
        <p v-else-if="item.basis === 'exact'">
          Every slide in the proposed removal candidate has an exact normalized
          rendering and text match in the proposed retained presentation. Review
          slide order, repeated slides, notes, animations, and attachments
          before deciding to remove it. This is not a byte-identical file match.
        </p>
        <p v-else-if="item.basis === 'similar'">
          Every slide in the proposed removal candidate has a match in the
          proposed retained presentation, with an average visual score of at
          least 95%. Compare text, numbers, diagrams and presentation notes
          before treating the content as interchangeable.
        </p>
        <p v-else>
          Only part of a presentation is covered by the other deck. Retain the
          unmatched content and review its {{ item.matchedSlides }} matching
          {{ item.matchedSlides === 1 ? "slide" : "slides" }} for reuse; this
          overlap does not justify deleting the whole file.
        </p>
        <p>
          Compared with
          <RouterLink
            :to="{ name: 'slides', query: { file: String(item.candidate.id) } }"
            >{{ item.candidate.filename }}</RouterLink
          >
          · File #{{ item.candidate.id }}
        </p>
      </article>
      <button v-if="recommendations.length > 5" @click="expanded = !expanded">
        {{
          expanded
            ? "Show top recommendations"
            : `Show all ${recommendations.length} comparisons`
        }}
      </button>
    </div>
    <div v-else class="recommendation-item">
      <span class="recommendation-badge">Keep presentation</span>
      <h3>No removal candidate identified</h3>
      <p>
        No matching slides were found in other analyzed presentations. Retain
        this presentation; analyze additional decks to broaden the comparison.
      </p>
    </div>
  </RecommendationPanel>
</template>
