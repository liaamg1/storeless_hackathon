<script setup lang="ts">
import { RouterLink } from "vue-router";
import { Copy, ChevronRight } from "@lucide/vue";
import type { DuplicateGroup } from "../../types/duplicate";
import { formatBytes } from "../../utils/formatBytes";
import { fileType, formatDate } from "../../utils/files";
defineProps<{ group: DuplicateGroup; groupNumber: number }>();
</script>
<template>
  <details class="duplicate-card">
    <summary>
      <div>
        <ChevronRight :size="17" class="expand-chevron" /><span
          class="file-type-icon"
          ><Copy :size="18"
        /></span>
        <div>
          <h3>
            Duplicate group {{ groupNumber }}
            <span class="exact-match">Exact match</span>
          </h3>
          <p>
            {{ group.file_count }} matching files ·
            {{ formatBytes(group.file_size_bytes) }} each
          </p>
        </div>
      </div>
      <span class="duplicate-group-savings"
        >{{ formatBytes(group.potential_savings_bytes)
        }}<small>potential savings</small></span
      >
    </summary>
    <div class="duplicate-group-body">
      <p class="hash">SHA-256: {{ group.sha256 }}</p>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>File name</th>
              <th>Size</th>
              <th>Uploaded</th>
              <th><span class="sr-only">Results</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="file in group.files" :key="file.id">
              <td class="break-word">{{ file.filename }}</td>
              <td class="nowrap">{{ formatBytes(file.size_bytes) }}</td>
              <td class="nowrap">{{ formatDate(file.uploaded_at) }}</td>
              <td>
                <RouterLink
                  :to="{
                    name:
                      fileType(file.filename) === 'video'
                        ? 'transcription'
                        : 'extract',
                    query: { file: String(file.id) },
                  }"
                  >Open</RouterLink
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </details>
</template>
