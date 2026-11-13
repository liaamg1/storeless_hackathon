<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import {
  analyzeVisuals,
  downloadVisualTranscript,
  getVisualTranscript,
  visualImageUrl,
} from "../../services/transcription";
import { formatTimestamp } from "../../utils/formatTimestamp";
import type { VisualTranscript } from "../../types/transcription";

const props = defineProps<{ fileId: number }>();
const showTimestamps = defineModel<boolean>("showTimestamps", {
  default: false,
});
const emit = defineEmits<{ status: [value: string] }>();
const result = ref<VisualTranscript | null>(null);
const error = ref("");
const starting = ref(false);
const loading = ref(false);
const downloading = ref(false);
const downloadError = ref("");
const hasVisuals = computed(() =>
  result.value?.sections.some((section) => section.visual),
);
let generation = 0;
let timer: ReturnType<typeof setTimeout> | undefined;

async function load(version: number): Promise<void> {
  loading.value = true;
  try {
    const data = await getVisualTranscript(props.fileId);
    if (version !== generation) return;
    result.value = data;
    error.value = "";
    emit("status", data.status);
    if (data.status === "queued" || data.status === "processing") {
      timer = setTimeout(() => void load(version), 3000);
    }
  } catch (cause) {
    if (version === generation)
      error.value =
        cause instanceof Error
          ? cause.message
          : "Could not load visual transcript.";
  } finally {
    if (version === generation) loading.value = false;
  }
}

function reload(): void {
  clearTimeout(timer);
  void load(++generation);
}

async function start(): Promise<void> {
  const version = generation;
  starting.value = true;
  error.value = "";
  try {
    await analyzeVisuals(props.fileId);
    if (version === generation) {
      starting.value = false;
      reload();
    }
  } catch (cause) {
    if (version === generation)
      error.value =
        cause instanceof Error
          ? cause.message
          : "Could not start visual analysis.";
  } finally {
    if (version === generation) starting.value = false;
  }
}

async function saveDocument(): Promise<void> {
  if (!result.value || result.value.status !== "completed" || downloading.value)
    return;
  const version = generation;
  const fileId = props.fileId;
  const filename =
    result.value.filename.replace(/\.mp4$/i, "") + "-visual-transcript.html";
  downloading.value = true;
  downloadError.value = "";
  try {
    const blob = await downloadVisualTranscript(fileId, showTimestamps.value);
    if (version !== generation) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  } catch (cause) {
    if (version === generation)
      downloadError.value =
        cause instanceof Error
          ? cause.message
          : "Could not download visual transcript.";
  } finally {
    if (version === generation) downloading.value = false;
  }
}

watch(
  () => props.fileId,
  () => {
    result.value = null;
    starting.value = false;
    downloading.value = false;
    downloadError.value = "";
    reload();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  generation++;
  clearTimeout(timer);
});
</script>

