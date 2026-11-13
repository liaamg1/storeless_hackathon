<script setup lang="ts">
import { useRouter } from "vue-router";
import DocumentSearch from "../components/search/DocumentSearch.vue";

const router = useRouter();

function openDocumentPage(fileId: number, pageNumber: number): void {
  void router.push({
    name: "extract",
    query: { file: String(fileId), page: String(pageNumber) },
  });
}

function openTranscriptSegment(fileId: number, segmentId: number): void {
  void router.push({
    name: "transcription",
    query: { file: String(fileId), segment: String(segmentId) },
  });
}
</script>

<template>
  <DocumentSearch @open-page="openDocumentPage" @open-segment="openTranscriptSegment" />
</template>
