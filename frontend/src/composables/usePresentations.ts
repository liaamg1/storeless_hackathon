import { onBeforeUnmount, onMounted, ref } from "vue";
import {
  listPresentations,
  getPresentation,
  getSlideComparison,
  analyzePresentation,
  uploadPresentation,
} from "../services/presentations";
import type {
  PresentationRecord,
  PresentationComparison,
} from "../types/presentation";

export function usePresentations() {
  const presentations = ref<PresentationRecord[]>([]);
  const selected = ref<PresentationRecord | null>(null);
  const comparison = ref<PresentationComparison | null>(null);
  const listLoading = ref(true);
  const loading = ref(false),
    uploading = ref(false),
    error = ref(""),
    listError = ref("");
  let timer: ReturnType<typeof setTimeout> | undefined;
  let version = 0,
    listVersion = 0,
    active = true;
  async function refreshList(): Promise<void> {
    const current = ++listVersion;
    listError.value = "";
    listLoading.value = true;
    try {
      const rows = await listPresentations();
      if (active && current === listVersion) presentations.value = rows;
    } catch (failure) {
      if (active && current === listVersion)
        listError.value =
          failure instanceof Error
            ? failure.message
            : "Could not load presentations.";
    } finally {
      if (active && current === listVersion) listLoading.value = false;
    }
  }
  async function poll(id: number, current: number): Promise<void> {
    try {
      const record = await getPresentation(id);
      if (current !== version || !active) return;
      selected.value = record;
      if (record.status === "completed") {
        const result = await getSlideComparison(id);
        if (current === version && active) {
          comparison.value = result;
          void refreshList();
        }
      } else if (record.status === "queued" || record.status === "processing") {
        timer = setTimeout(() => void poll(id, current), 1500);
      } else if (record.status === "failed") void refreshList();
    } catch (failure) {
      if (current === version && active)
        error.value =
          failure instanceof Error
            ? failure.message
            : "Could not load analysis.";
    } finally {
      if (current === version && active) loading.value = false;
    }
  }
  function select(id: number): void {
    version++;
    clearTimeout(timer);
    selected.value = null;
    comparison.value = null;
    error.value = "";
    loading.value = false;
    if (Number.isSafeInteger(id) && id > 0) {
      loading.value = true;
      void poll(id, version);
    }
  }
  async function analyze(): Promise<void> {
    if (!selected.value || loading.value) return;
    const id = selected.value.file_id,
      current = version;
    loading.value = true;
    error.value = "";
    try {
      await analyzePresentation(id);
      if (current === version && active) select(id);
    } catch (failure) {
      if (current === version && active) {
        error.value =
          failure instanceof Error
            ? failure.message
            : "Could not start analysis.";
        loading.value = false;
      }
    }
  }
  async function upload(file: File): Promise<PresentationRecord | null> {
    if (uploading.value) return null;
    uploading.value = true;
    error.value = "";
    try {
      const record = await uploadPresentation(file);
      void refreshList();
      return record;
    } catch (failure) {
      if (active)
        error.value =
          failure instanceof Error
            ? failure.message
            : "Could not upload presentation.";
      return null;
    } finally {
      if (active) uploading.value = false;
    }
  }
  onMounted(refreshList);
  onBeforeUnmount(() => {
    active = false;
    version++;
    clearTimeout(timer);
  });
  return {
    presentations,
    listLoading,
    selected,
    comparison,
    loading,
    uploading,
    error,
    listError,
    refreshList,
    select,
    analyze,
    upload,
  };
}
