<script setup lang="ts">
import type { FileRecord } from "../../types/file";

defineProps<{
  files: FileRecord[];
}>();

const emit = defineEmits<{ select: [fileId: number] }>();

function formatSize(sizeBytes: number): string {
  return (sizeBytes / 1_000_000).toFixed(2);
}

function formatUploadedAt(uploadedAt: string | null): string {
  return uploadedAt ? new Date(uploadedAt).toLocaleString() : "Unknown";
}
</script>

<template>
  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th scope="col">ID</th>
          <th scope="col">Filename</th>
          <th scope="col">Size (MB)</th>
          <th scope="col">SHA-256</th>
          <th scope="col">Uploaded</th>
          <th scope="col">Results</th>
        </tr>
      </thead>

      <tbody>
        <tr v-for="file in files" :key="file.id">
          <td>{{ file.id }}</td>
          <td>{{ file.filename }}</td>
          <td>{{ formatSize(file.size_bytes) }}</td>
          <td class="sha256">{{ file.sha256 }}</td>
          <td>{{ formatUploadedAt(file.uploaded_at) }}</td>
          <td><button type="button" @click="emit('select', file.id)">{{ file.filename.toLowerCase().endsWith(".mp4") ? "View transcript" : "View text" }}</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
