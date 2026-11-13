<script setup lang="ts">
import { onMounted, ref } from "vue";
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
    error.value = failure instanceof Error ? failure.message : "Could not scan for duplicates.";
  } finally {
    loading.value = false;
  }
}

onMounted(scanForDuplicates);
</script>

<template>
  <div>
    <section aria-labelledby="duplicates-heading">
      <h2 id="duplicates-heading">Duplicate file detection</h2>
      <p>Find files with matching SHA-256 hashes and sizes, even when filenames differ.</p>
      <p>Scans use stored metadata. Original files are not opened, modified, or deleted.</p>
      <button type="button" :disabled="loading" @click="scanForDuplicates">Scan for Duplicates</button>
      <p v-if="loading" role="status">Scanning for duplicates...</p>
      <p v-else-if="error" class="error" role="alert">{{ error }}</p>
    </section>
    <template v-if="response">
      <DuplicateSummary :summary="response.summary" />
      <p v-if="response.groups.length === 0" role="status">No duplicates found.</p>
      <DuplicateGroup
        v-for="(group, index) in response.groups" :key="`${group.sha256}-${group.file_size_bytes}`"
        :group="group" :group-number="index + 1"
      />
    </template>
  </div>
</template>
