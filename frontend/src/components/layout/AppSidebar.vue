<script setup lang="ts">
import { useRoute, RouterLink, type RouteLocationRaw } from "vue-router";
import {
  LayoutDashboard,
  Folder,
  Search,
  Copy,
  FileText,
  Video,
  Presentation,
  ChartNoAxesColumn,
  PanelLeftClose,
  PanelLeftOpen,
  Layers3,
  UploadCloud,
  Sparkles,
} from "@lucide/vue";
defineProps<{ collapsed?: boolean }>();
defineEmits<{ toggle: []; navigate: [] }>();
const route = useRoute();

interface NavItem {
  id: string;
  name: string;
  label: string;
  to: RouteLocationRaw;
  icon: unknown;
  isActive: () => boolean;
}

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: "Workspace",
    items: [
      {
        id: "home",
        name: "upload",
        label: "Home · Upload",
        to: { name: "upload", query: { tab: "upload" } },
        icon: UploadCloud,
        isActive: () =>
          route.name === "upload" &&
          (route.query.tab === "upload" || Boolean(route.query.file)),
      },
      {
        id: "files",
        name: "files",
        label: "Files",
        to: { name: "files" },
        icon: Folder,
        isActive: () => route.name === "files",
      },
      {
        id: "opportunities",
        name: "upload",
        label: "Opportunities",
        to: { name: "upload", query: { tab: "review" } },
        icon: Sparkles,
        isActive: () =>
          route.name === "upload" &&
          route.query.tab !== "upload" &&
          !route.query.file,
      },
      {
        id: "duplicates",
        name: "duplicates",
        label: "Duplicate cleanup",
        to: { name: "duplicates" },
        icon: Copy,
        isActive: () => route.name === "duplicates",
      },
      {
        id: "search",
        name: "search",
        label: "Search",
        to: { name: "search" },
        icon: Search,
        isActive: () => route.name === "search",
      },
    ],
  },
  {
    label: "More tools",
    items: [
      {
        id: "transcription",
        name: "transcription",
        label: "Video transcription",
        to: { name: "transcription" },
        icon: Video,
        isActive: () => route.name === "transcription",
      },
      {
        id: "slides",
        name: "slides",
        label: "Slide comparison",
        to: { name: "slides" },
        icon: Presentation,
        isActive: () => route.name === "slides",
      },
      {
        id: "extract",
        name: "extract",
        label: "Document text",
        to: { name: "extract" },
        icon: FileText,
        isActive: () => route.name === "extract",
      },
      {
        id: "storage",
        name: "storage",
        label: "Storage savings",
        to: { name: "storage" },
        icon: ChartNoAxesColumn,
        isActive: () => route.name === "storage",
      },
      {
        id: "overview",
        name: "overview",
        label: "Dashboard",
        to: { name: "overview" },
        icon: LayoutDashboard,
        isActive: () => route.name === "overview",
      },
    ],
  },
];
</script>
<template>
  <div class="sidebar-content" :class="{ collapsed }">
    <RouterLink
      :to="{ name: 'upload', query: { tab: 'review' } }"
      class="brand"
      aria-label="ReStore workspace"
      @click="$emit('navigate')"
      ><span class="brand-mark"><Layers3 :size="23" /></span
      ><span v-if="!collapsed"
        >ReStore<span class="brand-dot">.</span></span
      ></RouterLink
    >
    <nav aria-label="Main navigation">
      <component
        :is="group.label === 'More tools' ? 'details' : 'div'"
        v-for="group in groups"
        :key="group.label"
        class="nav-group"
        :open="
          collapsed ||
          group.items.some((item) => item.isActive()) ||
          undefined
        "
      >
        <summary
          v-if="group.label === 'More tools'"
          :aria-label="collapsed ? 'More tools' : undefined"
        >
          {{ collapsed ? "•••" : "More tools" }}
        </summary>
        <p
          v-if="!collapsed && group.label !== 'More tools'"
          class="nav-group-label"
        >
          {{ group.label }}
        </p>
        <RouterLink
          v-for="item in group.items"
          :key="item.id"
          :to="item.to"
          class="nav-link"
          :class="{ 'is-active': item.isActive() }"
          :title="collapsed ? item.label : undefined"
          :aria-label="collapsed ? item.label : undefined"
          @click="$emit('navigate')"
        >
          <component :is="item.icon" :size="18" aria-hidden="true" /><span
            v-if="!collapsed"
            >{{ item.label }}</span
          >
        </RouterLink>
      </component>
    </nav>
    <div class="sidebar-bottom">
      <button
        class="collapse-button"
        :aria-label="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        @click="$emit('toggle')"
      >
        <component
          :is="collapsed ? PanelLeftOpen : PanelLeftClose"
          :size="18"
        /><span v-if="!collapsed">Collapse sidebar</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.sidebar-content {
  min-height: 0;
  overflow: hidden;
}
.sidebar-content > .brand,
.sidebar-bottom {
  flex-shrink: 0;
}
nav {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: #53677f transparent;
  padding-bottom: 12px;
}
summary {
  cursor: pointer;
  padding: 10px 12px;
  font-size: 12px;
  color: #aab8ce;
}
</style>
