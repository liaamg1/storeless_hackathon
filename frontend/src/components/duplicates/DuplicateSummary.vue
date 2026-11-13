<script setup lang="ts">
import type { DuplicateSummary } from "../../types/duplicate";
import { formatBytes } from "../../utils/formatBytes";

defineProps<{ summary: DuplicateSummary }>();
</script>

<template>
  <section aria-labelledby="duplicate-summary-heading">
    <h2 id="duplicate-summary-heading">Summary</h2>
    <dl>
      <dt>Duplicate groups</dt><dd>{{ summary.duplicate_groups }}</dd>
      <dt>Redundant copies</dt><dd>{{ summary.redundant_copies }}</dd>
      <dt>Potential savings</dt><dd>{{ formatBytes(summary.potential_savings_bytes) }}</dd>
    </dl>
    <p>Savings assume one copy is retained and each additional copy occupies separate storage. No storage has been reclaimed.</p>
  </section>
</template>
