import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 构建产物供 FastAPI 以 /static/analysis-lab/ 挂载 / Build output for FastAPI static mount
export default defineConfig({
  plugins: [react()],
  base: "/static/analysis-lab/",
  build: {
    outDir: "../static/analysis-lab",
    emptyOutDir: true,
  },
  // 开发时把 /api 转到本机 FastAPI，便于本地联调 / Proxy API to FastAPI during dev
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
