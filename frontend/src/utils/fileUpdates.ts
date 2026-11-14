/** Notify open views only after the backend confirms a file-changing action. */
export const FILES_CHANGED = "restore:files-changed";
export const FILES_CHANGED_KEY = "restore:files-revision";

export function notifyFilesChanged(): void {
  window.dispatchEvent(new Event(FILES_CHANGED));
  try {
    // The storage event reaches other tabs; backend state remains authoritative.
    window.localStorage.setItem(
      FILES_CHANGED_KEY,
      `${Date.now()}:${Math.random()}`,
    );
  } catch {
    // Same-tab refresh still works when browser storage is disabled.
  }
}
