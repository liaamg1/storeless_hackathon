<script setup lang="ts">
import { Copy, Files, HardDrive } from "@lucide/vue";
import type { DuplicateSummary } from "../../types/duplicate";
import { formatBytes } from "../../utils/formatBytes";
defineProps<{ summary: DuplicateSummary }>();
</script>
<template>
  <div class="kpi-grid kpi-three">
    <div class="kpi-card">
      <div>
        Duplicate Groups<span class="kpi-icon"><Copy :size="17" /></span>
      </div>
      <strong>{{ summary.duplicate_groups }}</strong
      ><small>Identical content and file size</small>
    </div>
    <div class="kpi-card">
      <div>
        Redundant Copies<span class="kpi-icon"><Files :size="17" /></span>
      </div>
      <strong>{{ summary.redundant_copies }}</strong
      ><small>Additional copies beyond one original</small>
    </div>
    <div class="kpi-card">
      <div>
        Potential Savings<span class="kpi-icon"><HardDrive :size="17" /></span>
      </div>
      <strong>{{ formatBytes(summary.potential_savings_bytes) }}</strong
      ><small>Potential reclaimable storage</small>
    </div>
  </div>
  <p class="duplicate-summary-note">
    Potential savings assume one copy is retained. No files have been deleted or
    storage reclaimed.
  </p>
</template>
