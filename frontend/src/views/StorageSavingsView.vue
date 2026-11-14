<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import {
  ChartNoAxesColumn,
  Video,
  FileText,
  Presentation,
  ArrowUpRight,
} from "@lucide/vue";
import { useWorkspace } from "../composables/useWorkspace";
import StorageSavings from "../components/storage/StorageSavings.vue";
import EmptyState from "../components/shared/EmptyState.vue";

const route = useRoute();
const router = useRouter();
const { files, loading, error } = useWorkspace();
const selectedId = computed(() => {
  const id =
    typeof route.query.file === "string" ? Number(route.query.file) : 0;
  return Number.isSafeInteger(id) && id > 0 ? id : 0;
});
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
  <div>
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
          :disabled="loading && !files.length"
          @change="choose"
        >
          <option value="">Select a document or recording…</option>
          <option v-for="file in files" :key="file.id" :value="file.id">
            {{ file.filename }}
          </option>
        </select>
        <template v-if="selected">
          <RouterLink
            v-if="selected.type === 'video'"
            class="picker-action-link"
            :to="{ name: 'transcription', query: { file: String(selected.id) } }"
          >
            <Video :size="15" />Open Transcript<ArrowUpRight :size="14" />
          </RouterLink>
          <RouterLink
            v-else-if="selected.type === 'pdf'"
            class="picker-action-link"
            :to="{ name: 'extract', query: { file: String(selected.id) } }"
          >
            <FileText :size="15" />Open Document Text<ArrowUpRight :size="14" />
          </RouterLink>
          <RouterLink
            v-else-if="selected.type === 'pptx'"
            class="picker-action-link"
            :to="{ name: 'slides', query: { file: String(selected.id) } }"
          >
            <Presentation :size="15" />Compare Slides<ArrowUpRight :size="14" />
          </RouterLink>
        </template>
      </div>
    </section>
    <p v-if="error && !selectedId" class="notice error" role="alert">
      {{ error }}
    </p>
    <StorageSavings
      v-if="selectedId"
      :key="selectedId"
      :file-id="selectedId"
    /><p v-else-if="loading" role="status">Loading files…</p>
    <EmptyState
      v-else
      title="A smaller footprint starts with a file"
      description="Select a file above to compare its original size with measurable optimized output. Original uploads remain retained."
    />
  </div>
</template>
<style scoped>
.picker-action-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: 5px;
  border: 1px solid #d7dee8;
  background: #fff;
  color: #175ac6;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}
.picker-action-link:hover {
  background: #f1f5fa;
  text-decoration: none;
}
</style>
