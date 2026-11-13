<script setup lang="ts">
import { useRouter } from "vue-router";
import FilesTable from "../components/files/FilesTable.vue";
import { useFiles } from "../composables/useFiles";

const router = useRouter();
const { files, loading, error, loadFiles } = useFiles();

function openDocument(fileId: number): void {
  const file = files.value.find(file => file.id === fileId);
  const name = file?.filename.toLowerCase().endsWith(".mp4") ? "transcription" : "extract";
  void router.push({ name, query: { file: String(fileId) } });
}
</script>

<template>
  <section aria-labelledby="files-heading">
    <h2 id="files-heading">Saved files</h2>
    <button type="button" :disabled="loading" @click="loadFiles">Refresh files</button>
    <p v-if="loading" role="status">Loading files...</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
    <template v-else>
      <FilesTable :files="files" @select="openDocument" />
      <p v-if="files.length === 0">No files found. Upload a PDF or recording in the PDF Extraction or Video Transcription tab to get started.</p>
    </template>
  </section>
</template>
