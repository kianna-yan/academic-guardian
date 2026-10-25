<script setup lang="ts">
export interface StatItem {
  value: string | number;
  label: string;
  tone?: "red" | "amber" | "";
}

defineProps<{ items: StatItem[] }>();
</script>

<template>
  <div class="stats">
    <div v-for="s in items" :key="s.label" class="stat" :class="s.tone">
      <b>{{ s.value }}</b>
      <span>{{ s.label }}</span>
    </div>
  </div>
</template>
