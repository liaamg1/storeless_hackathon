import { createRouter, createWebHistory } from "vue-router";
import DuplicatesView from "../views/DuplicatesView.vue";
import VideoTranscriptionView from "../views/VideoTranscriptionView.vue";
import FilesView from "../views/FilesView.vue";
import PdfExtractionView from "../views/PdfExtractionView.vue";
import DocumentSearchView from "../views/DocumentSearchView.vue";

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", redirect: "/files" },
    { path: "/files", name: "files", component: FilesView },
    { path: "/extract", name: "extract", component: PdfExtractionView },
    { path: "/search", name: "search", component: DocumentSearchView },
    { path: "/duplicates", name: "duplicates", component: DuplicatesView },
    { path: "/transcription", name: "transcription", component: VideoTranscriptionView },
    { path: "/:pathMatch(.*)*", redirect: "/files" },
  ],
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 };
  },
});
