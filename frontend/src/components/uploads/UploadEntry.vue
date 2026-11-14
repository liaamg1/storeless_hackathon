<script setup lang="ts">
import { RouterLink } from "vue-router";
import { UploadCloud } from "@lucide/vue";
defineProps<{ description: string }>();
</script>
<template>
  <section class="feature-upload central-entry">
    <p>{{ description }}</p>
    <RouterLink
      class="central-upload-link"
      :to="{ name: 'upload', query: { tab: 'upload' } }"
      ><UploadCloud :size="15" />Upload Files</RouterLink
    >
  </section>
</template>
<style scoped>
.central-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px 16px;
  padding: 12px 16px;
  background: #f8fafd;
}
.central-entry p {
  color: #53677f;
  font-size: 13px;
  margin: 0;
  flex: 1;
  min-width: 180px;
}
.central-upload-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 12px;
  border-radius: 6px;
  background: #006fcf;
  color: white;
  font-size: 12px;
  font-weight: 500;
}
.central-upload-link:hover {
  background: #005caf;
  text-decoration: none;
}
</style>
