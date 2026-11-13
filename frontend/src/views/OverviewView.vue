<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import {
  Folder,
  FileText,
  Video,
  HardDrive,
  ArrowUpRight,
  Sparkles,
  RefreshCw,
} from "@lucide/vue";
import { useWorkspace } from "../composables/useWorkspace";
import { fetchDuplicateGroups } from "../services/duplicates";
import { filterFiles, formatDate } from "../utils/files";
import { formatBytes } from "../utils/formatBytes";
import FilesTable from "../components/files/FilesTable.vue";
import FileDetailsDrawer from "../components/files/FileDetailsDrawer.vue";
import StatusBadge from "../components/shared/StatusBadge.vue";
import EmptyState from "../components/shared/EmptyState.vue";
const { files, loading, error, statusError, refresh } = useWorkspace();
const duplicateSavings = ref<number | null>(null);
const savingsLoading = ref(true);
const selectedId = ref<number | null>(null);
const selected = computed(() =>
  files.value.find((file) => file.id === selectedId.value),
);
const recent = computed(() =>
  filterFiles(files.value, "", "all", "all", "newest").slice(0, 6),
);
const processing = computed(() =>
  files.value
    .filter(
      (file) => file.processing || file.video || file.presentation?.job_id,
    )
    .sort((a, b) => b.id - a.id)
    .slice(0, 5),
);
const pdfCount = computed(
  () => files.value.filter((file) => file.type === "pdf").length,
);
const videoCount = computed(
  () => files.value.filter((file) => file.type === "video").length,
);
let active = true;
onMounted(async () => {
  try {
    const result = await fetchDuplicateGroups();
    if (active) duplicateSavings.value = result.summary.potential_savings_bytes;
  } catch {
    duplicateSavings.value = null;
  } finally {
    if (active) savingsLoading.value = false;
  }
});
onBeforeUnmount(() => {
  active = false;
});
</script>
<template>
  <div class="page-intro">
    <div>
      <p class="eyebrow">Workspace at a glance</p>
      <h1>Overview</h1>
      <p>Your content, processing activity, and opportunities to store less.</p>
    </div>
    <button :disabled="loading" @click="refresh">
      <RefreshCw :size="16" :class="{ spin: loading }" />Refresh files
    </button>
  </div>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div>
        Total Files<span class="kpi-icon"><Folder :size="17" /></span>
      </div>
      <strong>{{ loading || error ? "—" : files.length }}</strong><small
        >Across your workspace</small
      >
    </div>
    <div class="kpi-card">
      <div>
        PDF Documents<span class="kpi-icon"><FileText :size="17" /></span>
      </div>
      <strong>{{ loading || error ? "—" : pdfCount }}</strong><small
        >Documents available for extraction</small
      >
    </div>
    <div class="kpi-card">
      <div>
        Video Recordings<span class="kpi-icon"><Video :size="17" /></span>
      </div>
      <strong>{{ loading || error ? "—" : videoCount }}</strong><small
        >Uploaded MP4 recordings</small
      >
    </div>
    <div class="kpi-card">
      <div>
        Potential Savings<span class="kpi-icon"><HardDrive :size="17" /></span>
      </div>
      <strong>{{
        savingsLoading
          ? "…"
          : duplicateSavings === null
            ? "Unavailable"
            : formatBytes(duplicateSavings)
      }}</strong><small>Exact duplicate copies · originals retained</small>
    </div>
  </div>
  <div class="overview-callout">
    <Sparkles :size="25" aria-hidden="true" />
    <div>
      <h3>Keep the knowledge. Reduce the footprint.</h3>
      <p>
        Compare your recordings with their compact, searchable text versions.
      </p>
    </div>
    <RouterLink :to="{ name: 'upload' }"
      >Upload Files <ArrowUpRight :size="14"
    /></RouterLink>
  </div>
  <div class="dashboard-columns">
    <section class="recent-files-panel">
      <header class="panel-heading">
        <h2>Recent files</h2>
        <RouterLink :to="{ name: 'files' }"
          >View all files <ArrowUpRight :size="14"
        /></RouterLink>
      </header>
      <p v-if="loading" class="table-state" role="status">
        Loading recent files…
      </p>
      <FilesTable
        v-else-if="recent.length"
        :files="recent"
        @select="selectedId = $event"
      /><EmptyState
        v-else
        :title="error ? 'Files unavailable' : 'No files yet'"
        description="Your recently uploaded documents and recordings will appear here."
      />
    </section>
    <section>
      <header class="panel-heading">
        <h2>Recent processing</h2>
        <span class="count-chip">All file types</span>
      </header>
      <p class="muted" style="font-size: 12px">
        Latest document and recording jobs and their current status.
      </p>
      <p v-if="loading" role="status">Loading jobs…</p>
      <p v-else-if="statusError" class="notice" role="status">
        {{ statusError }}
      </p>
      <EmptyState
        v-else-if="!processing.length"
        title="No processing jobs yet"
        description="Open Upload Files to choose processing for documents or recordings."
      />
      <div
        v-for="recording in processing"
        v-else
        :key="recording.id"
        class="processing-item"
      >
        <span class="file-type-icon" :class="recording.type"
          ><component
            :is="recording.type === 'video' ? Video : FileText"
            :size="17"
        /></span>
        <div>
          <RouterLink
            class="truncate"
            :title="recording.filename"
            :to="{
              name: 'files',
              query: { file: String(recording.id) },
            }"
            >{{ recording.filename }}</RouterLink><small>{{
            formatDate(recording.uploaded_at)
          }}</small
          ><StatusBadge :status="recording.status" />
        </div>
        <ArrowUpRight :size="15" class="muted" />
      </div>
    </section>
  </div>
  <FileDetailsDrawer
    v-if="selected"
    :file="selected"
    @close="selectedId = null"
  />
</template>
