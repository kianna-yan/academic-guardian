import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  // 相对路径：页面被挂在子路径、或被预览面板以非根路径打开时，/assets 这种
  // 根绝对引用会 404 导致白屏。用 "./" 让它跟着 index.html 所在位置走。
  // 接口请求仍是 /api（后端在根），不受影响。
  base: "./",
  plugins: [
    vue(),
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
