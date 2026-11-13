<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ChartNoAxesColumn } from "@lucide/vue";
import { useWorkspace } from "../composables/useWorkspace";
import StorageSavings from "../components/storage/StorageSavings.vue";
import EmptyState from "../components/shared/EmptyState.vue";
const route = useRoute();
const router = useRouter();
const { files, loading, error } = useWorkspace();
const selectedId = computed(() =>
  typeof route.query.file === "string" ? Number(route.query.file) : 0,
);
const selected = computed(() =>
  files.value.find((file) => file.id === selectedId.value),
);
function choose(event: Event): void {
  void router.replace({
    name: "storage",
    query: { file: (event.target as HTMLSelectElement).value || undefined },
  });
}
</script>
<template>
  <div class="page-intro">
    <div>
      <p class="eyebrow">Analytics</p>
      <h1>Storage Savings</h1>
      <p>Understand your optimized footprint, using actual output sizes.</p>
    </div>
  </div>
  <section>
    <div class="storage-picker">
      <ChartNoAxesColumn :size="22" class="muted" /><label for="storage-file"
        >Compare a file</label
      ><select
        id="storage-file"
        :value="selectedId || ''"
        :disabled="loading"
        @change="choose"
      >
        <option value="">Select a document or recording…</option>
        <option v-for="file in files" :key="file.id" :value="file.id">
          {{ file.filename }}
        </option>
      </select>
    </div>
  </section>
  <p v-if="loading" role="status">Loading files…</p>
  <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>
  <StorageSavings
    v-else-if="selected"
    :key="selected.id"
    :file-id="selected.id"
  /><EmptyState
    v-else
    :title="
      selectedId ? 'File not found' : 'A smaller footprint starts with a file'
    "
    description="Select a file to compare its original size with measurable optimized output. Original uploads remain retained."
  />
</template>
