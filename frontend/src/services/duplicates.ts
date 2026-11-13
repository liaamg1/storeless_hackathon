import { request } from "./api";
import type { DuplicateResponse } from "../types/duplicate";

export function fetchDuplicateGroups(): Promise<DuplicateResponse> {
  return request<DuplicateResponse>("/duplicates");
}
