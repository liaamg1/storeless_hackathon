<script setup lang="ts">
import { RouterLink } from "vue-router";
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
  ChevronRight,
} from "@lucide/vue";
defineProps<{ collapsed?: boolean }>();
defineEmits<{ toggle: []; navigate: [] }>();
const groups = [
  {
    label: "Workspace",
    items: [
      { name: "upload", label: "Workspace", icon: Layers3 },
      { name: "files", label: "All files", icon: Folder },
      { name: "duplicates", label: "Duplicate cleanup", icon: Copy },
      { name: "search", label: "Search", icon: Search },
    ],
  },
  {
    label: "More tools",
    items: [
      { name: "overview", label: "Dashboard", icon: LayoutDashboard },
      { name: "slides", label: "Presentation slides", icon: Presentation },
      { name: "extract", label: "Document text", icon: FileText },
      { name: "transcription", label: "Recording documents", icon: Video },
      { name: "storage", label: "Storage details", icon: ChartNoAxesColumn },
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
    <div v-if="!collapsed" class="workspace-label">
      <span class="workspace-avatar">R</span>
      <div>Hackathon Workspace<small>Intelligent storage</small></div>
      <ChevronRight :size="14" />
    </div>
    <nav aria-label="Main navigation">
      <component
        :is="group.label === 'More tools' ? 'details' : 'div'"
        v-for="group in groups"
        :key="group.label"
        class="nav-group"
        :open="collapsed || undefined"
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
          :key="item.name"
          :to="
            item.name === 'upload'
              ? { name: 'upload', query: { tab: 'review' } }
              : { name: item.name }
          "
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
      </component>
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

<style scoped>
.sidebar-content {
  min-height: 0;
  overflow: hidden;
}
.sidebar-content > .brand,
.workspace-label,
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
