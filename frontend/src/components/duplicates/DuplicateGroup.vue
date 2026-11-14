<script setup lang="ts">
import { RouterLink } from "vue-router";
import { cleanupCopies } from "../../services/duplicates";
import { computed, ref, watch } from "vue";
import { Copy, ChevronRight } from "@lucide/vue";
import type { DuplicateGroup } from "../../types/duplicate";
import { formatBytes } from "../../utils/formatBytes";
import { fileType, fileDestination, formatDate } from "../../utils/files";
import { duplicateRecommendation } from "../../utils/recommendations";
const props = defineProps<{ group: DuplicateGroup; groupNumber: number }>();
const recommendation = computed(() => duplicateRecommendation(props.group));
const emit = defineEmits<{ resolved: [] }>();
const keeperId = ref(recommendation.value?.keep.id ?? 0),
  busy = ref(false),
  error = ref(""),
  confirmation = ref(false);
watch(
  () => props.group.files.map((file) => file.id).join(","),
  () => {
    keeperId.value = recommendation.value?.keep.id ?? 0;
    confirmation.value = false;
    error.value = "";
  },
);
watch(keeperId, () => {
  confirmation.value = false;
});
async function resolve() {
  if (!confirmation.value || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await cleanupCopies(
      keeperId.value,
      props.group.files.map((file) => file.id),
    );
    emit("resolved");
  } catch (cause) {
    error.value =
      cause instanceof Error
        ? cause.message
        : "Cleanup failed. Refresh the case before retrying.";
  } finally {
    busy.value = false;
  }
}
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
        }}<small>potential savings · Review cleanup ↓</small></span
      >
    </summary>
    <div class="duplicate-group-body">
      <div class="cleanup-review">
        <div class="cleanup-review-header">
          <div>
            <h4>Choose a copy to keep</h4>
            <p v-if="recommendation" class="muted" style="margin: 2px 0 10px">
              Suggested keeper: <strong>{{ recommendation.keep.filename }}</strong> (File #{{
                recommendation.keep.id
              }}) — prefers completed analysis, then earliest upload.
            </p>
          </div>
        </div>
        <label :for="`keeper-${groupNumber}`">Retained copy</label
        ><select
          :id="`keeper-${groupNumber}`"
          v-model.number="keeperId"
          :disabled="busy"
        >
          <option v-for="file in group.files" :key="file.id" :value="file.id">
            {{ file.filename }} · File #{{ file.id
            }}{{ file.completed_operations?.length ? " · Analysis ready" : "" }}
          </option>
        </select>
        <label class="cleanup-confirm"
          ><input v-model="confirmation" type="checkbox" :disabled="busy" />I
          confirm removal of the other {{ group.files.length - 1 }} identical
          {{ group.files.length - 1 === 1 ? "copy" : "copies" }} and will keep
          File #{{ keeperId }} (derived text and images remain).</label
        ><button
          class="button-primary"
          :disabled="!confirmation || busy"
          @click="resolve"
        >
          {{
            busy
              ? "Verifying and cleaning up…"
              : "Verify keeper and remove duplicates"
          }}
        </button>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
      </div>
      <h4>Copies in this group</h4>
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
              :class="{ 'keep-copy': file.id === keeperId }"
            >
              <td class="break-word">
                {{ file.filename
                }}<small class="copy-id">File #{{ file.id }}</small>
              </td>
              <td>
                <span
                  class="copy-action"
                  :class="file.id === keeperId ? 'keep' : 'remove'"
                  >{{
                    file.id === keeperId ? "Keep this copy" : "Delete duplicate"
                  }}</span><small v-if="file.id !== keeperId" class="copy-id"
                  >Same content as File #{{ keeperId }}</small
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
.cleanup-review {
  padding: 18px;
  margin-top: 18px;
  border: 1px solid #e1d5b5;
  border-radius: 8px;
  background: #fffdf6;
}
.cleanup-review h4 {
  margin-top: 0;
}
.cleanup-review select {
  max-width: 100%;
}
.cleanup-review p {
  font-size: 12px;
  line-height: 1.7;
  margin: 12px 0;
}
.cleanup-confirm {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin: 16px 0;
  font-size: 13px;
}
.cleanup-confirm input {
  flex-shrink: 0;
  margin-top: 4px;
}

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
