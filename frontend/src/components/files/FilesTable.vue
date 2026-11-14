<script setup lang="ts">
import { RouterLink } from "vue-router";
import {
  FileText,
  Video,
  File,
  Presentation,
  ArrowUpRight,
  Ellipsis,
} from "@lucide/vue";
import type { WorkspaceFile } from "../../utils/files";
import { fileDestination, formatDate } from "../../utils/files";
import { formatBytes } from "../../utils/formatBytes";
import FileProgress from "../shared/FileProgress.vue";
import { processingStepLabel } from "../../utils/upload";
import StatusBadge from "../shared/StatusBadge.vue";
defineProps<{ files: WorkspaceFile[] }>();
defineEmits<{ select: [fileId: number] }>();
</script>
<template>
  <div class="table-container files-table">
    <table>
      <thead>
        <tr>
          <th scope="col" class="filename-column">File name</th>
          <th scope="col" class="type-column">Type</th>
          <th scope="col" class="size-column">Size</th>
          <th scope="col" class="status-column">Status</th>
          <th scope="col" class="date-column">Uploaded</th>
          <th scope="col" class="actions-column">
            <span class="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="file in files" :key="file.id">
          <td>
            <button
              class="file-name-button"
              :title="file.filename"
              @click="$emit('select', file.id)"
            >
              <span class="file-type-icon" :class="file.type"
                ><component
                  :is="
                    file.type === 'pdf'
                      ? FileText
                      : file.type === 'video'
                        ? Video
                        : file.type === 'pptx'
                          ? Presentation
                          : File
                  "
                  :size="19" /></span
              ><span class="truncate">{{ file.filename }}</span
              ><ArrowUpRight
                :size="14"
                class="file-open-arrow"
                aria-hidden="true"
              />
            </button>
          </td>
          <td class="type-column">
            <span class="file-extension">{{
              file.type === "video"
                ? "MP4"
                : file.type === "pdf"
                  ? "PDF"
                  : file.type === "pptx"
                    ? "PPTX"
                    : "FILE"
            }}</span>
          </td>
          <td class="size-column nowrap">{{ formatBytes(file.size_bytes) }}</td>
          <td class="status-column">
            <StatusBadge :status="file.status" /><FileProgress
              v-if="['queued', 'processing'].includes(file.status)"
              compact
              :status="file.status"
              :percent="file.processing?.progress_percent"
              :step="
                processingStepLabel(file.processing?.current_step ?? file.status)
              "
            />
          </td>
          <td class="date-column nowrap">{{ formatDate(file.uploaded_at) }}</td>
          <td>
            <div class="table-row-actions">
              <RouterLink
                v-if="file.type !== 'other'"
                class="row-open-link"
                :to="
                  file.type === 'pdf'
                    ? { name: 'extract', query: { file: String(file.id) } }
                    : fileDestination(file)
                "
              >
                {{
                  file.type === "video"
                    ? "Open Transcript"
                    : file.type === "pdf"
                      ? "Open Text"
                      : "Compare Slides"
                }}
              </RouterLink>
              <button
                type="button"
                class="icon-button"
                :aria-label="`Details for ${file.filename}`"
                title="File details & all actions"
                @click="$emit('select', file.id)"
              >
                <Ellipsis :size="18" />
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<style scoped>
.table-row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}
.row-open-link {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 5px;
  border: 1px solid #d7dee8;
  background: #fff;
  color: #175ac6;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.row-open-link:hover {
  background: #f1f5fa;
  border-color: #b5c7da;
  text-decoration: none;
}
</style>
