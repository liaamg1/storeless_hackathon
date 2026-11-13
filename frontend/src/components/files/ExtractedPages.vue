<script setup lang="ts">
import { computed, nextTick, watch } from "vue";
import type { DocumentPage } from "../../types/document";

const props = defineProps<{ pages: DocumentPage[]; selectedPage?: number | null }>();
const hasText = computed(() => props.pages.some(page => page.text.trim().length > 0));

watch([() => props.pages, () => props.selectedPage], async () => {
  if (!props.selectedPage) return;
  await nextTick();
  const target = document.getElementById(`document-page-${props.selectedPage}`);
  target?.scrollIntoView({ block: "start" });
  target?.focus({ preventScroll: true });
}, { immediate: true, flush: "post" });
</script>

<template>
  <section aria-labelledby="text-heading">
    <h2 id="text-heading">Extracted text</h2>
    <p v-if="pages.length > 0 && !hasText" role="status">
      No selectable text could be extracted. This PDF may contain scanned images; OCR is not implemented.
    </p>
    <article
      v-for="page in pages" :id="`document-page-${page.page_number}`" :key="page.page_number"
      class="document-page" :class="{ 'is-selected': page.page_number === selectedPage }"
      tabindex="-1" :aria-label="`Page ${page.page_number}`"
    >
      <h3>Page {{ page.page_number }}</h3>
      <pre v-if="page.text.trim()">{{ page.text }}</pre>
      <p v-else>No selectable text on this page.</p>
    </article>
  </section>
</template>

<style scoped>
.is-selected { border-left: 3px solid #175ac6; padding-left: 16px; }
.document-page { scroll-margin-top: 20px; }
</style>
