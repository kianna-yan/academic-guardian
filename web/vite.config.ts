import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import { fileURLToPath, URL } from "node:url";
import type { Plugin } from "vite";

/**
 * 构建版本自检（解决「不同人打开同一网址看到不同版式」）。
 *
 * 成因：index.html 是无 hash 的固定文件名，浏览器或 CDN 缓存里留着旧的一份时，
 * 它引用的仍是上一版 assets/index-xxxx.js。谁缓存命中旧 HTML，谁看到的就是老界面。
 * 带 hash 的 JS/CSS 本身不会串版本，问题只出在入口 HTML 上。
 *
 * 做法：每次构建生成唯一 build id，写进两份地方——
 *   ① index.html 里 <meta name="build-id">（这份 HTML 自带自己的版本号）
 *   ② 独立的 version.json（永远描述服务器上最新的一版）
 * 页面启动时用 no-store 拉 version.json 与自身比对，不一致就带 ?v= 参数重载一次
 * （新 URL 绕过 HTTP 缓存）。用 sessionStorage 记录已重载过的版本，最多只跳一次，
 * 即使 CDN 把 HTML 彻底钉死也不会死循环。
 */
const BUILD_ID =
  new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14) +
  "-" +
  Math.random().toString(36).slice(2, 6);

function buildVersionPlugin(): Plugin {
  return {
    name: "ag-build-version",
    transformIndexHtml(html) {
      return html.replace(/__BUILD_ID__/g, BUILD_ID);
    },
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "version.json",
        source: JSON.stringify({ build: BUILD_ID, at: new Date().toISOString() }),
      });
    },
  };
}

export default defineConfig({
  // 相对路径：页面被挂在子路径、或被预览面板以非根路径打开时，/assets 这种
  // 根绝对引用会 404 导致白屏。用 "./" 让它跟着 index.html 所在位置走。
  // 接口请求仍是 /api（后端在根），不受影响。
  base: "./",
  plugins: [
    vue(),
    buildVersionPlugin(),
    // 按需加载 Element Plus：模板里的 <el-xxx> 与 ElMessage 这类函数式调用
    // 都由插件在编译期自动补 import 和样式。之前整包 import 会打进 1 MB，
    // 而实际只用十来个组件，其中大部分体积是永远走不到的代码。
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: "src/auto-imports.d.ts",
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: "src/components.d.ts",
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发阶段把接口代理到 FastAPI，避免跨域
      "/api": {
        target: "http://127.0.0.1:8600",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "site",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        // 按 node_modules 路径分组，而不是点名包名：按需引入后
        // element-plus 不再是一个完整入口，点名的写法会把没走到的模块也拉进来。
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return;
          if (id.includes("echarts") || id.includes("zrender")) return "echarts";
          if (id.includes("element-plus") || id.includes("@element-plus")) return "element";
          if (id.includes("vue") || id.includes("pinia") || id.includes("axios")) return "vue";
          return "vendor";
        },
      },
    },
  },
});
