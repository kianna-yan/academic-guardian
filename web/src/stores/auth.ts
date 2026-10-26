import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { api, clearToken, getToken, setToken } from "@/api/client";
import type { AuthProfile, Role } from "@/types";

/** 每个端只允许进自己的路由，登录后回自己的首页 */
export const HOME_OF: Record<Role, string> = {
  student: "/student",
  counselor: "/counselor",
  admin: "/admin",
  parent: "/parent",
};

export const useAuthStore = defineStore("auth", () => {
  const token = ref(getToken());
  const profile = ref<AuthProfile | null>(null);
  const ready = ref(false);

  const isLogged = computed(() => !!token.value && !!profile.value);
  const role = computed<Role | null>(() => profile.value?.role ?? null);
  const sid = computed(() => profile.value?.sid ?? null);
  const mustChange = computed(() => !!profile.value?.must_change);

  async function login(r: Role, account: string, password: string) {
    const res = await api.login({ role: r, account, password });
    setToken(res.token);
    token.value = res.token;
    profile.value = res.profile;
    ready.value = true;
    return res;
  }

  /** 刷新页面后用本地 token 换回身份；token 失效就当作未登录 */
  async function hydrate() {
    if (!token.value) {
      ready.value = true;
      return null;
    }
    try {
      const res = await api.me();
      profile.value = res.profile;
    } catch {
      clearToken();
      token.value = "";
      profile.value = null;
    } finally {
      ready.value = true;
    }
    return profile.value;
  }

  function logout() {
    clearToken();
    token.value = "";
    profile.value = null;
    ready.value = true;
  }

  async function changePassword(oldPassword: string, newPassword: string) {
    const res = await api.changePassword({ old_password: oldPassword, new_password: newPassword });
    profile.value = res.profile;
    return res;
  }

  function home() {
    return profile.value ? HOME_OF[profile.value.role] : "/login";
  }

  return {
    token,
    profile,
    ready,
    isLogged,
    role,
    sid,
    mustChange,
    login,
    hydrate,
    logout,
    changePassword,
    home,
  };
});
