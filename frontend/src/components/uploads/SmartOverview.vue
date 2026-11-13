<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import type { ProcessingFile } from "../../types/upload";
import type { StorageSavings } from "../../types/storage";
import type { DuplicateResponse } from "../../types/duplicate";
import { getStorageSavings } from "../../services/storage";
import { fetchDuplicateGroups } from "../../services/duplicates";
import {
  getSlideComparison,
  listPresentations,
} from "../../services/presentations";
import {
  duplicateRecommendation,
  presentationRecommendations,
  type PresentationRecommendation,
} from "../../utils/recommendations";
import { formatBytes } from "../../utils/formatBytes";
import { recommendedOperations } from "../../utils/upload";
function needsAnalysis(file: ProcessingFile) {
  return recommendedOperations(file.file_type).some(
    (operation) => !file.operations.includes(operation),
  );
}

const props = defineProps<{ files: ProcessingFile[] }>();
const measurements = ref<Record<number, StorageSavings>>({});
const matches = ref<Record<number, PresentationRecommendation[]>>({});
const duplicates = ref<DuplicateResponse | null>(null),
  loading = ref(false),
  error = ref("");
let version = 0;
async function load() {
  const current = ++version;
  loading.value = true;
  error.value = "";
  const [dupes, decks] = await Promise.allSettled([
    fetchDuplicateGroups(),
    listPresentations(),
  ]);
  const sizes: Record<number, StorageSavings> = {},
    comparisons: Record<number, PresentationRecommendation[]> = {};
  await Promise.all(
    props.files.map(async (file) => {
      if (file.status !== "completed" || needsAnalysis(file)) return;
      try {
        if (file.file_type === "video")
          sizes[file.file_id] = await getStorageSavings(file.file_id);
        else if (
          file.steps.some(
            (step) =>
              step.operation === "slides" && step.status === "completed",
          )
        )
          comparisons[file.file_id] = presentationRecommendations(
            await getSlideComparison(file.file_id),
            decks.status === "fulfilled" ? decks.value : [],
          );
      } catch {
        if (current === version)
          error.value =
            "Some measurements or comparisons are unavailable. No savings are assumed for those files.";
      }
    }),
  );
  if (current !== version) return;
  duplicates.value = dupes.status === "fulfilled" ? dupes.value : null;
  measurements.value = sizes;
  matches.value = comparisons;
  loading.value = false;
  if (dupes.status === "rejected")
    error.value = "Duplicate information is unavailable. Retry the overview.";
}
watch(
  () =>
    props.files
      .map(
        (file) => `${file.file_id}:${file.status}:${file.operations.join(",")}`,
      )
      .join("|"),
  () => void load(),
  { immediate: true },
);
onBeforeUnmount(() => {
  version++;
});
const duplicatePlans = computed(
  () =>
    duplicates.value?.groups.flatMap((group) => {
      const plan = duplicateRecommendation(group);
      return plan ? [{ ...plan, bytes: group.potential_savings_bytes }] : [];
    }) ?? [],
);
const redundantIds = computed(
  () =>
    new Set(
      duplicatePlans.value.flatMap((plan) =>
        plan.remove.map((file) => file.id),
      ),
    ),
);
const potential = computed(() =>
  Object.values(measurements.value)
    .filter(
      (size) =>
        size.status === "completed" && !redundantIds.value.has(size.file_id),
    )
    .reduce((sum, size) => sum + Math.max(0, size.storage_saved_bytes ?? 0), 0),
);
const done = computed(
  () =>
    props.files.filter(
      (file) => file.status === "completed" && !needsAnalysis(file),
    ).length,
);
const showAll = ref(false);
const filter = ref("all");
function action(file: ProcessingFile) {
  const query = { file: String(file.file_id) };
  const result = (
    kind: string,
    title: string,
    description: string,
    label: string,
    name: string,
    visual = false,
  ) => ({
    kind,
    title,
    description,
    label,
    to: { name, query: visual ? { ...query, view: "visual" } : query },
  });
  if (file.status === "failed")
    return result(
      "attention",
      "Analysis needs attention",
      file.error_message ||
        "Retry the incomplete checks. Your original is retained.",
      "Retry analysis",
      "upload",
    );
  if (file.status !== "completed")
    return result(
      "processing",
      "Analysis is running",
      "Recommendations appear when processing finishes.",
      "View file status",
      "files",
    );
  if (needsAnalysis(file))
    return result(
      "attention",
      "Finish the remaining checks",
      "This file used earlier settings. Complete automatic analysis before making a cleanup decision.",
      "Complete analysis",
      "upload",
    );
  const size = measurements.value[file.file_id];
  if (file.file_type === "video") {
    if (size?.status === "completed" && (size.storage_saved_bytes ?? 0) > 0)
      return result(
        "save",
        "Review replacing the original recording",
        "Download and check the document first. Keep the MP4 if you still need audio, motion or full-resolution screens.",
        "Open optimized document",
        "transcription",
        true,
      );
    return result(
      "keep",
      "Keep the original recording",
      size?.status === "completed"
        ? "The generated document is not smaller than the original."
        : "Storage savings could not be measured. Retain the original.",
      "View results",
      "files",
    );
  }
  const match = matches.value[file.file_id]?.find(
    (item) => item.action === "review_removal",
  );
  if (match)
    return result(
      "review",
      "Review a possible presentation duplicate",
      `Compare ${match.remove?.filename} with ${match.keep.filename}. ${percent(match.averageSimilarity)}% visual similarity; verify content before removing a copy.`,
      "Compare presentations",
      "slides",
    );
  return result(
    "keep",
    "Keep this document",
    matches.value[file.file_id]?.length
      ? "Only partial overlap was found. Keep its unmatched content."
      : "No whole-file removal candidate was found.",
    "View results",
    "files",
  );
}
const filtered = computed(() =>
  props.files
    .filter((file) => !redundantIds.value.has(file.file_id))
    .filter(
      (file) => filter.value === "all" || action(file).kind === filter.value,
    )
    .sort((a, b) => {
      const rank: Record<string, number> = {
        attention: 0,
        save: 1,
        review: 2,
        processing: 3,
        keep: 4,
      };
      return (
        rank[action(a).kind]! - rank[action(b).kind]! ||
        (measurements.value[b.file_id]?.storage_saved_bytes ?? 0) -
          (measurements.value[a.file_id]?.storage_saved_bytes ?? 0)
      );
    }),
);
const visible = computed(() =>
  showAll.value ? filtered.value : filtered.value.slice(0, 6),
);
const labels: Record<string, string> = {
  save: "Potential saving",
  review: "Review match",
  attention: "Needs attention",
  processing: "Processing",
  keep: "Keep file",
};
function percent(value: number) {
  return (Math.floor(value * 100) / 100).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  });
}
</script>
<template>
  <section class="smart-overview" aria-labelledby="smart-overview-heading">
    <header>
      <div>
        <p class="eyebrow">Review results</p>
        <h2 id="smart-overview-heading">Your storage opportunities</h2>
        <p class="muted">
          Start with the recommended action for each file. Nothing is deleted
          automatically.
        </p>
      </div>
      <button :disabled="loading" @click="load">Refresh</button>
    </header>
    <div class="insight-stats">
      <div>
        <small>Files fully analyzed</small
        ><strong>{{ done }} / {{ files.length }}</strong
        ><span>More results appear as analysis finishes</span>
      </div>
      <div>
        <small>Smaller video documents</small
        ><strong>{{ loading ? "Measuring…" : formatBytes(potential) }}</strong
        ><span>Potential saving · analyzed videos only</span>
      </div>
      <div>
        <small>Duplicate copies</small
        ><strong>{{
          duplicates
            ? formatBytes(duplicates.summary.potential_savings_bytes)
            : "Unavailable"
        }}</strong
        ><span>Potential saving · workspace-wide</span>
      </div>
    </div>
    <details class="scope-note">
      <summary>How to read these savings</summary>

      <p>
        These are separate opportunities, not an amount already saved. Redundant
        copies are excluded from the video total to avoid counting them twice.
        Video savings use the actual download size, including HTML formatting
        and embedded images (timestamps off). Slide similarity has no measured
        byte saving.
      </p>
    </details>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div
      class="review-filters"
      role="group"
      aria-label="Filter recommendations"
    >
      <button
        v-for="option in [
          { id: 'all', label: 'All files' },
          { id: 'save', label: 'Save space' },
          { id: 'attention', label: 'Needs attention' },
          { id: 'review', label: 'Similar presentations' },
          { id: 'keep', label: 'Keep' },
        ]"
        :key="option.id"
        :aria-pressed="filter === option.id"
        @click="
          filter = option.id;
          showAll = false;
        "
      >
        {{ option.label }}
      </button>
    </div>
    <article
      v-for="plan in filter === 'all' || filter === 'save'
        ? duplicatePlans.slice(0, 3)
        : []"
      :key="`duplicate-${plan.keep.id}`"
      class="action-card duplicate-action"
    >
      <div class="action-heading">
        <div>
          <span class="action-label">Exact duplicate</span>
          <h3>
            {{ plan.remove.length }} redundant
            {{ plan.remove.length === 1 ? "copy" : "copies" }}
          </h3>
        </div>
        <strong class="saving-value"
          >{{ formatBytes(plan.bytes) }}<small>potential saving</small></strong
        >
      </div>
      <p>
        Keep <b>{{ plan.keep.filename }}</b> (#{{ plan.keep.id }}). Review the
        additional copies for removal.
      </p>
      <RouterLink
        class="primary-action"
        :to="{ name: 'duplicates', query: { file: String(plan.keep.id) } }"
        >Review duplicate copies →</RouterLink
      >
      <details>
        <summary>Copies and match evidence</summary>
        <p v-for="file in plan.remove" :key="file.id">
          {{ file.filename }} · #{{ file.id }}
        </p>
        <p>
          Recorded checksum and size match. Verify the retained copy and any
          processing results before removing another copy.
        </p>
      </details>
    </article>
    <RouterLink
      v-if="
        duplicatePlans.length > 3 && (filter === 'all' || filter === 'save')
      "
      :to="{ name: 'duplicates' }"
      >See all {{ duplicatePlans.length }} duplicate groups →</RouterLink
    >
    <article v-for="file in visible" :key="file.file_id" class="action-card">
      <div class="action-heading">
        <div>
          <span class="action-label" :class="action(file).kind">{{
            labels[action(file).kind]
          }}</span>
          <h3>{{ file.filename }}</h3>
        </div>
        <strong v-if="action(file).kind === 'save'" class="saving-value"
          >{{ formatBytes(measurements[file.file_id]!.storage_saved_bytes!)
          }}<small>potential saving</small></strong
        >
      </div>
      <h4>{{ action(file).title }}</h4>
      <p>{{ action(file).description }}</p>
      <RouterLink class="primary-action" :to="action(file).to"
        >{{ action(file).label }} →</RouterLink
      >
      <details>
        <summary>Details and evidence</summary>
        <div
          v-if="measurements[file.file_id]?.status === 'completed'"
          class="size-comparison"
        >
          <span
            >Original<b>{{ formatBytes(file.size_bytes) }}</b></span
          ><span
            >Download file<b>{{
              formatBytes(measurements[file.file_id]!.optimized_size_bytes!)
            }}</b></span
          ><span
            >Reduction<b
              >{{ percent(measurements[file.file_id]!.reduction_percent!) }}%</b
            ></span
          >
        </div>
        <p
          v-for="match in matches[file.file_id]
            ?.filter((item) => item.action === 'review_removal')
            .slice(0, 2)"
          :key="match.candidate.id"
        >
          {{ match.matchedSlides }} / {{ match.totalSlides }} selected slides
          match {{ match.candidate.filename }}.
          {{ percent(match.averageSimilarity) }}% average visual score. Check
          wording, numbers, notes, animations and slide order.
        </p>
        <p v-if="file.file_type !== 'video'">
          Slide overlap is a review signal, not proof of identical files or
          measured storage savings.
        </p>
        <RouterLink
          :to="{ name: 'files', query: { file: String(file.file_id) } }"
          >All results for this file →</RouterLink
        >
      </details>
    </article>
    <button v-if="filtered.length > 6" @click="showAll = !showAll">
      {{ showAll ? "Show fewer files" : `Show all ${filtered.length} files` }}
    </button>
    <p v-if="!files.length" class="muted">
      Add files in the first tab. Your recommendations will appear here after
      analysis.
    </p>
    <p
      v-else-if="
        !visible.length &&
        !(duplicatePlans.length && (filter === 'all' || filter === 'save'))
      "
      class="muted"
    >
      No files in this category.
    </p>
  </section>
</template>
<style scoped>
.review-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 20px 0;
}
.review-filters button {
  font-size: 12px;
}
.review-filters button[aria-pressed="true"] {
  background: #175ac6;
  color: white;
  border-color: #175ac6;
}
.action-card details {
  margin-top: 18px;
  padding-top: 12px;
  border-top: 1px solid #e1e7ef;
  font-size: 12px;
  color: #66768c;
}
.action-card summary {
  cursor: pointer;
}
.primary-action {
  display: inline-flex;
  padding: 8px 12px;
  border-radius: 6px;
  background: #edf4fc;
  color: #175ac6;
}
.saving-value {
  color: #23634b;
  font-size: 21px;
}
.saving-value small {
  display: block;
  font-size: 11px;
  font-weight: normal;
  color: #66768c;
}
.action-label.save {
  color: #23634b;
  background: #eaf7f0;
}
.action-label.attention,
.action-label.review {
  color: #805522;
  background: #fff6e5;
}
.action-heading h3 {
  margin: 10px 0 0;
}

