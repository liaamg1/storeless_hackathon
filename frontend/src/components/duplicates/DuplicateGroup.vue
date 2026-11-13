<script setup lang="ts">
import type { DuplicateGroup } from "../../types/duplicate";
import { formatBytes } from "../../utils/formatBytes";

defineProps<{ group: DuplicateGroup; groupNumber: number }>();

function formatUploadDate(uploadedAt: string | null): string {
  return uploadedAt ? new Date(uploadedAt).toLocaleString() : "Unknown";
}
</script>

<template>
  <section :aria-labelledby="`duplicate-group-${groupNumber}`">
    <h2 :id="`duplicate-group-${groupNumber}`">
      Duplicate group {{ groupNumber }}
      <span class="badge">Exact match</span>
    </h2>
    <p>{{ group.file_count }} files · {{ formatBytes(group.file_size_bytes) }} each</p>
    <p>Potential savings: <strong>{{ formatBytes(group.potential_savings_bytes) }}</strong></p>
    <p class="hash">SHA-256: {{ group.sha256 }}</p>
    <div class="table-container">
      <table>
        <caption>Files in duplicate group {{ groupNumber }}</caption>
        <thead>
          <tr><th scope="col">Filename</th><th scope="col">Size</th><th scope="col">Uploaded</th></tr>
        </thead>
        <tbody>
          <tr v-for="file in group.files" :key="file.id">
            <td>{{ file.filename }}</td>
            <td>{{ formatBytes(file.size_bytes) }}</td>
            <td>{{ formatUploadDate(file.uploaded_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.badge { display: inline-block; padding: 4px 8px; border-radius: 4px; background: #e8f3ed; font-size: 0.8rem; }
.hash { font-family: monospace; overflow-wrap: anywhere; }
caption { text-align: left; font-size: 0.9rem; }
</style>
