<script setup lang="ts">
import { FolderOpen } from "@lucide/vue";
defineProps<{ title: string; description?: string }>();
</script>
<template>
  <div class="empty-state">
    <FolderOpen :size="28" aria-hidden="true" />
    <h3>{{ title }}</h3>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>
