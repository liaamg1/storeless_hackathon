<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { RefreshCw } from "@lucide/vue";
import { usePresentations } from "../composables/usePresentations";
import type { SlideClassification } from "../types/presentation";
import SlideComparisonCard from "../components/presentations/SlideComparisonCard.vue";
import PresentationRecommendations from "../components/presentations/PresentationRecommendations.vue";
import EmptyState from "../components/shared/EmptyState.vue";
import UploadEntry from "../components/uploads/UploadEntry.vue";
const route = useRoute(),
  router = useRouter();
const {
  presentations,
  listLoading,
  selected,
  comparison,
  loading,
  error,
  listError,
  refreshList,
  select,
  analyze,
} = usePresentations();
const filter = ref<SlideClassification | "all">("all"),
  page = ref(1);
const filterOptions = [
  { value: "all", label: "All Results" },
  { value: "exact", label: "Exact Matches" },
  { value: "similar", label: "Similar Slides" },
  { value: "unique", label: "Unique Slides" },
] as const;
const recordsAnalyzed = computed(() =>
  presentations.value.filter((p) => p.status === "completed"),
);
const slideCount = computed(() =>
  recordsAnalyzed.value.reduce((sum, p) => sum + p.slide_count, 0),
);
const filtered = computed(
  () =>
    comparison.value?.slides.filter(
      (slide) =>
        filter.value === "all" || slide.classification === filter.value,
    ) ?? [],
);
const visible = computed(() =>
  filtered.value.slice((page.value - 1) * 6, page.value * 6),
);
const pageCount = computed(() =>
  Math.max(1, Math.ceil(filtered.value.length / 6)),
);
watch(
  () => route.query.file,
  (value) => {
    select(typeof value === "string" ? Number(value) : 0);
    page.value = 1;
  },
  { immediate: true },
);
watch([filter, () => comparison.value], () => {
  page.value = 1;
});
function choose(event: Event): void {
  const value = (event.target as HTMLSelectElement).value;
  void router.push({ name: "slides", query: { file: value || undefined } });
}
function refresh(): void {
  void refreshList();
  if (selected.value) select(selected.value.file_id);
}
</script>
<template>
  <div class="page-intro">
    <div>
      <p class="eyebrow">Presentation intelligence</p>
      <h1>Slide Comparison</h1>
      <p>Find reused slides across PDF and PowerPoint presentations.</p>
    </div>
    <button :disabled="loading" @click="refresh">
      <RefreshCw :size="16" />Refresh results
    </button>
  </div>
  <UploadEntry
    description="Add PDF or PPTX presentations and choose slide extraction and comparison from one central upload page."
  />
  <p v-if="listError" class="notice error" role="alert">{{ listError }}</p>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p>
  <section>
    <label for="selected-presentation">Presentation</label
    ><select
      id="selected-presentation"
      class="presentation-selector"
      :value="selected?.file_id ?? route.query.file ?? ''"
      @change="choose"
    >
      <option value="">Select a presentation…</option>
      <option
        v-for="item in presentations"
        :key="item.file_id"
        :value="item.file_id"
      >
        {{ item.filename }} ·
        {{ item.status === "not_processed" ? "Not analyzed" : item.status }}
      </option>
    </select>
    <p v-if="loading" class="muted" role="status">Loading analysis…</p>
    <template v-else-if="selected"
      ><p class="presentation-state" role="status">
        {{
          selected.status === "processing"
            ? "Rendering and hashing slides…"
            : selected.status === "queued"
              ? "Queued for background analysis"
              : selected.status === "not_processed"
                ? "This presentation has not been analyzed yet."
                : selected.status === "failed"
                  ? selected.error_message
                  : `${selected.slide_count} slides analyzed`
        }}
      </p>
      <button
        v-if="
          selected.status === 'not_processed' || selected.status === 'failed'
        "
        class="button-primary"
        @click="analyze"
      >
        {{ selected.status === "failed" ? "Retry analysis" : "Analyze slides" }}
      </button></template
    >
  </section>
  <div class="slide-kpis">
    <div class="kpi-card">
      <div>Presentations analyzed</div>
      <strong>{{
        listLoading || listError ? "—" : recordsAnalyzed.length
      }}</strong><small>Across the workspace</small>
    </div>
    <div class="kpi-card">
      <div>Total slides analyzed</div>
      <strong>{{ listLoading || listError ? "—" : slideCount }}</strong><small
        >Cached slide images and hashes</small
      >
    </div>
    <div class="kpi-card">
      <div>Exact matches</div>
      <strong>{{ comparison?.summary.exact_slides ?? "—" }}</strong><small
        >Slides in selected presentation</small
      >
    </div>
    <div class="kpi-card">
      <div>Similar · review required</div>
      <strong>{{ comparison?.summary.similar_slides ?? "—" }}</strong><small
        >Slides in selected presentation</small
      >
    </div>
    <div class="kpi-card">
      <div>Unique slides</div>
      <strong>{{ comparison?.summary.unique_slides ?? "—" }}</strong><small
        >Slides in selected presentation</small
      >
    </div>
  </div>
  <template v-if="comparison"
    ><PresentationRecommendations
      :comparison="comparison"
      :records="presentations"
    />
    <h2>Slide-by-slide evidence</h2>
    <p class="notice">
      {{ comparison.summary.exact_slides + comparison.summary.similar_slides }}
      matching slides identified across
      {{ comparison.summary.matching_presentations }} other presentations. These
      are potential reuse opportunities; no storage has been reclaimed.
    </p>
    <p class="slide-explanation">
      Similarity is a visual heuristic, not proof of identical information.
      Threshold: {{ comparison.similarity_threshold }}%. Review changes to
      numbers, labels and diagrams. Byte savings are unavailable until a
      concrete replacement strategy exists.
    </p>
    <div
      class="segmented-control slide-filters"
      role="group"
      aria-label="Filter slides"
    >
      <button
        v-for="option in filterOptions"
        :key="option.value"
        :class="{ active: filter === option.value }"
        :aria-pressed="filter === option.value"
        @click="filter = option.value"
      >
        {{ option.label }}
      </button>
    </div>
    <p class="muted">{{ filtered.length }} slides in this view</p>
    <SlideComparisonCard
      v-for="result in visible"
      :key="result.slide.id"
      :result="result"
    /><EmptyState
      v-if="!filtered.length"
      title="No slides in this category"
      description="Choose another filter to inspect the presentation."
    />
    <footer class="pagination">
      <span>Page {{ page }} of {{ pageCount }}</span>
      <div>
        <button :disabled="page <= 1" @click="page--">Previous</button
        ><button :disabled="page >= pageCount" @click="page++">Next</button>
      </div>
    </footer></template
  >
  <EmptyState
    v-else-if="!selected && !loading"
    title="Compare your presentations"
    description="Upload a presentation or select an existing PDF to analyze its slides."
  />
</template>
<style scoped>
.presentation-selector {
  width: 100%;
}
.presentation-state {
  margin: 14px 0 0;
  color: #66768c;
  font-size: 13px;
}
.presentation-state + button {
  margin-top: 12px;
}
.slide-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 22px;
}
.slide-explanation {
  font-size: 12px;
  color: #66768c;
  line-height: 1.7;
}
.slide-filters {
  margin: 10px 0 16px;
  flex-wrap: wrap;
}
.slide-kpis .kpi-card strong {
  font-size: 26px;
}
@media (max-width: 1000px) {
  .slide-kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .slide-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
