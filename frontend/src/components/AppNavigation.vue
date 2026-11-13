<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <nav aria-label="Main navigation">
    <RouterLink :to="{ name: 'files' }">Files</RouterLink>
    <RouterLink :to="{ name: 'extract' }">PDF Extraction</RouterLink>
    <RouterLink :to="{ name: 'search' }">Document Search</RouterLink>
    <RouterLink :to="{ name: 'duplicates' }">Duplicates</RouterLink>
    <RouterLink :to="{ name: 'transcription' }">Video Transcription</RouterLink>
  </nav>
</template>

<style scoped>
nav { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid #dce2e9; }
a {
  padding: 12px 16px;
  color: inherit;
  text-decoration: none;
  border-bottom: 3px solid transparent;
  border-radius: 4px 4px 0 0;
}
a:hover { background: #e8edf4; }
a:focus-visible { outline: 2px solid #175ac6; outline-offset: -2px; }
a.router-link-exact-active { border-bottom-color: #175ac6; color: #175ac6; font-weight: 600; }
@media (max-width: 600px) {
  a { padding: 10px; font-size: 0.9rem; }
}
</style>
