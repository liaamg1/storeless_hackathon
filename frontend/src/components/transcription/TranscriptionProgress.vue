<script setup lang="ts">
import StatusBadge from "../shared/StatusBadge.vue";
import type {
  ProcessingJob,
  ProcessingStep,
  VideoRecord,
} from "../../types/transcription";
import { formatBytes } from "../../utils/formatBytes";
import { formatTimestamp } from "../../utils/formatTimestamp";

defineProps<{ video: VideoRecord; job: ProcessingJob }>();
const stepLabels: Record<ProcessingStep, string> = {
  queued: "Waiting for processing to start",
  validating_video: "Validating video",
  extracting_audio: "Extracting audio",
  transcribing_audio: "Transcribing audio (includes loading the speech model)",
  saving_transcript: "Saving transcript",
  completed: "Completed",
};
</script>

<template>
  <section aria-labelledby="video-progress-heading" class="processing-panel">
    <h2 id="video-progress-heading">Video processing</h2>
    <p class="filename">{{ video.filename }}</p>
    <dl>
      <dt>Size</dt>
      <dd>{{ formatBytes(video.size_bytes) }}</dd>
      <dt>Duration</dt>
      <dd>
        {{
          video.duration_ms === null
            ? "Unknown"
            : formatTimestamp(video.duration_ms)
        }}
      </dd>
      <dt>Status</dt>
      <dd><StatusBadge :status="job.status" /></dd>
      <dt>
        {{
          job.status === "failed" ? "Last processing step" : "Processing step"
        }}
      </dt>
      <dd role="status">{{ stepLabels[job.current_step] }}</dd>
    </dl>
    <p v-if="job.status === 'failed'" class="error" role="alert">
      {{
        job.error_message ||
        "Processing failed. The original recording is preserved."
      }}
    </p>
  </section>
</template>

<style scoped>
.filename {
  overflow-wrap: anywhere;
}
</style>
