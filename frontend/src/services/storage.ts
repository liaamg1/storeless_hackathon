import { request } from "./api";
import type { StorageSavings } from "../types/storage";

export function getStorageSavings(fileId: number, signal?: AbortSignal): Promise<StorageSavings> {
  return request<StorageSavings>(`/files/${fileId}/storage-savings`, { signal });
}
