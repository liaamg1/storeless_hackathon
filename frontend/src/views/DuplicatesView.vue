<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ScanLine } from "@lucide/vue";
import EmptyState from "../components/shared/EmptyState.vue";
import DuplicateSummary from "../components/duplicates/DuplicateSummary.vue";
import DuplicateGroup from "../components/duplicates/DuplicateGroup.vue";
import { fetchDuplicateGroups } from "../services/duplicates";
import type { DuplicateResponse } from "../types/duplicate";

const response = ref<DuplicateResponse | null>(null);
const loading = ref(true);
const error = ref("");

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
        <p>Find identical files and understand potential storage savings.</p>
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
    <template v-if="response">
      <DuplicateSummary :summary="response.summary" />
      <EmptyState
        v-if="response.groups.length === 0"
        title="No duplicates found"
        description="All stored files have distinct content and size combinations."
      />
      <DuplicateGroup
        v-for="(group, index) in response.groups"
        :key="`${group.sha256}-${group.file_size_bytes}`"
        :group="group"
        :group-number="index + 1"
      />
    </template>
  </div>
</template>
