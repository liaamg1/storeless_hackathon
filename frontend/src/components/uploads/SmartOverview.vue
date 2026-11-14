<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { RefreshCw, UploadCloud } from "@lucide/vue";
import type { ProcessingFile } from "../../types/upload";
import type { StorageSavings } from "../../types/storage";
import type { DuplicateResponse } from "../../types/duplicate";
import { useFileUpdates } from "../../composables/useFileUpdates";
import { notifyFilesChanged } from "../../utils/fileUpdates";
import { getFiles } from "../../services/api";
import { getStorageSavings } from "../../services/storage";
import { fetchDuplicateGroups } from "../../services/duplicates";
import { processStoredFile } from "../../services/uploads";
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
import EmptyState from "../shared/EmptyState.vue";

function needsAnalysis(file: ProcessingFile) {
  return recommendedOperations(file.file_type).some(
    (operation) => !file.operations.includes(operation),
  );
}

const props = withDefaults(
  defineProps<{ files: ProcessingFile[]; active?: boolean }>(),
  { active: true },
);
defineEmits<{ addFiles: [] }>();

const activeIds = ref<Set<number> | null>(null);
const activeFiles = computed(() =>
  activeIds.value === null
    ? props.files
    : props.files.filter((file) => activeIds.value!.has(file.file_id)),
);
const measurements = ref<Record<number, StorageSavings>>({});
const matches = ref<Record<number, PresentationRecommendation[]>>({});
const duplicates = ref<DuplicateResponse | null>(null),
  loading = ref(false),
  error = ref("");
let version = 0;

async function load(force = false) {
  if (!props.active && !force) return;
  const current = ++version;
  loading.value = true;
  error.value = "";
  const [dupes, decks, inventory] = await Promise.allSettled([
    fetchDuplicateGroups(),
    listPresentations(),
    getFiles(),
  ]);
  if (current !== version) return;
  const ids = new Set(
    inventory.status === "fulfilled"
      ? inventory.value.map((file) => file.id)
      : [],
  );
  if (inventory.status === "fulfilled") activeIds.value = ids;
  duplicates.value = dupes.status === "fulfilled" ? dupes.value : null;

  const sizes: Record<number, StorageSavings> = force
      ? {}
      : { ...measurements.value },
    comparisons: Record<number, PresentationRecommendation[]> = force
      ? {}
      : { ...matches.value };
  await Promise.all(
    props.files
      .filter((file) => ids.has(file.file_id))
      .map(async (file) => {
        if (file.status !== "completed" || needsAnalysis(file)) return;
        try {
          if (file.file_type === "video") {
            if (force || !sizes[file.file_id])
              sizes[file.file_id] = await getStorageSavings(file.file_id);
          } else if (
            file.steps.some(
              (step) =>
                step.operation === "slides" && step.status === "completed",
            )
          ) {
            comparisons[file.file_id] = presentationRecommendations(
              await getSlideComparison(file.file_id),
              decks.status === "fulfilled" ? decks.value : [],
            );
          }
        } catch {
          if (current === version)
            error.value =
              "Some measurements or comparisons are unavailable. No savings are assumed for those files.";
        }
      }),
  );
  if (current !== version) return;
  measurements.value = sizes;
  matches.value = comparisons;
  loading.value = false;
  if (inventory.status === "rejected")
    error.value =
      "Current files could not be verified. Refresh to see active recommendations.";
  else if (dupes.status === "rejected")
    error.value = "Duplicate information is unavailable. Retry the overview.";
}
useFileUpdates(() => load(true));
watch(
  () => [
    props.active,
    props.files
      .map(
        (file) => `${file.file_id}:${file.status}:${file.operations.join(",")}`,
      )
      .join("|"),
  ],
  ([isActive]) => {
    if (isActive) void load();
  },
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
    activeFiles.value.filter(
      (file) => file.status === "completed" && !needsAnalysis(file),
    ).length,
);
const showAll = ref(false);
const filter = ref("all");
const runningIds = ref<Record<number, boolean>>({});

