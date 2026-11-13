<script setup lang="ts">
import type { VideoTranscript } from "../../types/transcription";
import { formatTimestamp } from "../../utils/formatTimestamp";

defineProps<{ transcript: VideoTranscript; downloading: boolean; downloadError: string }>();
defineEmits<{ download: [] }>();
</script>

<template>
  <section aria-labelledby="transcript-heading">
    <h2 id="transcript-heading">Transcript</h2>
    <p>{{ transcript.filename }} · Completed · {{ transcript.segments.length }} {{ transcript.segments.length === 1 ? "segment" : "segments" }}</p>
    <p v-if="transcript.language">Detected language: {{ transcript.language }}</p>
    <button type="button" :disabled="downloading" @click="$emit('download')">Download Transcript</button>
    <p v-if="downloadError" class="error" role="alert">{{ downloadError }}</p>
    <p v-if="transcript.segments.length === 0">No speech was detected in this recording.</p>
    <article v-for="segment in transcript.segments" :key="segment.id">
      <h3>{{ formatTimestamp(segment.start_ms) }} – {{ formatTimestamp(segment.end_ms) }}</h3>
      <p class="transcript-text">{{ segment.text }}</p>
    </article>
  </section>
</template>

<style scoped>
article { border-top: 1px solid #dce2e9; margin-top: 20px; padding-top: 12px; }
h3 { font-size: 1rem; }
.transcript-text { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
