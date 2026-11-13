<script setup lang="ts">
import { RouterLink } from "vue-router";
import { computed } from "vue";
import { Copy, ChevronRight } from "@lucide/vue";
import type { DuplicateGroup } from "../../types/duplicate";
import { formatBytes } from "../../utils/formatBytes";
import { fileType, fileDestination, formatDate } from "../../utils/files";
import { duplicateRecommendation } from "../../utils/recommendations";
const props = defineProps<{ group: DuplicateGroup; groupNumber: number }>();
const recommendation = computed(() => duplicateRecommendation(props.group));
</script>
<template>
  <details class="duplicate-card" :open="groupNumber === 1">
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
      <div v-if="recommendation" class="duplicate-advice">
        <p>
          <strong>Keep:</strong> {{ recommendation.keep.filename }}
          <small>(File #{{ recommendation.keep.id }})</small>
        </p>
        <p>
          <strong>Suggested deletion:</strong>
          {{ recommendation.remove.length }} duplicate
          {{ recommendation.remove.length === 1 ? "copy" : "copies" }} listed
          below.
        </p>
        <p class="muted">
          All copies have the same recorded SHA-256 and byte size. The earliest
          known upload is suggested for keeping; file ID breaks ties. Review
          filenames, linked processing results, and any links you rely on before
          removing a copy. Identical uploads can have different processing
          results.
        </p>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>File name</th>
              <th>Suggested action</th>
              <th>Size</th>
              <th>Uploaded</th>
              <th><span class="sr-only">Results</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="file in group.files"
              :key="file.id"
              :class="{ 'keep-copy': file.id === recommendation?.keep.id }"
            >
              <td class="break-word">
                {{ file.filename
                }}<small class="copy-id">File #{{ file.id }}</small>
              </td>
              <td>
                <span
                  class="copy-action"
                  :class="
                    file.id === recommendation?.keep.id ? 'keep' : 'remove'
                  "
                  >{{
                    file.id === recommendation?.keep.id
                      ? "Keep this copy"
                      : "Delete duplicate"
                  }}</span><small
                  v-if="file.id !== recommendation?.keep.id"
                  class="copy-id"
                  >Same content as File #{{ recommendation?.keep.id }}</small
                >
              </td>
              <td class="nowrap">{{ formatBytes(file.size_bytes) }}</td>
              <td class="nowrap">{{ formatDate(file.uploaded_at) }}</td>
              <td>
                <RouterLink
                  :to="
                    fileDestination({
                      id: file.id,
                      type: fileType(file.filename),
                    })
                  "
                  >Open</RouterLink
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <details class="duplicate-evidence">
        <summary>Match evidence</summary>
        <p class="hash">SHA-256: {{ group.sha256 }}</p>
        <p>
          Same recorded size: {{ group.file_size_bytes.toLocaleString() }} bytes
          per file.
        </p>
      </details>
    </div>
  </details>
</template>

<style scoped>
.table-container {
  position: relative;
  max-width: 100%;
}
.duplicate-advice {
  background: #f3f8fd;
  border: 1px solid #dbe5f1;
  border-radius: 9px;
  padding: 14px 18px;
  margin-bottom: 18px;
}
.duplicate-advice p {
  font-size: 13px;
  line-height: 1.75;
  overflow-wrap: anywhere;
  margin: 6px 0;
}
.copy-id {
  display: block;
  color: #66768c;
  font-size: 11px;
  margin-top: 6px;
}
.copy-action {
  display: inline-block;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 11px;
  white-space: nowrap;
}
.copy-action.keep {
  color: #23634b;
  background: #eaf7f0;
}
.copy-action.remove {
  color: #805522;
  background: #fff6e5;
}
.keep-copy {
  background: #f8fcfa;
}
.duplicate-evidence {
  margin-top: 18px;
  font-size: 12px;
  color: #66768c;
}
</style>
