<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { RefreshCw, ChevronLeft, ChevronRight, Folder } from "@lucide/vue";
import FilesTable from "../components/files/FilesTable.vue";
import FileFilters from "../components/files/FileFilters.vue";
import FileDetailsDrawer from "../components/files/FileDetailsDrawer.vue";
import EmptyState from "../components/shared/EmptyState.vue";
import { useWorkspace } from "../composables/useWorkspace";
import { filterFiles, type FileSort } from "../utils/files";
import { formatBytes } from "../utils/formatBytes";
const { files, loading, error, statusError, refresh } = useWorkspace();
const route = useRoute();
const router = useRouter();
const query = ref("");
const type = ref("all");
const status = ref("all");
const sort = ref<FileSort>("newest");
const page = ref(1);
const pageSize = 12;
const selectedId = ref<number | null>(null);

function openFile(id: number): void {
  selectedId.value = id;
  const nextFile = String(id);
  if (route.name === "files" && route.query.file !== nextFile) {
    void router.replace({
      name: "files",
      query: { file: nextFile },
    });
  }
}

function closeDrawer(): void {
  selectedId.value = null;
  if (route.name === "files" && route.query.file) {
    void router.replace({
      name: "files",
      query: {},
    });
  }
}

watch(
  () => route.query.file,
  (value) => {
    if (route.name !== "files") return;
    const id = typeof value === "string" ? Number(value) : 0;
    selectedId.value = Number.isSafeInteger(id) && id > 0 ? id : null;
  },
  { immediate: true },
);
const selectedFile = computed(() =>
  files.value.find((file) => file.id === selectedId.value),
);
const filtered = computed(() =>
  filterFiles(files.value, query.value, type.value, status.value, sort.value),
);
const totalPages = computed(() =>
  Math.max(1, Math.ceil(filtered.value.length / pageSize)),
);
const paged = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize),
);
const totalSize = computed(() =>
  files.value.reduce((sum, file) => sum + file.size_bytes, 0),
);
watch([query, type, status, sort], () => {
  page.value = 1;
});
watch(totalPages, (value) => {
  page.value = Math.min(page.value, value);
});
function reset(): void {
  query.value = "";
  type.value = "all";
  status.value = "all";
}
</script>
<template>
  <div>
    <div class="page-intro">
      <div>
        <p class="eyebrow">Workspace</p>
        <h1>All Files</h1>
        <p>Inspect uploaded documents, presentations, and recordings.</p>
      </div>
      <button :disabled="loading" aria-label="Refresh files" @click="refresh">
        <RefreshCw :size="16" :class="{ spin: loading }" /><span>Refresh</span>
      </button>
    </div>
    <section class="files-workspace" aria-label="File workspace">
      <header class="workspace-summary">
        <div>
          <Folder :size="18" />
          <h2>Stored files</h2>
          <span class="count-chip">{{ loading ? "…" : files.length }}</span>
        </div>
        <span class="muted">{{ formatBytes(totalSize) }} total uploaded</span>
      </header>
      <FileFilters
        v-model:query="query"
        v-model:type="type"
        v-model:status="status"
        v-model:sort="sort"
      />
      <p v-if="loading" role="status" class="table-state">Loading your files…</p>
      <p v-else-if="error" class="error table-state" role="alert">
        {{ error }} <button @click="refresh">Try again</button>
      </p>
      <template v-else
        ><p v-if="statusError" class="notice warning" role="status">
          {{ statusError }}
        </p>
        <FilesTable
          v-if="paged.length"
          :files="paged"
          @select="openFile($event)" /><EmptyState
          v-else
          :title="
            files.length
              ? 'No files match your filters'
              : 'Your workspace is empty'
          "
          :description="
            files.length
              ? 'Try another filename or clear the active filters.'
              : 'Use Upload Files to add your first PDF, PPTX, or MP4.'
          "
          ><button v-if="files.length" @click="reset">
            Clear filters
          </button></EmptyState
        >
        <footer v-if="filtered.length" class="pagination">
          <span
            >{{ (page - 1) * pageSize + 1 }}–{{
              Math.min(page * pageSize, filtered.length)
            }}
            of {{ filtered.length }} files</span
          >
          <div>
            <button
              class="icon-button"
              aria-label="Previous page"
              :disabled="page <= 1"
              @click="page--"
            >
              <ChevronLeft :size="17" /></button
            ><span>Page {{ page }} of {{ totalPages }}</span
            ><button
              class="icon-button"
              aria-label="Next page"
              :disabled="page >= totalPages"
              @click="page++"
            >
              <ChevronRight :size="17" />
            </button>
          </div></footer
      ></template>
    </section>
    <FileDetailsDrawer
      v-if="selectedFile"
      :key="selectedFile.id"
      :file="selectedFile"
      @close="closeDrawer"
    />
  </div>
</template>
