<script setup lang="ts">
import { ref } from "vue";
import { formatBytes } from "../../utils/formatBytes";

defineProps<{ uploading: boolean; error: string }>();
const emit = defineEmits<{ upload: [file: File] }>();
const selectedFile = ref<File | null>(null);

function selectFile(event: Event): void {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}
</script>

<template>
  <section aria-labelledby="video-upload-heading" class="feature-upload">
    <h2 id="video-upload-heading">Upload recording</h2>
    <p>
      Upload an MP4 recording to extract spoken content as a timestamped
      transcript.
    </p>
    <form @submit.prevent="selectedFile && emit('upload', selectedFile)">
      <label for="video-file">Choose MP4 recording</label>
      <input
        id="video-file"
        type="file"
        accept=".mp4,video/mp4"
        :disabled="uploading"
        @change="selectFile"
      />
      <p v-if="selectedFile">
        {{ selectedFile.name }} · {{ formatBytes(selectedFile.size) }}
      </p>
      <p v-else>No recording selected.</p>
      <button
        class="button-primary"
        type="submit"
        :disabled="!selectedFile || uploading"
      >
        Upload &amp; Transcribe
      </button>
    </form>
    <p v-if="uploading" role="status">Uploading and validating recording...</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </section>
</template>
