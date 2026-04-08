# 星空解算控制台前端 / Plate Solve Console UI

## 用途 / Purpose

- 技术栈：**Vite 5 + React 18 + TypeScript + Tailwind CSS**。
- 入口页面由 FastAPI 在 **`GET /debug/analysis`** 提供：若存在 `web/static/analysis-lab/index.html` 则返回 SPA，否则回退旧版 Jinja 模板。
- 静态资源由 FastAPI 挂载 **`/static`**，本应用 `base` 为 **`/static/analysis-lab/`**。
- 文案 i18n：**`web/static/i18n/analysis.zh.json`**、**`analysis.en.json`**；开发时 Vite 将 **`/static`** 代理到 FastAPI 以便加载上述 JSON。

## 源码布局 / Source layout

- **`src/shared/`**：API 客户端、`i18n`、`context`、工具与 `drawOverlay`（多入口共用）。
- **`src/apps/home/`**：用户首页 HUD（`HomeApp`、注入 `homeHudBody.html`、加载 `/static/js` 既有脚本链）。
- **`src/apps/lab/`**：星空解算实验室（`AnalysisLabApp`、子视图组件）。
- **`src/apps/system/`**：系统调试壳与页面（`SystemConsoleApp`、`DebugShell`、`pages/`）。
- **`src/apps/camera/`**：相机调试台。
- **`src/entries/`**：`home-main.tsx`、`main.tsx`、`system-main.tsx`、`camera-main.tsx` 对应 `home.html`、`index.html`、`system.html`、`camera.html`。
- 路径别名：`@shared/*`、`@apps/*`（见 `vite.config.ts`、`tsconfig.json`），以及 `@i18n` → `web/static/i18n`。

## 按页面单独开发 / Per-page dev

- **仅首页 / Home only**：`npm run dev:home`（打开 `home.html`，不强制同时调试 analysis/system/camera）。
- **仅调试台 / Debug SPAs**：`npm run dev:tools`（打开 `system.html`），或直接 `npm run dev` 在浏览器选不同 html。

## 常用命令 / Commands

```bash
cd web/spa
npm install          # 安装依赖 / Install deps
npm run dev          # 开发服务器（见下）/ Dev server
npm run build        # 生产构建（含主页离线 CSS），输出到 ../static/analysis-lab/ 与 ../static/css/hud-home.bundle.css
```

## 构建产物 / Build output

- 目录：**`web/static/analysis-lab/`**（`index.html` + `assets/`）。
- 主页离线样式：**`web/static/css/hud-home.bundle.css`**（由同一 `npm run build` 一并生成）。
- 部署到开发板前需包含该目录（本机构建后提交，或由 CI `npm ci && npm run build` 生成）。

## 本地联调 / Local API

- `vite.config.ts` 中配置了 **`/api`** 与 **`/static`** → `http://127.0.0.1:8000` 的代理；需同时启动 OGScope 后端（默认 8000 端口）。
- 开发时访问地址形如：`http://127.0.0.1:5173/static/analysis-lab/`（以终端输出为准）。

## 同步开发板 / Sync to board

- 脚本：**`scripts/sync_dev_board.sh`**（先 `npm run build`，再 `rsync`；会同步 analysis-lab 与主页离线资源）。
- 环境变量：`OGSCOPE_DEV_HOST`、`OGSCOPE_DEV_PATH`（可选 `OGSCOPE_DEV_USER`）。

## CI

- **`.github/workflows/ci.yml`** 在 pytest 前执行 `web/spa` 下的 `npm ci` 与 `npm run build`。
