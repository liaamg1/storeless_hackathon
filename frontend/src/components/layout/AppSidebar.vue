<script setup lang="ts">
import { RouterLink } from "vue-router";
import {
  LayoutDashboard,
  Folder,
  Search,
  Copy,
  FileText,
  Video,
  ChartNoAxesColumn,
  PanelLeftClose,
  PanelLeftOpen,
  Layers3,
  ChevronRight,
} from "@lucide/vue";
defineProps<{ collapsed?: boolean }>();
defineEmits<{ toggle: []; navigate: [] }>();
const groups = [
  {
    label: "Workspace",
    items: [
      { name: "overview", label: "Overview", icon: LayoutDashboard },
      { name: "files", label: "Files", icon: Folder },
      { name: "search", label: "Search", icon: Search },
      { name: "duplicates", label: "Duplicates", icon: Copy },
    ],
  },
  {
    label: "Processing",
    items: [
      { name: "extract", label: "PDF Extraction", icon: FileText },
      { name: "transcription", label: "Video Transcription", icon: Video },
    ],
  },
  {
    label: "Analytics",
    items: [
      { name: "storage", label: "Storage Savings", icon: ChartNoAxesColumn },
    ],
  },
];
</script>
<template>
  <div class="sidebar-content" :class="{ collapsed }">
    <RouterLink
      :to="{ name: 'overview' }"
      class="brand"
      aria-label="ReStore overview"
      @click="$emit('navigate')"
      ><span class="brand-mark"><Layers3 :size="23" /></span
      ><span v-if="!collapsed"
        >ReStore<span class="brand-dot">.</span></span
      ></RouterLink
    >
    <div v-if="!collapsed" class="workspace-label">
      <span class="workspace-avatar">R</span>
      <div>Hackathon Workspace<small>Intelligent storage</small></div>
      <ChevronRight :size="14" />
    </div>
    <nav aria-label="Main navigation">
      <div v-for="group in groups" :key="group.label" class="nav-group">
        <p v-if="!collapsed" class="nav-group-label">{{ group.label }}</p>
        <RouterLink
          v-for="item in group.items"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-link"
          :title="collapsed ? item.label : undefined"
          :aria-label="collapsed ? item.label : undefined"
          @click="$emit('navigate')"
        >
          <component :is="item.icon" :size="18" aria-hidden="true" /><span
            v-if="!collapsed"
            >{{ item.label }}</span
          >
        </RouterLink>
      </div>
    </nav>
    <div class="sidebar-bottom">
      <div v-if="!collapsed" class="sidebar-project">
        <span class="live-dot" />Ericsson Hackathon<small
          >ReStore · Demo workspace</small
        >
      </div>
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
