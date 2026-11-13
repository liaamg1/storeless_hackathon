<script setup lang="ts">
import { Search, SlidersHorizontal } from "@lucide/vue";
import type { FileSort } from "../../utils/files";
const query = defineModel<string>("query", { required: true });
const type = defineModel<string>("type", { required: true });
const status = defineModel<string>("status", { required: true });
const sort = defineModel<FileSort>("sort", { required: true });
</script>
<template>
  <div class="file-toolbar">
    <div class="input-with-icon filename-filter">
      <Search :size="17" aria-hidden="true" /><input
        v-model="query"
        type="search"
        aria-label="Search by filename"
        placeholder="Search by filename…"
      />
    </div>
    <div class="filter-controls">
      <SlidersHorizontal :size="16" class="muted" aria-hidden="true" /><select
        v-model="type"
        aria-label="Filter by file type"
      >
        <option value="all">All file types</option>
        <option value="pdf">PDF documents</option>
        <option value="video">MP4 recordings</option></select
      ><select v-model="status" aria-label="Filter by status">
        <option value="all">All statuses</option>
        <option value="available">Available</option>
        <option value="completed">Completed</option>
        <option value="queued">Queued</option>
        <option value="processing">Processing</option>
        <option value="failed">Failed</option>
        <option value="unknown">Unknown</option></select
      ><select v-model="sort" aria-label="Sort files">
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="name">Name: A–Z</option>
        <option value="name-desc">Name: Z–A</option>
        <option value="size">Size: largest</option>
        <option value="size-asc">Size: smallest</option>
      </select>
    </div>
  </div>
</template>
