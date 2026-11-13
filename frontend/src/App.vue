<script setup lang="ts">
import { RouterView } from "vue-router";
import AppNavigation from "./components/AppNavigation.vue";
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1>ReStore</h1>
      <p>Intelligent Document Storage</p>
      <AppNavigation />
    </header>
    <main>
      <RouterView />
    </main>
  </div>
</template>
