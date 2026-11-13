<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { UploadCloud, FileText, Video, X, LoaderCircle } from "@lucide/vue";
import { uploadPdf } from "../../services/api";
import { uploadVideo } from "../../services/transcription";
import { formatBytes } from "../../utils/formatBytes";
const emit = defineEmits<{ close: []; uploaded: [message: string] }>();
const router = useRouter();
const dialog = ref<HTMLDialogElement | null>(null);
const file = ref<File | null>(null);
const uploading = ref(false);
const error = ref("");
const success = ref("");
const dragging = ref(false);
const kind = computed(() =>
  file.value?.name.toLowerCase().endsWith(".mp4") ? "video" : "pdf",
);
const supported = computed(
  () => !!file.value && /\.(pdf|mp4)$/i.test(file.value.name),
);
function choose(candidate?: File): void {
  if (uploading.value) return;
  file.value = candidate ?? null;
  error.value = "";
  success.value = "";
}
function drop(event: DragEvent): void {
  dragging.value = false;
  choose(event.dataTransfer?.files[0]);
}
function close(): void {
  if (!uploading.value) emit("close");
}
async function submit(): Promise<void> {
  if (!file.value || !supported.value || uploading.value) return;
  uploading.value = true;
  error.value = "";
  try {
    if (kind.value === "video") {
      const result = await uploadVideo(file.value);
      success.value =
        "Upload complete. Transcription continues in the background.";
      await router.push({
        name: "transcription",
        query: { file: String(result.file_id) },
      });
    } else {
      const result = await uploadPdf(file.value);
      success.value = "PDF uploaded and text extracted.";
      await router.push({
        name: "extract",
        query: { file: String(result.id) },
      });
    }
    emit("uploaded", success.value);
    emit("close");
  } catch (failure) {
    error.value =
      failure instanceof Error ? failure.message : "Could not upload the file.";
  } finally {
    uploading.value = false;
  }
}
onMounted(() => dialog.value?.showModal());
onBeforeUnmount(() => dialog.value?.close());
</script>
<template>
  <dialog
    ref="dialog"
    class="upload-dialog"
    aria-labelledby="unified-upload-heading"
    @cancel.prevent="close"
    @click="
      (event) => {
        if (event.target === dialog) close();
      }
    "
  >
    <header class="dialog-heading">
      <div>
        <p class="eyebrow">Add to workspace</p>
        <h2 id="unified-upload-heading">Upload a file</h2>
      </div>
      <button
        class="icon-button"
        aria-label="Close upload"
        :disabled="uploading"
        @click="close"
      >
        <X :size="19" />
      </button>
    </header>
    <p class="muted">
      Upload a document or recording. ReStore takes care of the next step.
    </p>
    <form @submit.prevent="submit">
      <label
        class="upload-dropzone"
        :class="{ dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="drop"
      >
        <UploadCloud :size="32" aria-hidden="true" /><strong
          >Choose a file or drop it here</strong
        ><span>PDF documents and MP4 recordings</span
        ><input
          type="file"
          accept=".pdf,.mp4,application/pdf,video/mp4"
          aria-label="Choose PDF or MP4 file"
          :disabled="uploading"
          @change="choose(($event.target as HTMLInputElement).files?.[0])"
        />
      </label>
      <div v-if="file" class="selected-upload">
        <component :is="kind === 'video' ? Video : FileText" :size="22" />
        <div>
          <strong class="break-word">{{ file.name }}</strong><small
            >{{ formatBytes(file.size) }} ·
            {{
              supported
                ? kind === "video"
                  ? "Video transcription"
                  : "PDF text extraction"
                : "Unsupported format"
            }}</small
          >
        </div>
      </div>
      <p v-if="file && !supported" class="error" role="alert">
        Choose a PDF document or MP4 recording.
      </p>
      <p v-if="uploading" class="notice" role="status">
        <LoaderCircle :size="16" class="spin" />{{
          kind === "video"
            ? "Uploading and validating recording. Transcription will run in the background."
            : "Uploading PDF and extracting selectable text…"
        }}
      </p>
      <p v-if="error" class="error notice" role="alert">{{ error }}</p>
      <p v-if="success" role="status">{{ success }}</p>
      <footer class="dialog-actions">
        <button type="button" :disabled="uploading" @click="close">
          Cancel</button
        ><button
          class="button-primary"
          type="submit"
          :disabled="!supported || uploading"
        >
          <UploadCloud :size="16" />{{
            uploading ? "Uploading…" : "Upload file"
          }}
        </button>
      </footer>
    </form>
  </dialog>
</template>
