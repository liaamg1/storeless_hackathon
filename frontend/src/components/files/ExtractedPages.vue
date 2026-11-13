<script setup lang="ts">
import { computed, nextTick, watch } from "vue";
import type { DocumentPage } from "../../types/document";

function jumpToPage(event: Event): void {
  const target = document.getElementById(
    `document-page-${(event.target as HTMLSelectElement).value}`,
  ) as HTMLDetailsElement | null;
  if (target) {
    target.open = true;
    target.scrollIntoView({ block: "start" });
    target.focus({ preventScroll: true });
  }
}
const props = defineProps<{
  pages: DocumentPage[];
  selectedPage?: number | null;
}>();
const hasText = computed(() =>
  props.pages.some((page) => page.text.trim().length > 0),
);

watch(
  [() => props.pages, () => props.selectedPage],
  async () => {
    if (!props.selectedPage) return;
    await nextTick();
    const target = document.getElementById(
      `document-page-${props.selectedPage}`,
    );
    target?.scrollIntoView({ block: "start" });
    target?.focus({ preventScroll: true });
  },
  { immediate: true, flush: "post" },
);
</script>

<template>
  <section aria-labelledby="text-heading">
    <div class="panel-heading">
      <h2 id="text-heading">Extracted text</h2>
      <label class="page-jump"
        >Jump to page<select
          aria-label="Jump to PDF page"
          :value="selectedPage || pages[0]?.page_number"
          @change="jumpToPage"
        >
          <option
            v-for="page in pages"
            :key="page.page_number"
            :value="page.page_number"
          >
            {{ page.page_number }}
          </option>
        </select></label
      >
    </div>
    <p v-if="pages.length > 0 && !hasText" role="status">
      No selectable text could be extracted. This PDF may contain scanned
      images; OCR is not implemented.
    </p>
    <details
      v-for="page in pages"
      :id="`document-page-${page.page_number}`"
      :key="page.page_number"
      class="document-page"
      :class="{ 'is-selected': page.page_number === selectedPage }"
      :open="page.page_number === (selectedPage || pages[0]?.page_number)"
      tabindex="-1"
      :aria-label="`Page ${page.page_number}`"
    >
      <summary>Page {{ page.page_number }}</summary>
      <div class="document-page-content">
        <pre v-if="page.text.trim()">{{ page.text }}</pre>
        <p v-else>No selectable text on this page.</p>
      </div>
    </details>
  </section>
</template>

<style scoped>
.is-selected {
  border-left: 3px solid #175ac6;
  padding-left: 16px;
}
.document-page {
  scroll-margin-top: 90px;
}
</style>
