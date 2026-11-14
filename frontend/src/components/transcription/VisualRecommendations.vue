<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { VisualTranscript } from "../../types/transcription";
import type { StorageSavings } from "../../types/storage";
import { getStorageSavings } from "../../services/storage";
import { formatBytes } from "../../utils/formatBytes";
import { visualOverview } from "../../utils/recommendations";
import RecommendationPanel from "../shared/RecommendationPanel.vue";

const props = defineProps<{
  transcript: VisualTranscript;
  downloading: boolean;
}>();
defineEmits<{ download: [] }>();
const overview = computed(() => visualOverview(props.transcript));
const storage = ref<StorageSavings | null>(null);
const loading = ref(false),
  error = ref("");
let controller: AbortController | undefined;
let version = 0;
async function load(): Promise<void> {
  const requestVersion = ++version;
  controller?.abort();
  controller = new AbortController();
  storage.value = null;
  error.value = "";
  loading.value = true;
  try {
    const result = await getStorageSavings(
      props.transcript.file_id,
      controller.signal,
    );
    if (requestVersion === version) storage.value = result;
  } catch {
    if (requestVersion === version)
      error.value =
        "Storage measurements are unavailable. No removal recommendation can be made from file sizes.";
  } finally {
    if (requestVersion === version) loading.value = false;
  }
}
watch(
  () => props.transcript,
  () => void load(),
  { immediate: true },
);
onBeforeUnmount(() => {
  version++;
  controller?.abort();
});
const savings = computed(
  () =>
    storage.value?.status === "completed" &&
    (storage.value.storage_saved_bytes ?? 0) > 0,
);
function percent(value: number): string {
  return (Math.floor(value * 100) / 100).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  });
}
</script>
<template>
  <RecommendationPanel
    title="Recommended next steps"
    description="Review the compact document and measured storage results before deciding whether you still need the original MP4."
  >
    <template #summary>
      <div class="recommendation-stats">
        <div>
          <strong>{{ overview.visualSections }}</strong><span
            >Visual sections</span
          >
        </div>
        <div>
          <strong>{{ overview.uniqueImages }}</strong><span
            >Distinct saved images</span
          >
        </div>
        <div>
          <strong>{{ overview.speechSegments }}</strong><span
            >Speech segments preserved</span
          >
        </div>
      </div>
    </template>
    <div class="recommendation-list">
      <article class="recommendation-item">
        <span class="recommendation-badge">1 · Export document</span>
        <h3>Keep a readable copy with key visuals</h3>
        <p>
          Export the offline HTML document and verify that the images and spoken
          text you need are included.
        </p>
        <button :disabled="downloading" @click="$emit('download')">
          {{
            downloading ? "Preparing document…" : "Download optimized document"
          }}
        </button>
      </article>
      <article class="recommendation-item">
        <span class="recommendation-badge" :class="savings ? 'review' : ''"
          >2 ·
          {{
            savings ? "Review original for replacement" : "Retain original"
          }}</span
        >
        <p v-if="loading" role="status">Checking actual output sizes…</p>
        <template v-else-if="savings && storage">
          <h3>
            {{ percent(storage.reduction_percent!) }}% potential storage
            reduction
          </h3>
          <div class="recommendation-evidence">
            <span>Original: {{ formatBytes(storage.original_size_bytes) }}</span
            ><span
              >Download file:
              {{ formatBytes(storage.optimized_size_bytes!) }}</span
            ><span
              >Potential saving:
              {{ formatBytes(storage.storage_saved_bytes!) }}</span
            >
          </div>
          <p>
            Consider replacing
            <span class="recommendation-file">{{ transcript.filename }}</span>
            only after verifying the downloaded HTML document and confirming you
            no longer need the original audio or video.
          </p>
        </template>
        <template v-else-if="storage?.status === 'completed'"
          ><h3>No storage savings measured</h3>
          <p>
            The exported text and images are the same size or larger than the
            original MP4.
          </p></template
        >
        <template v-else
          ><h3>Storage savings cannot be confirmed</h3>
          <p>
            {{
              error ||
              storage?.message ||
              "Actual file-size measurements are not available."
            }}
          </p>
          <button v-if="error" @click="load">
            Retry measurements
          </button></template
        >
      </article>
      <article class="recommendation-item">
        <span class="recommendation-badge exact">3 · Image reuse</span>
        <h3>
          {{
            overview.reusedImages
              ? "Repeated visuals share image files"
              : "Distinct visuals preserved"
          }}
        </h3>
        <p v-if="overview.reusedImages">
          {{ overview.reusedImages }} repeated visual
          {{
            overview.reusedImages === 1 ? "interval reuses" : "intervals reuse"
          }}
          existing image files automatically.
        </p>
        <p v-else>
          {{
            overview.uniqueImages
              ? "Each saved visual is distinct and used by the document."
              : "No distinct visual was detected; keep the speech transcript."
          }}
        </p>
      </article>
    </div>
  </RecommendationPanel>
</template>
