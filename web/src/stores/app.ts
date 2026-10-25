import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { api } from "@/api/client";
import type { Meta, Overview } from "@/types";

export const useAppStore = defineStore("app", () => {
  const meta = ref<Meta | null>(null);
  const overview = ref<Overview | null>(null);
  const loading = ref(true);
  const error = ref("");

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      meta.value = await api.meta();
    } catch (e: any) {
      error.value = e?.message || "初始化失败";
    } finally {
      loading.value = false;
    }
  }

  async function loadOverview() {
    overview.value = await api.overview();
    return overview.value;
  }

  async function saveConfig(body: {
    red_line: number;
    yellow_line: number;
    absence_warn_ratio: number;
  }) {
    const res = await api.saveConfig(body);
    if (meta.value) meta.value.config = res.config;
    overview.value = res.overview;
    return res.overview;
  }

  const week = computed(() => meta.value?.week ?? 1);
  const classes = computed(() => meta.value?.classes ?? []);
  const schools = computed(() => meta.value?.schools ?? []);
  const llmEnabled = computed(() => !!meta.value?.llm?.enabled);

  return {
    meta,
    overview,
    loading,
    error,
    week,
    classes,
    schools,
    llmEnabled,
    load,
    loadOverview,
    saveConfig,
  };
});
