<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { RefreshCw, FileText, ChartNoAxesColumn } from "@lucide/vue";
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
const targetSlideNumber = computed(() => {
  const raw = route.query.page;
  const num = typeof raw === "string" ? Number(raw) : 0;
  return Number.isSafeInteger(num) && num > 0 ? num : null;
});
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
watch(filter, () => {
  page.value = 1;
});
watch(
  [() => comparison.value, targetSlideNumber],
  async ([comp, targetSlide]) => {
    if (!comp) {
      page.value = 1;
      return;
    }
    if (targetSlide) {
      filter.value = "all";
      const idx = comp.slides.findIndex(
        (s) => s.slide.slide_number === targetSlide,
      );
      if (idx >= 0) {
        page.value = Math.floor(idx / 6) + 1;
        await nextTick();
        const el = document.getElementById(`slide-card-${targetSlide}`);
        el?.scrollIntoView({ block: "center" });
        el?.focus({ preventScroll: true });
        return;
      }
    }
    page.value = 1;
  },
);
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
    <button :disabled="loading" aria-label="Refresh results" @click="refresh">
      <RefreshCw :size="16" :class="{ spin: loading }" /><span>Refresh</span>
    </button>
  </div>
  <UploadEntry
    v-if="!selected"
    description="Upload PDF or PPTX presentations to extract and compare slides automatically."
  />
  <p v-if="listError" class="notice error" role="alert">{{ listError }}</p>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p>
  <section class="selector-panel">
    <div class="selector-row">
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
      <template v-if="selected">
        <RouterLink
          v-if="selected.filename.toLowerCase().endsWith('.pdf')"
          class="selector-link-btn"
          :to="{ name: 'extract', query: { file: String(selected.file_id) } }"
        >
          <FileText :size="15" />Open Document Text
        </RouterLink>
        <RouterLink
          v-if="selected.filename.toLowerCase().endsWith('.pdf')"
          class="selector-link-btn"
          :to="{ name: 'storage', query: { file: String(selected.file_id) } }"
        >
          <ChartNoAxesColumn :size="15" />View Storage Comparison
        </RouterLink>
        <button
          type="button"
          :class="{
            'button-primary':
              selected.status === 'not_processed' ||
              selected.status === 'failed',
          }"
          :disabled="loading"
          @click="analyze"
        >
          <RefreshCw :size="15" :class="{ spin: loading }" />
          {{
            selected.status === "failed"
              ? "Retry Analysis"
              : selected.status === "not_processed"
                ? "Analyze Slides"
                : "Run or Update"
          }}
        </button>
      </template>
    </div>
    <p v-if="loading" class="presentation-state" role="status">
      Loading analysis…
    </p>
    <p v-else-if="selected" class="presentation-state" role="status">
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
        >In selected presentation</small
      >
    </div>
    <div class="kpi-card">
      <div>Similar · review</div>
      <strong>{{ comparison?.summary.similar_slides ?? "—" }}</strong><small
        >In selected presentation</small
      >
    </div>
    <div class="kpi-card">
      <div>Unique slides</div>
      <strong>{{ comparison?.summary.unique_slides ?? "—" }}</strong><small
        >In selected presentation</small
      >
    </div>
  </div>
  <template v-if="comparison"
    ><PresentationRecommendations
      :comparison="comparison"
      :records="presentations"
    />
    <div class="slides-toolbar">
      <div>
        <h2>Slide-by-slide comparison</h2>
        <p class="slide-explanation">
          {{
            comparison.summary.exact_slides + comparison.summary.similar_slides
          }}
          matching slides across
          {{ comparison.summary.matching_presentations }} other decks (threshold:
          {{ comparison.similarity_threshold }}%). Review wording and numbers
          before removing slides.
        </p>
      </div>
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
    </div>
    <SlideComparisonCard
      v-for="result in visible"
      :key="result.slide.id"
      :result="result"
      :highlighted="result.slide.slide_number === targetSlideNumber"
    /><EmptyState
      v-if="!filtered.length"
      title="No slides in this category"
      description="Choose another filter to inspect the presentation."
    />
    <footer v-if="filtered.length" class="pagination">
      <span>Page {{ page }} of {{ pageCount }} ({{ filtered.length }} slides)</span>
      <div>
        <button :disabled="page <= 1" @click="page--">Previous</button
        ><button :disabled="page >= pageCount" @click="page++">Next</button>
      </div>
    </footer></template
  >
  <EmptyState
    v-else-if="!selected && !loading"
    title="Compare your presentations"
    description="Select an existing PDF or PPTX presentation above to inspect its slides."
  />
</template>
<style scoped>
.selector-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.selector-row label {
  margin: 0;
  font-weight: 600;
}
.presentation-selector {
  flex: 1;
  min-width: 220px;
}
.selector-link-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: 5px;
  border: 1px solid #d7dee8;
  background: #fff;
  color: #33445b;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}
.selector-link-btn:hover {
  background: #f1f5fa;
  border-color: #b5c7da;
  text-decoration: none;
}
.presentation-state {
  margin: 10px 0 0;
  color: #66768c;
  font-size: 13px;
}
.slide-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.slides-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin: 20px 0 14px;
}
.slides-toolbar h2 {
  margin: 0 0 4px;
}
.slide-explanation {
  font-size: 12px;
  color: #66768c;
  margin: 0;
}
.slide-filters {
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
