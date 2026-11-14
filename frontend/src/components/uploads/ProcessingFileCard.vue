<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import { FileText, Video, Presentation, RefreshCw } from "@lucide/vue";
import type { ProcessingFile } from "../../types/upload";
import {
  operationLabel,
  processingStepLabel,
  recommendedOperations,
} from "../../utils/upload";
import { processStoredFile } from "../../services/uploads";
import { notifyFilesChanged } from "../../utils/fileUpdates";
import { formatBytes } from "../../utils/formatBytes";
import FileProgress from "../shared/FileProgress.vue";
import StatusBadge from "../shared/StatusBadge.vue";

const props = defineProps<{ file: ProcessingFile; detail?: boolean }>();
const emit = defineEmits<{ updated: [file: ProcessingFile] }>();
const retrying = ref(false);
const retryError = ref("");

const completed = (operation: string) =>
  props.file.steps.some(
    (step) => step.operation === operation && step.status === "completed",
  );
const needsMoreChecks = computed(() =>
  recommendedOperations(props.file.file_type).some(
    (op) => !props.file.operations.includes(op),
  ),
);
const links = computed(() => {
  const query = { file: String(props.file.file_id) };
  const result = [];
  if (props.file.file_type === "video") {
    result.push({
      label: "Open Transcript",
      to: { name: "transcription", query },
    });
    if (completed("visuals"))
      result.push({
        label: "Visual Transcript",
        to: { name: "transcription", query: { ...query, view: "visual" } },
      });
    result.push({
      label: "View Storage Comparison",
      to: { name: "storage", query },
    });
  } else if (props.file.file_type === "pdf") {
    result.push({
      label: "Open Document Text",
      to: { name: "extract", query },
    });
    if (completed("slides"))
      result.push({
        label: "Compare Slides",
        to: { name: "slides", query },
      });
    result.push({
      label: "View Storage Comparison",
      to: { name: "storage", query },
    });
  } else if (props.file.file_type === "pptx") {
    result.push({
      label: "Compare Slides",
      to: { name: "slides", query },
    });
  }
  if (completed("duplicates"))
    result.push({
      label: "Duplicates",
      to: { name: "duplicates", query },
    });
  return result;
});

async function runOrRetry(): Promise<void> {
  if (retrying.value) return;
  retrying.value = true;
  retryError.value = "";
  try {
    const updated = await processStoredFile(
      props.file.file_id,
      recommendedOperations(props.file.file_type),
    );
    notifyFilesChanged();
    emit("updated", updated);
  } catch (error) {
    retryError.value =
      error instanceof Error ? error.message : "Could not run analysis.";
  } finally {
    retrying.value = false;
  }
}
</script>
<template>
  <article
    class="processing-file-card"
    :aria-label="`Processing ${file.filename}`"
  >
    <header>
      <span class="file-type-icon" :class="file.file_type"
        ><component
          :is="
            file.file_type === 'video'
              ? Video
              : file.file_type === 'pptx'
                ? Presentation
                : FileText
          "
          :size="19"
      /></span>
      <div>
        <h3>{{ file.filename }}</h3>
        <p>
          {{
            file.file_type === "video" ? "MP4" : file.file_type.toUpperCase()
          }}
          · {{ formatBytes(file.size_bytes) }} · File #{{ file.file_id }}
        </p>
      </div>
      <StatusBadge :status="file.status" />
    </header>
    <FileProgress
      v-if="file.status !== 'completed'"
      :status="file.status"
      :percent="file.progress_percent"
      :step="
        file.status === 'failed'
          ? 'Failed · ' + processingStepLabel(file.current_step)
          : processingStepLabel(file.current_step)
      "
    />
    <details class="step-details" :open="detail || file.status === 'failed'">
      <summary>Analysis steps ({{ file.steps.length }})</summary>
      <ol class="operation-progress">
        <li v-for="step in file.steps" :key="step.operation">
          <span class="operation-state" :class="step.status">{{
            step.status === "completed"
              ? "✓"
              : step.status === "failed" || step.status === "unavailable"
                ? "!"
                : step.status === "processing"
                  ? "●"
                  : "○"
          }}</span>
          <div>
            <strong>{{
              operationLabel(step.operation, file.file_type)
            }}</strong><small>{{
              step.status === "completed"
                ? "Completed"
                : step.status === "unavailable"
                  ? "Unavailable"
                  : processingStepLabel(step.current_step)
            }}</small>
            <p v-if="step.error_message" class="error">
              {{ step.error_message }}
            </p>
          </div>
        </li>
      </ol>
    </details>
    <p v-if="retryError" class="error" role="alert" style="margin-top: 8px">
      {{ retryError }}
    </p>
    <div v-if="!detail" class="processing-results">
      <RouterLink
        class="primary-result"
        :to="{ name: 'files', query: { file: String(file.file_id) } }"
        >File Details</RouterLink
      >
      <RouterLink v-for="link in links" :key="link.label" :to="link.to">{{
        link.label
      }}</RouterLink>
      <button
        type="button"
        class="inline-retry-button"
        :disabled="retrying"
        @click="runOrRetry"
      >
        <RefreshCw :size="13" :class="{ spin: retrying }" />
        {{
          retrying
            ? "Running…"
            : file.status === "failed"
              ? "Retry Analysis"
              : needsMoreChecks
                ? "Complete Analysis"
                : "Run or Update"
        }}
      </button>
    </div>
  </article>
</template>
<style scoped>
.processing-file-card {
  padding: 16px 18px;
  border: 1px solid #dce5ef;
  border-radius: 10px;
  background: white;
  min-width: 0;
  margin: 12px 0;
}
header {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
}
header > div {
  flex: 1;
  min-width: 120px;
}
h3 {
  margin: 0 0 4px;
  font-size: 14px;
  overflow-wrap: anywhere;
}
header p {
  font-size: 12px;
  color: #66768c;
  margin: 0;
}
.step-details {
  margin-top: 10px;
  font-size: 12px;
  color: #53677f;
}
.step-details summary {
  cursor: pointer;
  font-weight: 500;
}
.operation-progress {
  list-style: none;
  padding: 0;
  margin: 10px 0 0;
  display: grid;
  gap: 10px;
}
.operation-progress li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.operation-progress strong {
  font-size: 12px;
  font-weight: 500;
  color: #18283d;
}
.operation-progress small {
  display: block;
  color: #66768c;
  font-size: 11px;
}
.operation-progress .error {
  font-size: 12px;
  margin: 4px 0 0;
}
.operation-state {
  color: #66768c;
  width: 18px;
  flex-shrink: 0;
}
.operation-state.completed {
  color: #237347;
}
.operation-state.failed,
.operation-state.unavailable {
  color: #a34232;
}
.operation-state.processing {
  color: #175ac6;
}
.processing-results {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 14px;
  border-top: 1px solid #e1e7ef;
  margin-top: 12px;
  padding-top: 12px;
  font-size: 12px;
}
.primary-result,
.retry-link {
  font-weight: 600;
}
.inline-retry-button {
  min-height: 26px;
  padding: 4px 10px;
  font-size: 12px;
  margin-left: auto;
}
</style>
