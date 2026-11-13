<script setup lang="ts">
import { useRouter } from "vue-router";
import DocumentSearch from "../components/search/DocumentSearch.vue";

const router = useRouter();

function openDocumentPage(
  fileId: number,
  pageNumber: number,
  fileType: "pdf" | "pptx" = "pdf",
): void {
  void router.push({
    name: fileType === "pptx" ? "slides" : "extract",
    query: { file: String(fileId), page: String(pageNumber) },
  });
}

function openTranscriptSegment(
  fileId: number,
  segmentId: number,
  visual = false,
): void {
  void router.push({
    name: "transcription",
    query: {
      file: String(fileId),
      segment: String(segmentId),
      ...(visual ? { view: "visual" } : {}),
    },
  });
}
</script>

<template>
  <DocumentSearch
    @open-page="openDocumentPage"
    @open-segment="openTranscriptSegment"
  />
</template>
