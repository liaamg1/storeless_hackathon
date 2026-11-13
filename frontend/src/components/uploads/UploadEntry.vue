<script setup lang="ts">
import { RouterLink } from "vue-router";
import { UploadCloud } from "@lucide/vue";
defineProps<{ description: string }>();
</script>
<template>
  <section class="feature-upload central-entry">
    <div>
      <h2>Add files to your workspace</h2>
      <p>{{ description }}</p>
    </div>
    <RouterLink
      class="central-upload-link"
      :to="{ name: 'upload', query: { tab: 'upload' } }"
      ><UploadCloud :size="16" />Upload Files</RouterLink
    >
  </section>
</template>
<style scoped>
.central-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}
.central-entry > div {
  flex: 1;
  min-width: 180px;
}
.central-entry p {
  color: #66768c;
  font-size: 13px;
  margin: 8px 0 0;
}
.central-upload-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #006fcf;
  color: white;
  font-size: 13px;
}
</style>
