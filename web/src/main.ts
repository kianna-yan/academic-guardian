import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/dist/index.css";

import "@/styles/main.css";
import App from "@/App.vue";
import router from "@/router";
import { useAppStore } from "@/stores/app";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(ElementPlus, { locale: zhCn });

// 先把 meta 拿到再挂载，避免首屏闪一下空壳
const store = useAppStore();
store.load().finally(() => app.mount("#app"));
