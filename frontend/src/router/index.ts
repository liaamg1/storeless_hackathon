import { createRouter, createWebHistory } from "vue-router";
import SlideComparisonView from "../views/SlideComparisonView.vue";
import OverviewView from "../views/OverviewView.vue";
import StorageSavingsView from "../views/StorageSavingsView.vue";
import DuplicatesView from "../views/DuplicatesView.vue";
import VideoTranscriptionView from "../views/VideoTranscriptionView.vue";
import FilesView from "../views/FilesView.vue";
import PdfExtractionView from "../views/PdfExtractionView.vue";
import DocumentSearchView from "../views/DocumentSearchView.vue";
import UploadFilesView from "../views/UploadFilesView.vue";

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/upload",
      name: "upload",
      component: UploadFilesView,
      meta: { title: "Workspace" },
    },
    {
      path: "/slides",
      name: "slides",
      component: SlideComparisonView,
      meta: { title: "Slide Comparison" },
    },
    { path: "/", redirect: "/upload" },
    {
      path: "/overview",
      name: "overview",
      component: OverviewView,
      meta: { title: "Overview" },
    },
    {
      path: "/storage",
      name: "storage",
      component: StorageSavingsView,
      meta: { title: "Storage Savings" },
    },
    {
      path: "/files",
      name: "files",
      meta: { title: "Files" },
      component: FilesView,
    },
    {
      path: "/extract",
      name: "extract",
      meta: { title: "Document text" },
      component: PdfExtractionView,
    },
    {
      path: "/search",
      name: "search",
      meta: { title: "Search" },
      component: DocumentSearchView,
    },
    {
      path: "/duplicates",
      name: "duplicates",
      meta: { title: "Duplicates" },
      component: DuplicatesView,
    },
    {
      path: "/transcription",
      name: "transcription",
      meta: { title: "Video Transcription" },
      component: VideoTranscriptionView,
    },
    { path: "/:pathMatch(.*)*", redirect: "/files" },
  ],
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 };
  },
});
