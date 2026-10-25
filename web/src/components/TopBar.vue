<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => (route.meta?.title as string) || "");
const sub = computed(() => (route.meta?.sub as string) || "");
</script>

<template>
  <header class="topbar">
    <div class="topbar-left">
      <h1>{{ title }}</h1>
      <p>{{ sub }}</p>
    </div>
    <div class="topbar-right">
      <slot />
    </div>
  </header>
</template>
