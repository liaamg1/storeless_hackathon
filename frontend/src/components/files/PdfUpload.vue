<script setup lang="ts">
import { FileText } from "@lucide/vue";
import { formatBytes } from "../../utils/formatBytes";
import { ref } from "vue";

defineProps<{ uploading: boolean; error: string; success: string }>();
const emit = defineEmits<{ upload: [file: File] }>();
const selectedFile = ref<File | null>(null);

function selectFile(event: Event): void {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
}
</script>

<template>
  <section aria-labelledby="upload-heading" class="feature-upload">
    <h2 id="upload-heading"><FileText :size="18" /> Upload document</h2>
    <p>
      Extract selectable text from each page. Image-only scans require OCR,
      which is not available.
    </p>
    <form @submit.prevent="selectedFile && emit('upload', selectedFile)">
      <label for="pdf-file">Choose PDF</label>
      <input
        id="pdf-file"
        type="file"
        accept=".pdf,application/pdf"
        :disabled="uploading"
        @change="selectFile"
      />
      <p>
        {{
          selectedFile
            ? `${selectedFile.name} · ${formatBytes(selectedFile.size)}`
            : "No file selected."
        }}
      </p>
      <button
        class="button-primary"
        type="submit"
        :disabled="!selectedFile || uploading"
      >
        {{ uploading ? "Processing..." : "Upload" }}
      </button>
    </form>
    <p v-if="uploading" role="status">Uploading and extracting text...</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="success" role="status">{{ success }}</p>
  </section>
</template>
