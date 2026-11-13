<script setup lang="ts">
import type { DocumentDetails } from "../../types/document";

defineProps<{ document: DocumentDetails }>();
</script>

<template>
  <section aria-labelledby="document-heading">
    <h2 id="document-heading">Document information</h2>
    <dl>
      <dt>Filename</dt><dd>{{ document.filename }}</dd>
      <dt>Size</dt><dd>{{ (document.size_bytes / 1_000).toFixed(1) }} KB</dd>
      <dt>Pages</dt><dd>{{ document.page_count }}</dd>
      <dt>Extraction status</dt>
      <dd>{{ document.status === "completed" ? "Completed" : "No extracted pages stored" }}</dd>
    </dl>
    <p v-if="document.status === 'not_processed'">
      This file has no extracted pages. Upload its original PDF to extract text.
    </p>
  </section>
</template>
