<script setup lang="ts">
defineProps<{ title: string; description: string }>();
</script>
<template>
  <section class="recommendations-panel" :aria-label="title">
    <header>
      <p class="eyebrow">Recommendations</p>
      <h2>{{ title }}</h2>
      <p class="recommendation-description">{{ description }}</p>
      <slot name="summary" />
    </header>
    <slot />
    <p class="recommendation-footnote">
      Recommendations only · No files have been deleted.
    </p>
  </section>
</template>
<style scoped>
.recommendations-panel {
  border: 1px solid #d6e4f3;
  border-radius: 12px;
  padding: clamp(18px, 3vw, 28px);
  margin: 22px 0;
  background: #f7faff;
}
h2 {
  margin: 6px 0 10px;
  font-size: 19px;
}
.recommendation-description {
  color: #53677f;
  line-height: 1.7;
  font-size: 13px;
  margin: 0 0 18px;
}
.recommendation-footnote {
  color: #66768c;
  font-size: 12px;
  margin: 18px 0 0;
}
:deep(.recommendation-list) {
  display: grid;
  gap: 12px;
}
:deep(.recommendation-item) {
  background: white;
  border: 1px solid #dce5ef;
  border-radius: 10px;
  padding: 18px;
  min-width: 0;
}
:deep(.recommendation-item h3) {
  margin: 10px 0;
  font-size: 15px;
  overflow-wrap: anywhere;
}
:deep(.recommendation-item p) {
  margin: 8px 0;
  line-height: 1.75;
  color: #53677f;
  font-size: 13px;
  overflow-wrap: anywhere;
}
:deep(.recommendation-badge) {
  display: inline-flex;
  padding: 4px 9px;
  border-radius: 6px;
  background: #edf4fc;
  color: #315978;
  font-size: 11px;
  font-weight: 600;
}
:deep(.recommendation-badge.exact) {
  color: #23634b;
  background: #eaf7f0;
}
:deep(.recommendation-badge.review) {
  color: #805522;
  background: #fff6e5;
}
:deep(.recommendation-evidence) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  padding: 10px 0;
  color: #53677f;
  font-size: 12px;
}
:deep(.recommendation-file) {
  overflow-wrap: anywhere;
  font-weight: 600;
  color: #192e4b;
}
:deep(.recommendation-stats) {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
:deep(.recommendation-stats div) {
  padding: 14px;
  border-radius: 8px;
  background: white;
  border: 1px solid #dce5ef;
}
:deep(.recommendation-stats strong) {
  display: block;
  font-size: 23px;
  margin-bottom: 5px;
}
:deep(.recommendation-stats span) {
  font-size: 12px;
  color: #53677f;
}
@media (max-width: 600px) {
  :deep(.recommendation-stats) {
    grid-template-columns: 1fr;
  }
}
</style>
