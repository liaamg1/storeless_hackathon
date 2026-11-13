<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { getStorageSavings } from "../../services/storage";
import type { StorageSavings } from "../../types/storage";

const props = defineProps<{ fileId: number; refreshKey?: string }>();
const comparison = ref<StorageSavings | null>(null);
const loading = ref(false);
const error = ref("");
let controller: AbortController | null = null;
let version = 0;

async function loadComparison(): Promise<void> {
  const requestVersion = ++version;
  controller?.abort();
  controller = new AbortController();
  comparison.value = null;
  error.value = "";
  loading.value = true;
  try {
    const result = await getStorageSavings(props.fileId, controller.signal);
    if (requestVersion === version) comparison.value = result;
  } catch (failure) {
    if (requestVersion === version) {
      error.value = failure instanceof Error ? failure.message : "Storage comparison is unavailable.";
    }
  } finally {
    if (requestVersion === version) loading.value = false;
  }
}

watch(() => [props.fileId, props.refreshKey], () => void loadComparison(), { immediate: true });
onBeforeUnmount(() => { version += 1; controller?.abort(); });

const ready = computed(() => comparison.value?.status === "completed" && comparison.value.reduction_percent !== null);
const larger = computed(() => (comparison.value?.storage_saved_bytes ?? 0) < 0);
const chartScale = computed(() => Math.max(
  comparison.value?.original_size_bytes ?? 0, comparison.value?.optimized_size_bytes ?? 0, 1,
));
function barWidth(bytes: number): string { return `${bytes / chartScale.value * 100}%`; }
function mb(bytes: number): string {
  const value = bytes / 1_000_000;
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: value > 0 && value < 0.001 ? 6 : value < 1 ? 4 : 2,
  }) + " MB";
}
function percentage(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude > 0 && magnitude < 0.01) return "<0.01%";
  // Truncate so a small, nonzero output is never presented as 100% reduction.
  return (Math.floor(magnitude * 100) / 100).toFixed(2) + "%";
}
</script>

<template>
  <section class="storage-savings" aria-labelledby="storage-savings-heading">
    <header class="savings-header">
      <div>
        <p class="eyebrow">Storage savings</p>
        <h2 id="storage-savings-heading">Storage Optimization<span v-if="comparison"> — {{ comparison.filename }}</span></h2>
      </div>
      <span class="potential-badge">Potential savings</span>
    </header>
    <p class="retained-note">Your original file is still retained. These figures compare it with the optimized output.</p>
    <p v-if="loading" role="status">Measuring optimized content…</p>
    <div v-else-if="error" role="alert" class="unavailable">
      <p>{{ error }}</p>
      <button type="button" @click="loadComparison">Retry comparison</button>
    </div>
    <template v-else-if="comparison">
      <div class="comparison-cards">
        <div class="size-card original-card">
          <p class="card-label">Original File</p>
          <p class="size-value">{{ mb(comparison.original_size_bytes) }}</p>
          <p class="card-detail">{{ comparison.original_size_bytes.toLocaleString() }} bytes · Uploaded file</p>
        </div>
        <div class="size-card optimized-card">
          <p class="card-label">Optimized File</p>
          <template v-if="ready && comparison.optimized_size_bytes !== null">
            <p class="size-value">{{ mb(comparison.optimized_size_bytes) }}</p>
            <p class="card-detail">{{ comparison.optimized_size_bytes.toLocaleString() }} bytes · Total output</p>
          </template>
          <template v-else>
            <p class="unmeasured-value">{{ comparison.status === 'processing' ? 'Processing…' : 'Unavailable' }}</p>
            <p class="card-detail">A completed, measurable output is required</p>
          </template>
        </div>
      </div>
      <template v-if="ready && comparison.optimized_size_bytes !== null && comparison.reduction_percent !== null && comparison.storage_saved_bytes !== null">
        <div class="savings-summary" :class="{ increase: larger }">
          <strong class="savings-percent">{{ percentage(comparison.reduction_percent) }}</strong>
          <div>
            <p class="summary-label">{{ larger ? 'larger than the original' : 'potential storage reduction' }}</p>
            <p>{{ mb(Math.abs(comparison.storage_saved_bytes)) }} {{ larger ? 'additional storage required' : 'could be saved by replacing the original' }}</p>
          </div>
        </div>
        <figure class="size-chart" aria-label="Original and optimized file sizes on the same scale">
          <figcaption>File size comparison</figcaption>
          <div class="chart-row">
            <div class="chart-label"><span>Original</span><strong>{{ mb(comparison.original_size_bytes) }}</strong></div>
            <div class="bar-track"><div class="bar original-bar" :style="{ width: barWidth(comparison.original_size_bytes) }"></div></div>
          </div>
          <div class="chart-row">
            <div class="chart-label"><span>Optimized</span><strong>{{ mb(comparison.optimized_size_bytes) }}</strong></div>
            <div class="bar-track"><div class="bar optimized-bar" :style="{ width: barWidth(comparison.optimized_size_bytes) }"></div></div>
          </div>
          <p class="chart-note">Both bars use the same scale. Very small outputs may appear as a thin line.</p>
        </figure>
      </template>
      <p v-else class="unavailable" role="status">{{ comparison.message }}</p>
      <div class="output-breakdown">
        <h3>Optimized content</h3>
        <ul>
          <li v-for="component in comparison.components" :key="component.kind">
            <span>{{ component.label }}</span>
            <strong v-if="component.status === 'measured' && component.size_bytes !== null">
              {{ mb(component.size_bytes) }} <small>({{ component.size_bytes.toLocaleString() }} bytes)</small>
            </strong>
            <span v-else class="not-generated">{{ component.status === 'not_generated' ? 'Not generated' : 'Unavailable' }}</span>
          </li>
        </ul>
      </div>
      <p class="measurement-note">{{ ready ? comparison.message + ' ' : '' }}1 MB = 1,000,000 bytes. Only generated output content is included.</p>
    </template>
  </section>
