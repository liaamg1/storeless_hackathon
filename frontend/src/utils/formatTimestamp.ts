export function formatTimestamp(milliseconds: number): string {
  const wholeSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(wholeSeconds / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const seconds = wholeSeconds % 60;
  return [hours, minutes, seconds].map(value => String(value).padStart(2, "0")).join(":")
    + `.${String(milliseconds % 1000).padStart(3, "0")}`;
}
