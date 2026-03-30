# 星图解算实验室前端 / Analysis Lab UI

## 用途 / Purpose

- 技术栈：**Vite 5 + React 18 + TypeScript + Tailwind CSS**。
- 入口页面由 FastAPI 在 **`GET /debug/analysis`** 提供：若存在 `web/static/analysis-lab/index.html` 则返回 SPA，否则回退旧版 Jinja 模板。
- 静态资源由 FastAPI 挂载 **`/static`**，本应用 `base` 为 **`/static/analysis-lab/`**。

## 常用命令 / Commands

```bash
cd web/analysis-ui
npm install          # 安装依赖 / Install deps
npm run dev          # 开发服务器（见下）/ Dev server
npm run build        # 生产构建，输出到 ../static/analysis-lab/
```

## 构建产物 / Build output

- 目录：**`web/static/analysis-lab/`**（`index.html` + `assets/`）。
- 部署到开发板前需包含该目录（本机构建后提交，或由 CI `npm ci && npm run build` 生成）。

## 本地联调 / Local API

- `vite.config.ts` 中配置了 **`/api` → `http://127.0.0.1:8000`** 的代理；需同时启动 OGScope 后端（默认 8000 端口）。
- 开发时访问地址形如：`http://127.0.0.1:5173/static/analysis-lab/`（以终端输出为准）。

## 同步开发板 / Sync to board

- 脚本：**`scripts/sync_dev_board.sh`**（先 `npm run build`，再 `rsync`）。
- 环境变量：`OGSCOPE_DEV_HOST`、`OGSCOPE_DEV_PATH`（可选 `OGSCOPE_DEV_USER`）。

## CI

- **`.github/workflows/ci.yml`** 在 pytest 前执行 `web/analysis-ui` 下的 `npm ci` 与 `npm run build`。