</template>

<style scoped>
.savings-header { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; }
.eyebrow { margin: 0 0 8px; color: #53677f; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
h2 { margin: 0; overflow-wrap: anywhere; }
.potential-badge { background: #eff5fb; color: #315978; border: 1px solid #d6e4ef; border-radius: 20px; padding: 5px 12px; font-size: 0.8rem; white-space: nowrap; }
.retained-note, .card-detail, .chart-note, .measurement-note { color: #617084; font-size: 0.85rem; }
.retained-note { margin: 12px 0 24px; }
.comparison-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.size-card { border: 1px solid #dce5ef; background: #f5f8fc; border-radius: 12px; padding: 22px; }
.optimized-card { background: #f0faf6; border-color: #cee8dd; }
.card-label { font-weight: 600; margin: 0 0 12px; }
.size-value { font-size: clamp(1.4rem, 3vw, 2rem); font-weight: 700; margin: 0; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.card-detail { margin: 10px 0 0; }
.unmeasured-value { font-size: 1.3rem; font-weight: 600; color: #617084; margin: 0; }
.savings-summary { display: flex; align-items: center; flex-wrap: wrap; gap: 20px; margin: 24px 0; padding: 24px; border-radius: 12px; background: #ecf8f2; color: #23634b; }
.savings-summary.increase { color: #805522; background: #fff8eb; }
.savings-percent { font-size: clamp(2.2rem, 5vw, 3rem); letter-spacing: -0.04em; font-variant-numeric: tabular-nums; }
.savings-summary p { margin: 4px 0; font-size: 0.9rem; }
.savings-summary .summary-label { font-weight: 600; font-size: 1rem; }
.size-chart { margin: 28px 0; }
figcaption { font-weight: 600; margin-bottom: 18px; }
.chart-row { margin: 16px 0; }
.chart-label { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 0.9rem; margin-bottom: 8px; }
.bar-track { height: 18px; background: #edf1f5; border-radius: 6px; overflow: hidden; }
.bar { height: 100%; border-radius: 6px; }
.original-bar { background: #8daac8; }
.optimized-bar { background: #53a789; }
.output-breakdown { border-top: 1px solid #e1e7ed; padding-top: 16px; margin-top: 24px; }
h3 { font-size: 1rem; margin: 0 0 12px; }
ul { padding: 0; margin: 0; list-style: none; }
li { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding: 12px 0; border-bottom: 1px solid #edf1f5; font-size: 0.9rem; }
small { font-weight: 400; color: #617084; }
.not-generated { color: #617084; }
.unavailable { padding: 16px; background: #f5f7fa; border: 1px solid #e1e7ed; border-radius: 8px; color: #53677f; }
.measurement-note { margin-bottom: 0; }
@media (max-width: 600px) {
  .comparison-cards { grid-template-columns: 1fr; }
  .size-card, .savings-summary { padding: 18px; }
}
</style>