async function runOrUpdate(file: ProcessingFile): Promise<void> {
  if (runningIds.value[file.file_id]) return;
  runningIds.value = { ...runningIds.value, [file.file_id]: true };
  error.value = "";
  try {
    await processStoredFile(
      file.file_id,
      recommendedOperations(file.file_type),
    );
    notifyFilesChanged();
    await load(true);
  } catch (cause) {
    error.value =
      cause instanceof Error
        ? cause.message
        : "Could not run or update analysis.";
  } finally {
    runningIds.value = { ...runningIds.value, [file.file_id]: false };
  }
}

function buildAction(file: ProcessingFile) {
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
      "Retry Analysis",
      "upload",
    );
  if (file.status !== "completed")
    return result(
      "processing",
      "Analysis is running",
      "Recommendations appear when processing finishes.",
      file.file_type === "video" ? "Open Transcript" : "View File Details",
      file.file_type === "video" ? "transcription" : "files",
    );
  if (needsAnalysis(file))
    return result(
      "attention",
      "Finish the remaining checks",
      "Complete automatic analysis before making a cleanup decision.",
      "Run or Update",
      "upload",
    );
  const size = measurements.value[file.file_id];
  if (file.file_type === "video") {
    if (size?.status === "completed" && (size.storage_saved_bytes ?? 0) > 0)
      return result(
        "save",
        "Review replacing the original recording",
        "Download and verify the compact document first. Keep the MP4 if you still need audio or motion.",
        "Open Visual Transcript",
        "transcription",
        true,
      );
    return result(
      "keep",
      "Keep the original recording",
      size?.status === "completed"
        ? "The generated document is not smaller than the original."
        : "Storage savings could not be measured. Retain the original.",
      "Open Transcript",
      "transcription",
    );
  }
  const match = matches.value[file.file_id]?.find(
    (item) => item.action === "review_removal",
  );
  if (match)
    return result(
      "review",
      "Review a possible presentation duplicate",
      `Compare ${match.remove?.filename} with ${match.keep.filename} (${percent(match.averageSimilarity)}% visual similarity).`,
      "Compare Slides",
      "slides",
    );
  return result(
    "keep",
    "Keep this document",
    matches.value[file.file_id]?.length
      ? "Only partial slide overlap was found. Keep its unique content."
      : "No whole-file removal candidate was found.",
    file.file_type === "pdf" ? "Open Document Text" : "Compare Slides",
    file.file_type === "pdf" ? "extract" : "slides",
  );
}

