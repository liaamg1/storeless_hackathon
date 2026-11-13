<script setup lang="ts">
import { FileText, Video, File, ArrowUpRight, Ellipsis } from "@lucide/vue";
import type { WorkspaceFile } from "../../utils/files";
import { formatDate } from "../../utils/files";
import { formatBytes } from "../../utils/formatBytes";
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
          <th scope="col">Size</th>
          <th scope="col">Status</th>
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
                  : "FILE"
            }}</span>
          </td>
          <td class="nowrap">{{ formatBytes(file.size_bytes) }}</td>
          <td><StatusBadge :status="file.status" /></td>
          <td class="date-column nowrap">{{ formatDate(file.uploaded_at) }}</td>
          <td>
            <button
              class="icon-button"
              :aria-label="`Details for ${file.filename}`"
              @click="$emit('select', file.id)"
            >
              <Ellipsis :size="18" />
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
