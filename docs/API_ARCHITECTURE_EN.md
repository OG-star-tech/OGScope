# OGScope API Architecture

English | [中文](API_ARCHITECTURE.md)

This document describes the **current** API layering and directory layout so contributors keep business logic out of route handlers.

For system-level architecture (core boundary, user vs developer surfaces, operations cross-cutting), see  
`docs/architecture/OGSCOPE_SYSTEM_ARCHITECTURE_BILINGUAL.md`.

## FastAPI app entry and new endpoints

- **Application entry**: `ogscope/web/app.py` (Uvicorn, `openapi_tags`, custom ReDoc, `/docs` / `/docs/dev` / `/docs/all`).
- **Router aggregation**: `ogscope/web/api/main.py` (`include_router`, `tags`).

### When adding endpoints

1. Keep business logic in `domain/*` or `core/application/*`; `routes.py` handles HTTP adaptation only.
2. Stable surface: `/api/core/v1/*`; developer surface: `/api/dev/*`.
3. Update contract docs: `docs/contracts/core-rest-v1.md` / `core-rest-v1_EN.md`, `dev-rest-v1.md` / `dev-rest-v1_EN.md`.
4. When adding debug-console fields, camera telemetry, or analysis-result `overlay_ext`, also update `docs/DEBUG_CONSOLE.md` / `DEBUG_CONSOLE_EN.md`.

Board deployment overview: [Development Guide](development/README_EN.md) | [中文](development/README.md). Pre-submit checks: section 5 below.

## 1) Directory layout (current)

```text
ogscope/
├── web/
│   ├── app.py                    # FastAPI entry, docs/docs/dev/docs/all
│   └── api/
│       ├── main.py               # Router aggregation (prefix=/api)
│       ├── core/routes.py        # Stable contract: /api/core/v1/*
│       ├── debug/routes.py       # Dev debug: /api/dev/debug/*
│       ├── analysis/routes.py    # Dev analysis: /api/dev/analysis/*
│       ├── system/routes.py      # Dev system: /api/dev/system/*
│       ├── network/routes.py     # Network APIs
│       ├── camera/routes.py      # Camera base APIs
│       └── ...                   # alignment, models, etc.
├── domain/
│   ├── camera/
│   ├── analysis/
│   ├── network/
│   ├── system/
│   └── shared/
├── core/
│   └── application/core_service.py # core/v1 orchestration
└── adapters/                     # Boundary adapters (lazy / compat)
```

## 2) Design rules (mandatory)

- Routes only do HTTP adaptation: parse args, map exceptions, `response_model` serialization.
- Business logic belongs in `domain/*` or `core/application/*`, not in `routes.py`.
- Stable external surface is `core/v1`; experimental tooling is `dev/*`.
- Reuse via `domain/shared`; do not copy-paste across domains.

## 3) API surfaces and doc entrypoints

- Stable contract: `/api/core/v1/*`
- Developer APIs: `/api/dev/*`
  - Debug: `/api/dev/debug/*`
  - Analysis lab: `/api/dev/analysis/*`
  - System status: `/api/dev/system/*`

Documentation:

- `/docs` — contract only
- `/docs/dev` — developer APIs only
- `/docs/all` — everything

## 4) Typical request flow

```text
HTTP Request
  -> web/api/*/routes.py          (HTTP adaptation)
  -> domain/*/services.py         (business logic)
  -> adapters/hardware/algorithms (boundary capabilities)
  -> route response model          (serialization)
```

## 5) Pre-submit checklist (strongly recommended)

Before API changes, confirm:

1. No new `/api/debug/*`, `/api/analysis/*`, `/api/system/*` legacy prefixes.
2. Developer APIs live under `/api/dev/*`.
3. Stable APIs live under `/api/core/v1/*`.
4. New logic is not stuffed into `routes.py`.
5. `/docs` and `/docs/dev` grouping looks correct.
6. Contract docs updated:
   - `docs/contracts/core-rest-v1.md` / `docs/contracts/core-rest-v1_EN.md`
   - `docs/contracts/dev-rest-v1.md` / `docs/contracts/dev-rest-v1_EN.md`
   - `docs/contracts/core-compatibility-matrix.md` (when versioning/path policy changes)
7. Debug-console fields, camera-pipeline telemetry, and analysis extension fields are reflected in debug documentation.

## 6) Quick verification commands

```bash
curl http://127.0.0.1:8000/api
curl http://127.0.0.1:8000/api/core/v1/system/status
curl http://127.0.0.1:8000/api/dev/debug/camera/status
```
