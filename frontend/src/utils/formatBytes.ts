/** Decimal units match the existing file list's MB convention. */
export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1_000 && unit < units.length - 1) {
    value /= 1_000;
    unit += 1;
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${units[unit]}`;
}
