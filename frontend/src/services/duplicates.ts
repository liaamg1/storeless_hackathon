import { notifyFilesChanged } from "../utils/fileUpdates";
import { request } from "./api";
import type { DuplicateResponse } from "../types/duplicate";

export function fetchDuplicateGroups(): Promise<DuplicateResponse> {
  return request<DuplicateResponse>("/duplicates");
}

export interface CleanupResolution {
  id: string;
  keeper_id: number;
  removed_ids: number[];
  status: "pending_purge" | "resolved";
  removed_bytes: number;
  measurement_complete: boolean;
  created_at: string;
  completed_at: string | null;
}
export const getCleanupHistory = () =>
  request<CleanupResolution[]>("/duplicates/resolutions");
export async function cleanupCopies(
  keeperId: number,
  memberIds: number[],
): Promise<CleanupResolution> {
  const result = await request<CleanupResolution>("/duplicates/cleanup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      keeper_id: keeperId,
      member_ids: memberIds,
      confirmed: true,
    }),
  });
  notifyFilesChanged();
  return result;
}
export async function finishCleanup(id: string): Promise<CleanupResolution> {
  const result = await request<CleanupResolution>(
    `/duplicates/resolutions/${id}/finish`,
    { method: "POST" },
  );
  notifyFilesChanged();
  return result;
}