const filtered = computed(() => {
  const rank: Record<string, number> = {
    attention: 0,
    save: 1,
    review: 2,
    processing: 3,
    keep: 4,
  };
  return activeFiles.value
    .filter((file) => !redundantIds.value.has(file.file_id))
    .map((file) => ({ file, action: buildAction(file) }))
    .filter(
      (item) => filter.value === "all" || item.action.kind === filter.value,
    )
    .sort(
      (a, b) =>
        rank[a.action.kind]! - rank[b.action.kind]! ||
        (measurements.value[b.file.file_id]?.storage_saved_bytes ?? 0) -
          (measurements.value[a.file.file_id]?.storage_saved_bytes ?? 0),
    );
});
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
  <section class="smart-overview" aria-label="Storage recommendations">
    <div class="insight-stats">
      <div>
        <small>Files analyzed</small
        ><strong>{{ done }} / {{ activeFiles.length }}</strong
        ><span>Completed all checks</span>
      </div>
      <div>
        <small>Video optimization</small
        ><strong>{{ loading ? "Measuring…" : formatBytes(potential) }}</strong
        ><span>Potential saving · compact exports</span>
      </div>
      <div>
        <small>Exact duplicates</small
        ><strong>{{
          duplicates
            ? formatBytes(duplicates.summary.potential_savings_bytes)
            : "Unavailable"
        }}</strong
        ><span>Potential saving · redundant copies</span>
      </div>
    </div>

    <div class="review-toolbar">
      <div
        class="segmented-control review-filters"
        role="group"
        aria-label="Filter recommendations"
      >
        <button
          v-for="option in [
            { id: 'all', label: 'All' },
            { id: 'save', label: 'Save space' },
            { id: 'attention', label: 'Needs attention' },
            { id: 'review', label: 'Similar slides' },
            { id: 'keep', label: 'Keep' },
          ]"
          :key="option.id"
          :class="{ active: filter === option.id }"
          :aria-pressed="filter === option.id"
          @click="
            filter = option.id;
            showAll = false;
          "
        >
          {{ option.label }}
        </button>
      </div>
      <button
        :disabled="loading"
        aria-label="Refresh recommendations"
        @click="load(true)"
      >
        <RefreshCw :size="14" :class="{ spin: loading }" /><span>Refresh</span>
      </button>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

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
            {{ plan.remove.length === 1 ? "copy" : "copies" }} of
            {{ plan.keep.filename }}
          </h3>
        </div>
        <strong class="saving-value"
          >{{ formatBytes(plan.bytes) }}<small>potential saving</small></strong
        >
      </div>
      <p>
        Keep <b>{{ plan.keep.filename }}</b> (#{{ plan.keep.id }}) and remove
        identical copies ({{
          plan.remove.map((f) => `#${f.id}`).join(", ")
        }}).
      </p>
      <RouterLink
        class="primary-action"
        :to="{ name: 'duplicates', query: { file: String(plan.keep.id) } }"
        >Review duplicate copies →</RouterLink
      >
    </article>

    <RouterLink
      v-if="
        duplicatePlans.length > 3 && (filter === 'all' || filter === 'save')
      "
      class="see-all-link"
      :to="{ name: 'duplicates' }"
      >See all {{ duplicatePlans.length }} duplicate groups →</RouterLink
    >

    <article
      v-for="{ file, action } in visible"
      :key="file.file_id"
      class="action-card"
    >
      <div class="action-heading">
        <div>
          <span class="action-label" :class="action.kind">{{
            labels[action.kind]
          }}</span>
          <h3>{{ file.filename }}</h3>
        </div>
        <strong v-if="action.kind === 'save'" class="saving-value"
          >{{ formatBytes(measurements[file.file_id]!.storage_saved_bytes!)
          }}<small>potential saving</small></strong
        >
      </div>
      <h4>{{ action.title }}</h4>
      <p>{{ action.description }}</p>
      <div class="action-footer">
        <div class="action-buttons-row">
          <button
            v-if="action.kind === 'attention'"
            type="button"
            class="button-primary"
            :disabled="runningIds[file.file_id]"
            @click="runOrUpdate(file)"
          >
            <RefreshCw :size="14" :class="{ spin: runningIds[file.file_id] }" />
            {{ runningIds[file.file_id] ? "Running…" : action.label }}
          </button>
          <RouterLink v-else class="primary-action" :to="action.to"
            >{{ action.label }} →</RouterLink
          >

          <template v-if="file.file_type === 'video'">
            <RouterLink
              v-if="action.label !== 'Open Transcript'"
              class="secondary-action"
              :to="{
                name: 'transcription',
                query: { file: String(file.file_id) },
              }"
            >
              Open Transcript
            </RouterLink>
            <RouterLink
              class="secondary-action"
              :to="{ name: 'storage', query: { file: String(file.file_id) } }"
            >
              View Storage Comparison
            </RouterLink>
          </template>
          <template v-else-if="file.file_type === 'pdf'">
            <RouterLink
              class="secondary-action"
              :to="{ name: 'slides', query: { file: String(file.file_id) } }"
            >
              Compare Slides
            </RouterLink>
            <RouterLink
              class="secondary-action"
              :to="{ name: 'storage', query: { file: String(file.file_id) } }"
            >
              View Storage Comparison
            </RouterLink>
          </template>

          <button
            v-if="action.kind !== 'attention'"
            type="button"
            class="secondary-action-btn"
            :disabled="runningIds[file.file_id]"
            @click="runOrUpdate(file)"
          >
            <RefreshCw :size="13" :class="{ spin: runningIds[file.file_id] }" />
            {{ runningIds[file.file_id] ? "Running…" : "Run or Update" }}
          </button>
        </div>
        <details class="inline-evidence">
          <summary>Evidence</summary>
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
                >{{
                  percent(measurements[file.file_id]!.reduction_percent!)
                }}%</b
              ></span
            >
          </div>
          <p
            v-for="match in matches[file.file_id]
              ?.filter((item) => item.action === 'review_removal')
              .slice(0, 2)"
            :key="match.candidate.id"
          >
            {{ match.matchedSlides }} / {{ match.totalSlides }} slides match
            {{ match.candidate.filename }} ({{
              percent(match.averageSimilarity)
            }}% average visual score).
          </p>
          <p v-if="file.file_type !== 'video'">
            Visual slide similarity requires manual review before deleting
            files.
          </p>
          <RouterLink
            :to="{ name: 'files', query: { file: String(file.file_id) } }"
            >Open file details →</RouterLink
          >
        </details>
      </div>
    </article>

    <button v-if="filtered.length > 6" @click="showAll = !showAll">
      {{ showAll ? "Show fewer files" : `Show all ${filtered.length} files` }}
    </button>

    <EmptyState
      v-if="!files.length"
      title="No files analyzed yet"
      description="Upload PDFs, PowerPoint decks, or MP4 recordings to see storage savings and duplicate recommendations."
    >
      <button class="button-primary" @click="$emit('addFiles')">
        <UploadCloud :size="16" />Add files
      </button>
    </EmptyState>
    <p
      v-else-if="
        !visible.length &&
        !(duplicatePlans.length && (filter === 'all' || filter === 'save'))
      "
      class="muted"
      style="padding: 18px 0"
    >
      No files in this category.
    </p>
  </section>
