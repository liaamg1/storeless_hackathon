import { onBeforeUnmount, onMounted } from "vue";
import { FILES_CHANGED, FILES_CHANGED_KEY } from "../utils/fileUpdates";

/** Reconcile recommendations after cleanup, including changes in another tab. */
export function useFileUpdates(refresh: () => void | Promise<void>): void {
  const changed = () => {
    void refresh();
  };
  const stored = (event: StorageEvent) => {
    if (event.key === FILES_CHANGED_KEY) changed();
  };
  onMounted(() => {
    window.addEventListener(FILES_CHANGED, changed);
    window.addEventListener("storage", stored);
    window.addEventListener("focus", changed);
  });
  onBeforeUnmount(() => {
    window.removeEventListener(FILES_CHANGED, changed);
    window.removeEventListener("storage", stored);
    window.removeEventListener("focus", changed);
  });
}
