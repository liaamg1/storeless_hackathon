<script setup lang="ts">
import { formatBytes } from "../../utils/formatBytes";
import type { DocumentDetails } from "../../types/document";

defineProps<{ document: DocumentDetails }>();
</script>

<template>
  <section aria-labelledby="document-heading">
    <h2 id="document-heading">Document information</h2>
    <dl>
      <dt>Filename</dt>
      <dd>{{ document.filename }}</dd>
      <dt>Size</dt>
      <dd>{{ formatBytes(document.size_bytes) }}</dd>
      <dt>Pages</dt>
      <dd>{{ document.page_count }}</dd>
      <dt>Extraction status</dt>
      <dd>
        {{
          document.status === "completed"
            ? "Completed"
            : "No extracted pages stored"
        }}
      </dd>
    </dl>
    <p v-if="document.status === 'not_processed'">
      This file has no extracted pages. Upload its original PDF to extract text.
    </p>
  </section>
</template>