<template>
  <section class="visual-reader" aria-labelledby="visual-transcript-heading">
    <header>
      <p class="eyebrow">Recording knowledge</p>
      <h2 id="visual-transcript-heading">Visual Transcript</h2>
      <p v-if="result" class="visual-filename">{{ result.filename }}</p>
      <p class="muted">
        Important screen content paired with the words spoken while it was
        displayed. Select an image to inspect it.
      </p>
    </header>
    <div v-if="result?.status === 'completed'" class="visual-actions">
      <label v-if="hasVisuals" class="timestamp-toggle"
        ><input v-model="showTimestamps" type="checkbox" />Show
        timestamps</label
      >
      <button
        class="visual-download"
        :disabled="downloading"
        @click="saveDocument"
      >
        {{
          downloading
            ? "Preparing download…"
            : hasVisuals
              ? "Download with pictures (.html)"
              : "Download document (.html)"
        }}
      </button>
      <p class="muted export-note">
        One HTML file that opens offline. The download uses your timestamp
        setting.
      </p>
    </div>
    <p v-if="downloadError" class="error" role="alert">{{ downloadError }}</p>
    <p v-if="loading && !result" role="status">Loading visual transcript…</p>
    <div v-if="error" role="alert">
      <p class="error">{{ error }}</p>
      <button @click="reload">Retry loading</button>
    </div>
    <template v-if="result">
      <div
        v-if="result.status === 'queued' || result.status === 'processing'"
        class="visual-notice"
        role="status"
      >
        {{
          result.status === "queued"
            ? "Visual analysis is queued."
            : "Extracting and comparing screen content…"
        }}
        Your speech transcript is ready below.
      </div>
      <div v-else-if="result.status === 'failed'" class="visual-notice">
        <p role="alert">
          {{ result.error_message || "Visual analysis failed." }} Your speech
          transcript is preserved.
        </p>
        <button :disabled="starting" @click="start">
          {{ starting ? "Queuing…" : "Retry visual analysis" }}
        </button>
      </div>
      <div v-else-if="result.status === 'not_processed'" class="visual-notice">
        <p>This recording has not been analyzed for visual content.</p>
        <button :disabled="starting" @click="start">
          {{ starting ? "Queuing…" : "Extract visuals" }}
        </button>
      </div>
      <p v-else-if="!hasVisuals" class="muted">
        No distinct visual content was detected. The speech transcript is shown
        below.
      </p>
      <slot v-if="!hasVisuals" />
      <template v-else>
        <article
          v-for="(section, index) in result.sections"
          :key="section.visual?.id ?? `speech-${index}`"
          class="visual-section"
        >
          <template v-if="section.visual">
            <p v-if="showTimestamps" class="visual-time">
              {{ formatTimestamp(section.visual.start_ms) }} –
              {{ formatTimestamp(section.visual.end_ms) }}
            </p>
            <a
              :href="visualImageUrl(fileId, section.visual.id)"
              target="_blank"
              rel="noopener"
              :aria-label="`Expand visual at ${formatTimestamp(section.visual.start_ms)}`"
            >
              <img
                :src="visualImageUrl(fileId, section.visual.id)"
                :alt="`Screen content at ${formatTimestamp(section.visual.start_ms)}`"
                loading="lazy"
                width="640"
                height="360"
              />
            </a>
          </template>
          <p
            v-if="!showTimestamps && section.segments.length"
            class="visual-speech"
          >
            {{
              section.segments
                .map((segment) => segment.text.trim().replace(/\s+/g, " "))
                .join(" ")
            }}
          </p>
          <template v-else>
            <p
              v-for="segment in section.segments"
              :key="segment.id"
              class="visual-speech"
            >
              <small class="visual-time">{{
                formatTimestamp(segment.start_ms)
              }}</small>
              {{ segment.text.trim().replace(/\s+/g, " ") }}
            </p>
          </template>
          <p v-if="!section.segments.length" class="muted">
            No speech during this visual.
          </p>
        </article>
      </template>
    </template>
  </section>
</template>

<style scoped>
.visual-reader {
  padding: clamp(20px, 4vw, 40px);
}
.visual-reader h2 {
  margin: 8px 0;
}
.visual-reader header {
  margin-bottom: 24px;
}
.visual-filename {
  overflow-wrap: anywhere;
  font-weight: 600;
}
.visual-notice {
  padding: 16px;
  background: #f0f5fc;
  border: 1px solid #dbe5f3;
  border-radius: 10px;
  margin-bottom: 20px;
}
.visual-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 20px;
  margin-bottom: 24px;
}
.visual-download {
  background: #175ac6;
  border-color: #175ac6;
  color: white;
}
.export-note {
  flex-basis: 100%;
  margin: 0;
  font-size: 12px;
}
.visual-section {
  max-width: 76ch;
  margin: 0 auto 28px;
  border-bottom: 1px solid #e1e7ef;
  padding-bottom: 20px;
}
.visual-section img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid #dce2e9;
  border-radius: 8px;
  background: white;
}
.visual-time {
  color: #53677f;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.visual-speech {
  line-height: 1.85;
  overflow-wrap: anywhere;
}
.visual-speech small {
  display: block;
}
</style>
