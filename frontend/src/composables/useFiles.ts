import { onMounted, ref } from "vue";
import { getFiles } from "../services/api";
import type { FileRecord } from "../types/file";

/** Loads files on mount and exposes the same action for manual refreshes. */
export function useFiles() {
  const files = ref<FileRecord[]>([]);
  const loading = ref(true);
  const error = ref("");

  async function loadFiles() {
    loading.value = true;
    error.value = "";

    try {
      files.value = await getFiles();
    } catch (err) {
      error.value = err instanceof Error ? err.message : "Failed to load files";
    } finally {
      loading.value = false;
    }
  }

  onMounted(loadFiles);

  return { files, loading, error, loadFiles };
}
