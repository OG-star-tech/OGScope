/**
 * Vite 多入口 SPA：源码在 src/{shared,apps,entries}，产物写入 ../static/analysis-lab/。
 * Multi-entry SPA: sources under src/{shared,apps,entries}; output to ../static/analysis-lab/.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 构建产物供 FastAPI 以 /static/analysis-lab/ 挂载 / Build output for FastAPI static mount
export default defineConfig({
  plugins: [react()],
  base: "/static/analysis-lab/",
  resolve: {
    alias: {
      // 与 web/static/i18n 共用一份文案 / Single source with FastAPI static
      "@i18n": path.resolve(__dirname, "../static/i18n"),
      "@shared": path.resolve(__dirname, "src/shared"),
      "@apps": path.resolve(__dirname, "src/apps"),
      "@core-ui": path.resolve(__dirname, "src/core-ui"),
      "@dev-ui": path.resolve(__dirname, "src/dev-ui"),
      "@core-api": path.resolve(__dirname, "src/coreApi"),
      "@dev-api": path.resolve(__dirname, "src/devApi"),
    },
  },
  build: {
    outDir: "../static/analysis-lab",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        home: path.resolve(__dirname, "home.html"),
        analysis: path.resolve(__dirname, "index.html"),
        system: path.resolve(__dirname, "system.html"),
        camera: path.resolve(__dirname, "camera.html"),
      },
    },
  },
  // 开发时把 /api 转到本机 FastAPI，便于本地联调 / Proxy API to FastAPI during dev
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      // i18n JSON 与 FastAPI /static 一致 / Same as FastAPI static i18n
      "/static": "http://127.0.0.1:8000",
    },
  },
});
