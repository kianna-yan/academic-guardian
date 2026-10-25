import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  // 相对路径：页面被挂在子路径、或被预览面板以非根路径打开时，/assets 这种
  // 根绝对引用会 404 导致白屏。用 "./" 让它跟着 index.html 所在位置走。
  // 接口请求仍是 /api（后端在根），不受影响。
  base: "./",
  plugins: [vue()],
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
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ["echarts/core", "echarts/charts", "echarts/renderers"],
          element: ["element-plus"],
        },
      },
    },
  },
});
