import { createApp } from "vue";
import { createPinia } from "pinia";

// 样式仍用全量：部分组件是通过 `import { ElMessage } from "element-plus"`
// 显式引入的，这类写法走不到按需注入，漏掉就会出现「弹窗没样式」。
// 全量 CSS gzip 后约 40 KB，不是瓶颈；真正大的是那 1 MB JS，已改为按需。
import "element-plus/dist/index.css";

import "@/styles/main.css";
import App from "@/App.vue";
import router from "@/router";
import { useAppStore } from "@/stores/app";

const app = createApp(App);
app.use(createPinia());
app.use(router);

// 不再 app.use(ElementPlus)：那会把整包组件注册进来，抵消按需加载。
// 组件由 vite 插件在编译期按需引入，中文文案走 App.vue 里的 <el-config-provider>。

// 先把 meta 拿到再挂载。index.html 里已放骨架屏，等待期间看到的是骨架而非白屏。
const store = useAppStore();
store.load().finally(() => app.mount("#app"));