.smart-overview {
  padding: clamp(18px, 3vw, 28px);
  margin: 24px 0;
  background: #f6f9fd;
  border: 1px solid #d9e4f1;
  border-radius: 12px;
}
header,
.action-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
h2 {
  margin: 5px 0;
}
header p {
  font-size: 13px;
  line-height: 1.7;
}
.insight-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 22px 0;
}
.insight-stats > div {
  background: white;
  border: 1px solid #dce5ef;
  border-radius: 10px;
  padding: 18px;
}
.insight-stats small,
.insight-stats span {
  display: block;
  color: #66768c;
  font-size: 12px;
}
.insight-stats strong {
  display: block;
  font-size: 27px;
  margin: 10px 0;
  color: #175a46;
}
.scope-note {
  font-size: 12px;
  color: #66768c;
  line-height: 1.7;
}
.action-card {
  background: white;
  border: 1px solid #dce5ef;
  border-radius: 10px;
  padding: 20px;
  margin: 14px 0;
  overflow-wrap: anywhere;
}
.action-card h3 {
  font-size: 15px;
  margin: 0 0 12px;
}
.action-card h4 {
  font-size: 15px;
  margin: 14px 0 8px;
}
.action-card p {
  font-size: 13px;
  line-height: 1.8;
  color: #53677f;
}
.action-card a {
  font-size: 13px;
  font-weight: 500;
}
.action-label {
  font-size: 11px;
  color: #315978;
  background: #edf4fc;
  padding: 4px 8px;
  border-radius: 5px;
  display: inline-block;
}
.duplicate-action {
  border-left: 4px solid #ca9d45;
}
.size-comparison {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  font-size: 12px;
  margin: 16px 0;
}
.size-comparison b {
  display: block;
  font-size: 17px;
  margin-top: 5px;
}
.all-results {
  display: block;
  margin-top: 16px;
}
@media (max-width: 750px) {
  .insight-stats {
    grid-template-columns: 1fr;
  }
}
</style>
