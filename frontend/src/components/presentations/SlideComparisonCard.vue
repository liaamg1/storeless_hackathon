<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { SlideComparison } from "../../types/presentation";
import { slideImageUrl } from "../../services/presentations";
const props = defineProps<{ result: SlideComparison }>();
const matchId = ref<number | null>(null);
const match = computed(
  () =>
    props.result.matches.find((item) => item.slide.id === matchId.value) ??
    props.result.matches[0],
);
watch(
  () => props.result.slide.id,
  () => {
    matchId.value = null;
  },
);
const labels = {
  exact: "Exact Match",
  similar: "Similar — Review Required",
  unique: "Unique",
};
</script>
<template>
  <article class="slide-card">
    <header class="panel-heading">
      <h3>Slide {{ result.slide.slide_number }}</h3>
      <span
        class="slide-classification"
        :class="match?.classification ?? result.classification"
        >{{ labels[match?.classification ?? result.classification] }}</span
      >
    </header>
    <div v-if="result.matches.length > 1" class="slide-match-picker">
      <label :for="`match-${result.slide.id}`"
        >Matching slides ({{ result.matches.length }})</label
      ><select
        :id="`match-${result.slide.id}`"
        :value="match?.slide.id"
        @change="matchId = Number(($event.target as HTMLSelectElement).value)"
      >
        <option
          v-for="item in result.matches"
          :key="item.slide.id"
          :value="item.slide.id"
        >
          {{ item.slide.filename }} · Slide {{ item.slide.slide_number }} ·
          {{ item.similarity_percent }}% ·
          {{
            item.classification === "exact"
              ? "Exact Match"
              : "Similar — Review Required"
          }}
        </option>
      </select>
    </div>
    <div class="slide-pair" :class="{ 'single-slide': !match }">
      <figure>
        <a
          :href="slideImageUrl(result.slide.id, false)"
          target="_blank"
          rel="noopener"
          :aria-label="`Open full image: ${result.slide.filename}, slide ${result.slide.slide_number}`"
          ><img
            :src="slideImageUrl(result.slide.id)"
            :alt="`Slide ${result.slide.slide_number} from ${result.slide.filename}`"
            loading="lazy"
        /></a>
        <figcaption>
          <strong :title="result.slide.filename">{{
            result.slide.filename
          }}</strong><span
            >Selected presentation · Slide {{ result.slide.slide_number }}</span
          >
        </figcaption>
      </figure>
      <figure v-if="match">
        <a
          :href="slideImageUrl(match.slide.id, false)"
          target="_blank"
          rel="noopener"
          :aria-label="`Open matching image: ${match.slide.filename}, slide ${match.slide.slide_number}`"
          ><img
            :src="slideImageUrl(match.slide.id)"
            :alt="`Slide ${match.slide.slide_number} from ${match.slide.filename}`"
            loading="lazy"
        /></a>
        <figcaption>
          <strong :title="match.slide.filename">{{
            match.slide.filename
          }}</strong><span
            >Matching presentation · Slide {{ match.slide.slide_number }}</span
          >
        </figcaption>
      </figure>
    </div>
    <p v-if="match" class="slide-score">
      <strong>{{ match.similarity_percent }}%</strong>
      {{
        match.classification === "exact"
          ? "Identical normalized rendering and text"
          : "Perceptual-hash similarity · review changed text, numbers and diagrams"
      }}
    </p>
    <p v-else class="muted">
      No sufficiently similar slide found in another analyzed presentation.
    </p>
    <div class="slide-recommendation">
      <strong>Suggested action</strong>
      <p v-if="match?.classification === 'exact'">
        Reuse one copy of this slide. Its normalized image and extracted text
        match {{ match.slide.filename }}, slide {{ match.slide.slide_number }}.
        Check presentation context before removing a repeated slide.
      </p>
      <p v-else-if="match">
        Review before removing or merging. The {{ match.similarity_percent }}%
        score measures visual similarity; check changed wording, numbers and
        diagrams side by side.
      </p>
      <p v-else>
        Keep this slide. No matching slide was found in another analyzed
        presentation.
      </p>
    </div>
    <details v-if="result.slide.text.trim()" class="slide-text">
      <summary>Extracted slide text</summary>
      <pre>{{ result.slide.text }}</pre>
    </details>
  </article>
</template>

<style scoped>
.slide-recommendation {
  border-left: 3px solid #8daac8;
  background: #f4f8fd;
  border-radius: 0 8px 8px 0;
  padding: 12px 16px;
  margin: 18px 0;
}
.slide-recommendation strong {
  font-size: 12px;
}
.slide-recommendation p {
  font-size: 13px;
  line-height: 1.75;
  margin: 8px 0 0;
  color: #53677f;
  overflow-wrap: anywhere;
}
</style>
