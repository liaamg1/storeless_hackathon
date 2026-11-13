<script setup lang="ts">
import type { FileStatus } from "../../utils/files";
defineProps<{ status: FileStatus }>();
const labels: Record<FileStatus, string> = {
  available: "Available",
  unknown: "Unknown",
  queued: "Queued",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};
</script>
<template>
  <span class="status-badge" :class="`status-${status}`"
    ><span class="status-dot" />{{ labels[status] }}</span
  >
</template>
