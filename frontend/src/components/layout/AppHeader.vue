<script setup lang="ts">
import { useRoute, RouterLink } from "vue-router";
import { Menu, Search, Upload, ChevronRight } from "@lucide/vue";
const route = useRoute();
defineEmits<{ menu: []; upload: [] }>();
</script>
<template>
  <header class="topbar">
    <div class="header-location">
      <button
        class="icon-button mobile-menu"
        aria-label="Open navigation"
        @click="$emit('menu')"
      >
        <Menu :size="20" /></button
      ><RouterLink :to="{ name: 'upload' }" class="breadcrumb-root"
        >Workspace</RouterLink
      ><ChevronRight :size="14" class="breadcrumb-root" /><strong>{{
        route.meta.title || "ReStore"
      }}</strong>
    </div>
    <div class="header-actions">
      <RouterLink
        class="header-search"
        :to="{ name: 'search' }"
        aria-label="Search files and content"
        ><Search :size="16" /><span>Search workspace</span
        ><kbd>⌘ / Ctrl K</kbd></RouterLink
      ><button class="button-primary" @click="$emit('upload')">
        <Upload :size="16" /><span>Upload Files</span>
      </button>
    </div>
  </header>
</template>
