<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { formatTimestamp } from "../../utils/formatTimestamp";
import type { VideoTranscript } from "../../types/transcription";

const props = defineProps<{
  transcript: VideoTranscript;
  downloading: boolean;
  downloadError: string;
  selectedSegmentId?: number | null;
}>();
defineEmits<{ download: [] }>();

const showTimestamps = ref(false);
const paragraphs = computed(() => {
  const segments = new Map(
    props.transcript.segments.map((segment) => [segment.id, segment]),
  );
  return props.transcript.paragraphs.map((ids) =>
    ids.flatMap((id) => {
      const segment = segments.get(id);
      return segment
        ? [{ ...segment, text: segment.text.trim().replace(/\s+/g, " ") }]
        : [];
    }),
  );
});
// Name the speaker only when the voice changes. Paragraphs also break on pauses
// and length, so consecutive paragraphs often belong to the same speaker.
function speakerOf(index: number): string {
  return paragraphs.value[index]?.[0]?.speaker || "Speaker";
}
function showSpeakerLabel(index: number): boolean {
  if (!paragraphs.value[index]?.length) return false;
  return index === 0 || speakerOf(index) !== speakerOf(index - 1);
}
const wordCount = computed(() =>
  props.transcript.segments.reduce(
    (count, segment) =>
      count + (segment.text.trim().match(/\S+/g)?.length ?? 0),
    0,
  ),
);

// Wait for asynchronous transcript loading and DOM rendering before following a search link.
watch(
  () => [props.transcript, props.selectedSegmentId],
  async () => {
    await nextTick();
    if (!props.selectedSegmentId) return;
    const segment = document.getElementById(
      `transcript-segment-${props.selectedSegmentId}`,
    );
    segment?.scrollIntoView({ block: "center" });
    segment?.focus({ preventScroll: true });
  },
  { immediate: true },
);
</script>

<template>
  <section aria-labelledby="transcript-heading" class="transcript-reader">
    <header class="reader-header">
      <div>
        <p class="eyebrow">Text version</p>
        <h2 id="transcript-heading" :title="transcript.filename">
          {{ transcript.filename.replace(/\.mp4$/i, "") }}
        </h2>
        <p class="reader-meta">{{ wordCount }} words · UTF-8 plain text</p>
      </div>
      <button
        class="download-button"
        type="button"
        :disabled="downloading"
        @click="$emit('download')"
      >
        {{ downloading ? "Preparing download…" : "Download text (.txt)" }}
      </button>
    </header>
    <label class="timestamp-toggle"
      ><input v-model="showTimestamps" type="checkbox" />Show timestamps</label
    >
    <p class="reader-description">
      The spoken content of your recording, saved as a compact, searchable
      document.
    </p>
    <p v-if="downloadError" class="error" role="alert">{{ downloadError }}</p>
    <p v-if="paragraphs.length === 0">
      No speech was detected in this recording.
    </p>
    <div v-else class="transcript-body">
      <p v-for="(paragraph, index) in paragraphs" :key="index">
        <strong
          v-if="showSpeakerLabel(index)"
          class="speaker-label"
          :data-speaker="paragraph[0].speaker"
          >{{ paragraph[0].speaker || "Speaker" }}</strong
        >
        <template
          v-for="(segment, segmentIndex) in paragraph"
          :key="segment.id"
        >
          {{ segmentIndex > 0 ? " " : ""
          }}<span
            :id="`transcript-segment-${segment.id}`"
            tabindex="-1"
            :class="{
              selected: segment.id === selectedSegmentId,
              'timestamped-segment': showTimestamps,
            }"
            :aria-current="
              segment.id === selectedSegmentId ? 'true' : undefined
            "
            ><small v-if="showTimestamps" class="segment-time">{{
              formatTimestamp(segment.start_ms)
            }}</small
            >{{ segment.text }}</span
          >
        </template>
      </p>
    </div>
  </section>
</template>

<style scoped>
.transcript-reader {
  padding: clamp(24px, 5vw, 48px);
}
.reader-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 20px;
}
.eyebrow {
  margin: 0 0 8px;
  color: #53677f;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
h2 {
  margin: 0;
  font-size: clamp(1.4rem, 3vw, 1.9rem);
  overflow-wrap: anywhere;
}
.reader-meta,
.reader-description {
  color: #53677f;
  font-size: 0.9rem;
}
.reader-meta {
  margin: 10px 0 0;
}
.reader-description {
  padding-bottom: 24px;
  border-bottom: 1px solid #dce2e9;
}
.download-button {
  background: #175ac6;
  color: white;
  border-color: #175ac6;
}
.transcript-body {
  max-width: 70ch;
  margin: 32px auto 0;
  font-size: 1.08rem;
  line-height: 1.85;
  overflow-wrap: anywhere;
}
.transcript-body p {
  margin: 0 0 1.4em;
}
.speaker-label {
  display: block;
  margin-bottom: 2px;
  color: #175ac6;
  font-size: 0.8rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.selected {
  background: #fff1b8;
  border-radius: 3px;
  outline: 2px solid #c89923;
  outline-offset: 2px;
}
</style>
