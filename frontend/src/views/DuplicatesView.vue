<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { ScanLine } from "@lucide/vue";
import EmptyState from "../components/shared/EmptyState.vue";
import DuplicateSummary from "../components/duplicates/DuplicateSummary.vue";
import DuplicateGroup from "../components/duplicates/DuplicateGroup.vue";
import {
  getCleanupHistory,
  finishCleanup,
  fetchDuplicateGroups,
  type CleanupResolution,
} from "../services/duplicates";
import { useFileUpdates } from "../composables/useFileUpdates";
import type { DuplicateResponse } from "../types/duplicate";

const response = ref<DuplicateResponse | null>(null);
const route = useRoute();
const loading = ref(true);
const error = ref("");
const resolutions = ref<CleanupResolution[]>([]);
const cleanupError = ref("");
async function retryCleanup(id: string) {
  cleanupError.value = "";
  try {
    await finishCleanup(id);
    await scanForDuplicates();
  } catch (cause) {
    cleanupError.value =
      cause instanceof Error ? cause.message : "Could not finish cleanup.";
  }
}
const orderedGroups = computed(() =>
  [...(response.value?.groups ?? [])]
    .filter(
      (group) =>
        !route.query.file ||
        group.files.some((file) => String(file.id) === route.query.file),
    )
    .sort(
      (a, b) =>
        b.potential_savings_bytes - a.potential_savings_bytes ||
        a.sha256.localeCompare(b.sha256),
    ),
);

const visibleSummary = computed(() => ({
  duplicate_groups: orderedGroups.value.length,
  redundant_copies: orderedGroups.value.reduce(
    (sum, group) => sum + group.file_count - 1,
    0,
  ),
  potential_savings_bytes: orderedGroups.value.reduce(
    (sum, group) => sum + group.potential_savings_bytes,
    0,
  ),
}));

let scanVersion = 0;
onBeforeUnmount(() => {
  scanVersion++;
});
async function scanForDuplicates(): Promise<void> {
  const current = ++scanVersion;
  loading.value = true;
  error.value = "";
  // Hide old estimates during a new scan so a failed request cannot look successful.
  response.value = null;
  try {
    const groups = await fetchDuplicateGroups();
    if (current !== scanVersion) return;
    response.value = groups;
    try {
      const history = await getCleanupHistory();
      if (current !== scanVersion) return;
      resolutions.value = history;
      cleanupError.value = "";
    } catch {
      if (current !== scanVersion) return;
      cleanupError.value =
        "Cleanup history is unavailable. No removals are assumed.";
    }
  } catch (failure) {
    if (current !== scanVersion) return;
    error.value =
      failure instanceof Error
        ? failure.message
        : "Could not scan for duplicates.";
  } finally {
    if (current === scanVersion) loading.value = false;
  }
}

useFileUpdates(scanForDuplicates);
onMounted(scanForDuplicates);
</script>

<template>
  <div>
    <div class="page-intro">
      <div>
        <p class="eyebrow">Workspace</p>
        <h1>Duplicate Cleanup</h1>
        <p>
          Keep one verified original per group and remove identical copies.
        </p>
      </div>
      <button
        class="button-primary"
        :disabled="loading"
        aria-label="Scan for Duplicates"
        @click="scanForDuplicates"
      >
        <ScanLine :size="16" /><span>{{
          loading ? "Scanning…" : "Scan for Duplicates"
        }}</span>
      </button>
    </div>
    <p v-if="loading" class="notice" role="status">
      Scanning stored file metadata…
    </p>
    <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
    <template v-if="response">
      <p v-if="route.query.file" class="notice">
        Showing duplicate groups containing File #{{ route.query.file }}.
        <RouterLink :to="{ name: 'duplicates' }"
          >Show all duplicates</RouterLink
        >
      </p>
      <DuplicateSummary :summary="visibleSummary" />
      <EmptyState
        v-if="orderedGroups.length === 0"
        :title="
          route.query.file
            ? 'No duplicates found for this file'
            : 'No exact duplicates found'
        "
        :description="
          route.query.file
            ? 'This file is not part of a stored exact-duplicate group.'
            : 'All stored files have distinct content and size combinations.'
        "
      >
        <p style="font-size: 13px; margin: 8px 0 0">
          Looking for reused slides across decks?
          <RouterLink :to="{ name: 'slides' }">Open Slide Comparison →</RouterLink>
        </p>
      </EmptyState>
      <DuplicateGroup
        v-for="(group, index) in orderedGroups"
        :key="`${group.sha256}-${group.file_size_bytes}`"
        :group="group"
        :group-number="index + 1"
        @resolved="scanForDuplicates"
      />
    </template>
    <details v-if="resolutions.length" class="cleanup-history">
      <summary>Cleanup history ({{ resolutions.length }})</summary>
      <article v-for="item in resolutions" :key="item.id">
        <strong
          >{{ item.status === "resolved" ? "Resolved" : "Pending cleanup" }} ·
          Retained File #{{ item.keeper_id }}</strong
        >
        <p>
          {{ item.removed_ids.length }} redundant original records ·
          {{ item.removed_bytes.toLocaleString() }} confirmed bytes removed{{
            item.measurement_complete ? "" : " (partial measurement)"
          }}
        </p>
        <RouterLink
          :to="{ name: 'files', query: { file: String(item.keeper_id) } }"
          >Open retained file</RouterLink
        ><button
          v-if="item.status === 'pending_purge'"
          @click="retryCleanup(item.id)"
        >
          Verify keeper and finish cleanup
        </button>
      </article>
    </details>
    <p v-if="cleanupError" class="error" role="alert">{{ cleanupError }}</p>
  </div>
</template>

<style scoped>
.cleanup-history {
  background: white;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
  margin-top: 20px;
}
.cleanup-history summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
}
.cleanup-history article {
  padding: 14px 0 4px;
  margin-top: 12px;
  border-top: 1px solid #e1e7ef;
}
.cleanup-history p {
  font-size: 13px;
  color: #66768c;
  margin: 4px 0 8px;
}
.cleanup-history button {
  margin-left: 12px;
}
</style>
