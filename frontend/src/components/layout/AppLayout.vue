<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter, RouterView } from "vue-router";
import AppSidebar from "./AppSidebar.vue";
import AppHeader from "./AppHeader.vue";
const route = useRoute();
const router = useRouter();
const collapsed = ref(false);
const mobileNav = ref<HTMLDialogElement | null>(null);
function shortcut(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    void router
      .push({ name: "search" })
      .then(() =>
        nextTick(() => document.getElementById("document-search")?.focus()),
      );
  }
}
watch(
  () => route.fullPath,
  () => {
    mobileNav.value?.close();
  },
);
watch(
  () => route.meta.title,
  (title) => {
    document.title = `${title || "Workspace"} · ReStore`;
  },
  { immediate: true },
);
function closeDesktopDrawer(): void {
  if (window.innerWidth > 900) mobileNav.value?.close();
}
onMounted(() => {
  window.addEventListener("keydown", shortcut);
  window.addEventListener("resize", closeDesktopDrawer);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", shortcut);
  window.removeEventListener("resize", closeDesktopDrawer);
});
</script>
<template>
  <a href="#main-content" class="skip-link">Skip to content</a>
  <div class="app-shell" :class="{ 'sidebar-collapsed': collapsed }">
    <aside class="desktop-sidebar">
      <AppSidebar :collapsed="collapsed" @toggle="collapsed = !collapsed" />
    </aside>
    <div class="app-main">
      <AppHeader
        @menu="mobileNav?.showModal()"
        @upload="router.push({ name: 'upload', query: { tab: 'upload' } })"
      />
      <main id="main-content" tabindex="-1" class="page-content">
        <RouterView />
      </main>
      <footer class="app-footer">
        <span>ReStore</span> · Intelligent document storage<span
          >Original files are retained</span
        >
      </footer>
    </div>
  </div>
  <dialog
    ref="mobileNav"
    class="mobile-navigation"
    aria-label="Navigation"
    @click="
      (event) => {
        if (event.target === mobileNav) mobileNav?.close();
      }
    "
  >
    <AppSidebar
      @navigate="mobileNav?.close()"
      @toggle="mobileNav?.close()"
    /><button class="mobile-nav-close" @click="mobileNav?.close()">
      Close navigation
    </button>
  </dialog>
</template>
