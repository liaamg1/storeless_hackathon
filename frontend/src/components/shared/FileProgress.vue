<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{
  status: string;
  percent?: number | null;
  step: string;
  compact?: boolean;
}>();
const active = computed(() =>
  ["queued", "processing", "uploading"].includes(props.status),
);
const measured = computed(() =>
  props.status === "completed"
    ? 100
    : typeof props.percent === "number" && Number.isFinite(props.percent)
      ? Math.max(0, Math.min(100, props.percent))
      : null,
);
</script>
<template>
  <div class="file-progress" :class="[status, { compact }]">
    <div class="progress-caption">
      <span>{{ step }}</span
      ><strong v-if="measured !== null"
        >{{ measured }}%</strong
      ><span v-else-if="active">{{
        status === "queued" ? "Waiting" : "In progress"
      }}</span>
    </div>
    <div
      class="progress-track"
      role="progressbar"
      :aria-label="step"
      :aria-valuemin="0"
      :aria-valuemax="100"
      :aria-valuenow="measured ?? undefined"
      :aria-valuetext="
        measured === null
          ? 'Progress cannot be measured yet'
          : `${measured}% complete for ${step}`
      "
      :aria-busy="active"
    >
      <span
        :class="{ indeterminate: measured === null && active }"
        :style="{
          width: measured === null ? (active ? '35%' : '0%') : `${measured}%`,
        }"
      />
    </div>
    <div
      v-if="active && !compact"
      class="processing-skeleton"
      aria-hidden="true"
    >
      <i /><i />
    </div>
  </div>
</template>
<style scoped>
.file-progress {
  margin: 12px 0;
  min-width: 0;
}
.progress-caption {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #53677f;
  line-height: 1.6;
  margin-bottom: 7px;
}
.progress-caption strong {
  font-size: 11px;
  font-weight: 500;
}
.progress-track {
  height: 7px;
  border-radius: 8px;
  background: #e8edf4;
  overflow: hidden;
}
.progress-track > span {
  display: block;
  height: 100%;
  background: #3478cf;
  border-radius: 8px;
}
.completed .progress-track > span {
  background: #2b8a59;
}
.failed .progress-track > span {
  background: #b84848;
}
.indeterminate {
  animation: slide 1.5s ease-in-out infinite;
}
.processing-skeleton {
  display: grid;
  gap: 7px;
  margin-top: 14px;
}
.processing-skeleton i {
  display: block;
  height: 8px;
  border-radius: 5px;
  background: #edf1f6;
  animation: pulse 1.5s ease-in-out infinite;
}
.processing-skeleton i:last-child {
  width: 65%;
}
.compact {
  min-width: 140px;
  max-width: 240px;
  margin: 7px 0 0;
}
.compact .progress-caption {
  font-size: 10px;
  gap: 4px;
}
@keyframes slide {
  0% {
    transform: translateX(-110%);
  }
  100% {
    transform: translateX(390%);
  }
}
@keyframes pulse {
  50% {
    opacity: 0.4;
  }
}
@media (prefers-reduced-motion: reduce) {
  .indeterminate,
  .processing-skeleton i {
    animation: none;
  }
}
</style>