</template>
<style scoped>
.smart-overview {
  padding: clamp(18px, 3vw, 26px);
  margin: 0 0 20px;
  background: #f6f9fd;
  border: 1px solid #d9e4f1;
  border-radius: 12px;
}
.insight-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}
.insight-stats > div {
  background: white;
  border: 1px solid #dce5ef;
  border-radius: 10px;
  padding: 16px 18px;
}
.insight-stats small,
.insight-stats span {
  display: block;
  color: #66768c;
  font-size: 12px;
}
.insight-stats strong {
  display: block;
  font-size: 25px;
  margin: 6px 0 4px;
  color: #175a46;
}
.review-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}
.review-filters {
  flex-wrap: wrap;
}
.action-card {
  background: white;
  border: 1px solid #dce5ef;
  border-radius: 10px;
  padding: 18px 20px;
  margin: 12px 0;
  overflow-wrap: anywhere;
}
.action-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.action-heading h3 {
  font-size: 15px;
  margin: 8px 0 0;
}
.action-card h4 {
  font-size: 14px;
  margin: 10px 0 4px;
}
.action-card p {
  font-size: 13px;
  line-height: 1.65;
  color: #53677f;
  margin: 0 0 12px;
}
.action-card a {
  font-size: 13px;
  font-weight: 500;
}
.action-footer {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.inline-evidence {
  font-size: 12px;
  color: #66768c;
  width: 100%;
  margin-top: 4px;
}
.inline-evidence summary {
  cursor: pointer;
  color: #53677f;
  font-weight: 500;
}
.inline-evidence[open] {
  padding-top: 10px;
  border-top: 1px solid #e1e7ef;
}
.action-buttons-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.secondary-action {
  display: inline-flex;
  align-items: center;
  padding: 6px 11px;
  border-radius: 6px;
  border: 1px solid #d7dee8;
  background: #fff;
  color: #33445b;
  font-size: 12px;
  font-weight: 500;
}
.secondary-action:hover {
  background: #f1f5fa;
  border-color: #b5c7da;
  text-decoration: none;
}
.secondary-action-btn {
  min-height: 31px;
  padding: 5px 10px;
  font-size: 12px;
}
.primary-action {
  display: inline-flex;
  padding: 7px 12px;
  border-radius: 6px;
  background: #edf4fc;
  color: #175ac6;
}
.primary-action:hover {
  background: #dfecfa;
  text-decoration: none;
}
.saving-value {
  color: #23634b;
  font-size: 20px;
  text-align: right;
}
.saving-value small {
  display: block;
  font-size: 11px;
  font-weight: normal;
  color: #66768c;
}
.action-label {
  font-size: 11px;
  color: #315978;
  background: #edf4fc;
  padding: 3px 8px;
  border-radius: 5px;
  display: inline-block;
  font-weight: 500;
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
.duplicate-action {
  border-left: 4px solid #ca9d45;
}
.see-all-link {
  display: inline-block;
  margin: 4px 0 12px;
  font-size: 13px;
  font-weight: 500;
}
.size-comparison {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  font-size: 12px;
  margin: 12px 0;
}
.size-comparison b {
  display: block;
  font-size: 15px;
  margin-top: 3px;
  color: #18283d;
}
@media (max-width: 750px) {
  .insight-stats {
    grid-template-columns: 1fr;
  }
}
</style>
