<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { ScanLine } from "@lucide/vue";
import EmptyState from "../components/shared/EmptyState.vue";
import DuplicateSummary from "../components/duplicates/DuplicateSummary.vue";
import DuplicateGroup from "../components/duplicates/DuplicateGroup.vue";
import RecommendationPanel from "../components/shared/RecommendationPanel.vue";
import { fetchDuplicateGroups } from "../services/duplicates";
import type { DuplicateResponse } from "../types/duplicate";

const response = ref<DuplicateResponse | null>(null);
const loading = ref(true);
const error = ref("");
const orderedGroups = computed(() =>
  [...(response.value?.groups ?? [])].sort(
    (a, b) =>
      b.potential_savings_bytes - a.potential_savings_bytes ||
      a.sha256.localeCompare(b.sha256),
  ),
);

async function scanForDuplicates(): Promise<void> {
  loading.value = true;
  error.value = "";
  // Hide old estimates during a new scan so a failed request cannot look successful.
  response.value = null;
  try {
    response.value = await fetchDuplicateGroups();
  } catch (failure) {
    error.value =
      failure instanceof Error
        ? failure.message
        : "Could not scan for duplicates.";
  } finally {
    loading.value = false;
  }
}

onMounted(scanForDuplicates);
</script>

<template>
  <div>
    <div class="page-intro">
      <div>
        <p class="eyebrow">Workspace</p>
        <h1>Duplicates</h1>
        <p>
          Review exact matches, choose a copy to keep, and identify redundant
          files.
        </p>
      </div>
      <button
        class="button-primary"
        :disabled="loading"
        @click="scanForDuplicates"
      >
        <ScanLine :size="16" />{{
          loading ? "Scanning…" : "Scan for Duplicates"
        }}
      </button>
    </div>
    <p v-if="loading" class="notice" role="status">
      Scanning stored file metadata…
    </p>
    <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
    <p class="notice">
      Looking for reused presentation slides?
      <RouterLink :to="{ name: 'slides' }">Open Slide Comparison</RouterLink>
    </p>
    <template v-if="response">
      <DuplicateSummary :summary="response.summary" />
      <RecommendationPanel
        v-if="response.groups.length"
        title="Suggested cleanup"
        description="Start with the largest storage opportunities. Each group names one suggested copy to keep and the identical copies you can consider deleting."
      >
        <div class="recommendation-item">
          <span class="recommendation-badge exact">Exact file matches</span>
          <h3>
            {{ response.summary.redundant_copies }} redundant copies to review
          </h3>
          <p>
            Keep one copy per group. Suggested deletions are based on matching
            recorded SHA-256 hashes and byte sizes; the scan does not reopen the
            files. Expand a group to review its file names, IDs, and evidence.
          </p>
        </div>
      </RecommendationPanel>
      <EmptyState
        v-if="response.groups.length === 0"
        title="No duplicates found"
        description="All stored files have distinct content and size combinations."
      />
      <DuplicateGroup
        v-for="(group, index) in orderedGroups"
        :key="`${group.sha256}-${group.file_size_bytes}`"
        :group="group"
        :group-number="index + 1"
      />
    </template>
  </div>
</template>
