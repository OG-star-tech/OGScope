# OGScope API Architecture

本文档描述当前生效的 API 分层与目录约定，供后续开发者快速对齐，避免把业务逻辑重新塞回路由层。

## 1) 目录分层（当前）

```text
ogscope/
├── web/
│   ├── app.py                    # FastAPI 应用入口、docs/docs/dev/docs/all
│   └── api/
│       ├── main.py               # 聚合路由（统一 prefix=/api）
│       ├── core/routes.py        # 标准契约：/api/core/v1/*
│       ├── debug/routes.py       # 开发调试：/api/dev/debug/*
│       ├── analysis/routes.py    # 开发分析：/api/dev/analysis/*
│       ├── system/routes.py      # 开发系统：/api/dev/system/*
│       ├── network/routes.py     # 网络域接口
│       ├── camera/routes.py      # 相机基础接口
│       └── ...                   # alignment/models 等
├── domain/
│   ├── camera/
│   ├── analysis/
│   ├── network/
│   ├── system/
│   └── shared/
├── core/
│   └── application/core_service.py # core/v1 契约编排
└── adapters/                     # 边界适配（懒加载/兼容桥接）
```

## 2) 设计原则（必须遵守）

- 路由层只做 HTTP 适配：参数解析、异常映射、`response_model` 序列化。
- 业务逻辑下沉到 `domain/*` 或 `core/application/*`，避免写在 `routes.py`。
- 标准对外能力固定在 `core/v1`，开发实验能力固定在 `dev/*`。
- 允许通过 `domain/shared` 复用，不要跨域直接复制粘贴逻辑。

## 3) API 分域与文档入口

- 标准契约（对外稳定）：`/api/core/v1/*`
- 开发者接口（内部调试）：`/api/dev/*`
  - 调试工具：`/api/dev/debug/*`
  - 分析实验：`/api/dev/analysis/*`
  - 系统状态：`/api/dev/system/*`

文档入口：

- `/docs`：仅标准契约
- `/docs/dev`：仅开发者接口
- `/docs/all`：全量接口

## 4) 典型请求流

```text
HTTP Request
  -> web/api/*/routes.py          (HTTP 适配)
  -> domain/*/services.py         (业务逻辑)
  -> adapters/hardware/algorithms (边界能力)
  -> route response model          (序列化)
```

## 5) 提交前防误改检查（强烈建议）

提交 API 相关改动前，请逐项确认：

1. 没有新增 `/api/debug/*`、`/api/analysis/*`、`/api/system/*` 旧前缀。
2. 开发接口统一在 `/api/dev/*` 下。
3. 标准接口统一在 `/api/core/v1/*` 下。
4. 新增业务逻辑没有写进 `routes.py`。
5. `/docs` 与 `/docs/dev` 展示分组符合预期。
6. 相关契约文档已同步更新：
   - `docs/contracts/core-rest-v1.md`
   - `docs/contracts/dev-rest-v1.md`

## 6) 快速验证命令

```bash
# 启动后检查 API 根
curl http://127.0.0.1:8000/api

# 核心契约示例
curl http://127.0.0.1:8000/api/core/v1/system/status

# 开发域示例
curl http://127.0.0.1:8000/api/dev/debug/camera/status
```
