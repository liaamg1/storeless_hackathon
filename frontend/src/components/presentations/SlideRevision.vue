<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { request } from "../../services/api";
import { slideImageUrl } from "../../services/presentations";
const props = defineProps<{ selectedId: number; comparedId: number }>();
interface Revision {
  selected: { text: string; changed: boolean }[];
  compared: { text: string; changed: boolean }[];
  removed_words: number;
  added_words: number;
  selected_numbers: string[];
  compared_numbers: string[];
  truncated: boolean;
  has_text: boolean;
  text_equal: boolean;
}
const revision = ref<Revision | null>(null),
  error = ref(""),
  overlay = ref(false);
let version = 0;
async function load() {
  const current = ++version;
  revision.value = null;
  error.value = "";
  try {
    const value = await request<Revision>(
      `/presentations/slides/${props.selectedId}/revisions/${props.comparedId}`,
    );
    if (current === version) revision.value = value;
  } catch {
    if (current === version)
      error.value =
        "Change details unavailable. The slide previews remain available.";
  }
}
watch(
  () => [props.selectedId, props.comparedId],
  () => {
    overlay.value = false;
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  version++;
});
</script>
<template>
  <section class="slide-revision" aria-label="Slide changes">
    <h4>What changed?</h4>
    <p class="revision-note">
      Selected slide compared with the chosen match. These labels do not imply
      which version is newer.
    </p>
    <p v-if="error" role="alert">
      {{ error }} <button @click="load">Retry</button>
    </p>
    <p v-else-if="!revision" role="status">Comparing slide text…</p>
    <template v-else
      ><p v-if="!revision.has_text">
        No selectable text to compare. Inspect the images for diagram or
        scanned-text changes.
      </p>
      <p v-else-if="revision.text_equal">
        The extracted wording is identical. Images, formatting or diagrams may
        still differ.
      </p>
      <template v-else
        ><p>
          <strong>{{ revision.removed_words }}</strong> words only in selected ·
          <strong>{{ revision.added_words }}</strong> words only in compared
        </p>
        <div
          v-if="
            revision.selected_numbers.length || revision.compared_numbers.length
          "
          class="number-changes"
        >
          <span
            >Selected numbers:
            <b>{{ revision.selected_numbers.join(", ") || "None" }}</b></span
          ><span
            >Compared numbers:
            <b>{{ revision.compared_numbers.join(", ") || "None" }}</b></span
          >
        </div>
        <div class="revision-pair">
          <div>
            <h5>Selected slide</h5>
            <p>
              <template v-for="(part, index) in revision.selected" :key="index"
                >{{ index ? " " : ""
                }}<mark :class="{ changed: part.changed }">{{
                  part.text
                }}</mark></template
              >
            </p>
          </div>
          <div>
            <h5>Compared slide</h5>
            <p>
              <template v-for="(part, index) in revision.compared" :key="index"
                >{{ index ? " " : ""
                }}<mark :class="{ changed: part.changed }">{{
                  part.text
                }}</mark></template
              >
            </p>
          </div>
        </div></template
      >
      <p v-if="revision.truncated" class="revision-note">
        Text comparison is limited to the first 2,000 words per slide. Review
        the full slide before removing content.
      </p></template
    >
    <label class="overlay-toggle"
      ><input v-model="overlay" type="checkbox" />Show visual difference
      overlay</label
    ><template v-if="overlay"
      ><p class="revision-note">
        Bright areas indicate pixel differences, including layout and font
        changes. This does not measure changed meaning.
      </p>
      <div class="difference-overlay">
        <img
          :src="slideImageUrl(selectedId, false)"
          alt="Selected slide for visual difference"
        /><img
          class="difference-layer"
          :src="slideImageUrl(comparedId, false)"
          alt="Compared slide difference layer"
        /></div
    ></template>
  </section>
</template>
<style scoped>
.slide-revision {
  border: 1px solid #dce5ef;
  border-radius: 8px;
  padding: 18px;
  margin: 18px 0;
  background: #fbfcfe;
}
h4 {
  margin: 0 0 10px;
  font-size: 14px;
}
h5 {
  margin: 0 0 8px;
}
.revision-note {
  font-size: 12px;
  color: #66768c;
  line-height: 1.7;
}
.revision-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.revision-pair > div {
  padding: 14px;
  border: 1px solid #dce5ef;
  border-radius: 8px;
  background: white;
  min-width: 0;
}
.revision-pair p {
  line-height: 1.9;
  overflow-wrap: anywhere;
  font-size: 13px;
}
mark {
  background: transparent;
  color: inherit;
}
mark.changed {
  background: #fff0be;
  outline: 1px solid #dfc56f;
  border-radius: 2px;
}
.number-changes {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 13px;
  margin: 14px 0;
}
.number-changes b {
  background: #fff0be;
  padding: 3px 6px;
}
.overlay-toggle {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  margin-top: 18px;
}
.difference-overlay {
  position: relative;
  isolation: isolate;
  background: black;
  max-width: 960px;
}
.difference-overlay img {
  display: block;
  width: 100%;
  height: auto;
}
.difference-layer {
  position: absolute;
  inset: 0;
  mix-blend-mode: difference;
}
@media (max-width: 650px) {
  .revision-pair {
    grid-template-columns: 1fr;
  }
}
</style>
