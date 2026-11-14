<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { useFileUpdates } from "../../composables/useFileUpdates";
import { getSlideSources, slideImageUrl } from "../../services/presentations";
const props = defineProps<{ fileId: number; frameId: number }>();
import type { SlideSources } from "../../services/presentations";
const result = ref<SlideSources | null>(null),
  loading = ref(false),
  error = ref("");
let version = 0;
async function load(refresh = false) {
  const current = ++version;
  loading.value = true;
  error.value = "";
  try {
    const data = await getSlideSources(props.fileId, refresh);
    if (current === version) result.value = data;
  } catch {
    if (current === version)
      error.value =
        "Source-slide comparison is unavailable. Your visual transcript is preserved.";
  } finally {
    if (current === version) loading.value = false;
  }
}
useFileUpdates(() => {
  if (result.value) return load();
});
watch(
  () => props.fileId,
  () => {
    version++;
    result.value = null;
    error.value = "";
  },
);
onBeforeUnmount(() => {
  version++;
});
</script>
<template>
  <details
    class="source-slides"
    @toggle="
      (event) => {
        if ((event.target as HTMLDetailsElement).open && !result && !loading)
          void load();
      }
    "
  >
    <summary>Find this visual in uploaded presentations</summary>
    <p v-if="loading" role="status">Comparing cached presentation images…</p>
    <p v-if="error" role="alert">
      {{ error }} <button @click="load(true)">Retry</button>
    </p>
    <template v-if="result"
      ><p class="source-note">
        Possible sources only. Visual similarity can miss changed numbers or
        wording; verify the slide before treating it as the source. Your video
        images remain unchanged.
      </p>
      <p v-if="!result.slides_compared">
        No analyzed presentation images are available. Upload and analyze a PDF
        or PPTX first.
      </p>
      <p
        v-else-if="
          !result.frames.find((frame) => frame.frame_id === frameId)?.matches
            .length
        "
      >
        No source candidate met the matching threshold among
        {{ result.slides_compared }} analyzed slides.
      </p>
      <article
        v-for="match in result.frames.find(
          (frame) => frame.frame_id === frameId,
        )?.matches ?? []"
        :key="match.slide_id"
      >
        <a
          :href="slideImageUrl(match.slide_id, false)"
          target="_blank"
          rel="noopener"
          ><img
            :src="slideImageUrl(match.slide_id)"
            :alt="`${match.filename}, slide ${match.slide_number}`"
            loading="lazy"
        /></a>
        <div>
          <strong>{{ match.filename }} · Slide {{ match.slide_number }}</strong>
          <p>
            {{ match.similarity_percent }}% visual similarity · verify source
          </p>
          <RouterLink
            :to="{ name: 'slides', query: { file: String(match.file_id) } }"
            >Open presentation</RouterLink
          >
          ·
          <a
            :href="slideImageUrl(match.slide_id, false)"
            target="_blank"
            rel="noopener"
            >Inspect source slide</a
          >
        </div>
      </article>
      <p v-if="result.skipped_images" class="source-note">
        {{ result.skipped_images }} unavailable or incompatible images were
        skipped.
      </p>
      <button @click="load(true)">Refresh source candidates</button></template
    >
  </details>
</template>
<style scoped>
.source-slides {
  border: 1px solid #dce5ef;
  padding: 14px;
  border-radius: 8px;
  margin: 16px 0;
  font-size: 13px;
}
summary {
  cursor: pointer;
  color: #175ac6;
  font-weight: 500;
}
.source-note {
  font-size: 12px;
  line-height: 1.7;
  color: #66768c;
}
article {
  display: flex;
  gap: 14px;
  border-top: 1px solid #e1e7ef;
  padding: 14px 0;
  align-items: flex-start;
}
article img {
  width: 150px;
  max-width: 100%;
  height: auto;
  border: 1px solid #dce5ef;
  border-radius: 6px;
}
article > div {
  min-width: 0;
  overflow-wrap: anywhere;
  flex: 1;
}
article p {
  font-size: 12px;
  color: #66768c;
}
@media (max-width: 600px) {
  article {
    flex-direction: column;
  }
}
</style>
