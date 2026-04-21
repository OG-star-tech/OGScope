# Architecture Quick Checklist

English | [中文](ARCHITECTURE_QUICK_CHECKLIST.md)

Before submitting API or architecture changes, quickly verify the items below (~2 minutes).

## 1) Routing and surfaces

- [ ] Stable contract uses only `"/api/core/v1/*"`.
- [ ] Developer APIs use only `"/api/dev/*"`.
- [ ] Legacy prefixes not reintroduced: `"/api/debug/*"`, `"/api/analysis/*"`, `"/api/system/*"`.
- [ ] `/docs`, `/docs/dev`, `/docs/all` scopes match this change.

## 2) Layering

- [ ] `routes.py` is HTTP-only (parse, map exceptions, serialize responses).
- [ ] Business logic lives in `domain/*` or `core/application/*`, not in routes.
- [ ] Cross-domain reuse goes through `domain/shared/*` without copy-paste.
- [ ] No new `domain -> web.api` reverse dependency.

## 3) Documentation sync

- [ ] Contract docs updated:
  - `docs/contracts/core-rest-v1.md` / `docs/contracts/core-rest-v1_EN.md`
  - `docs/contracts/dev-rest-v1.md` / `docs/contracts/dev-rest-v1_EN.md`
  - `docs/contracts/core-compatibility-matrix.md` (inline bilingual)
- [ ] If tags/grouping changed, also check:
  - `ogscope/web/api/main.py`
  - `ogscope/web/app.py`
- [ ] If layout or dev conventions changed, also update:
  - `docs/API_ARCHITECTURE.md` / `docs/API_ARCHITECTURE_EN.md`
  - `docs/development/README.md`
  - `docs/development/README_EN.md`
  - `CONTRIBUTING.md` / `CONTRIBUTING_EN.md`

## 4) Basic verification

- [ ] Unit tests: `poetry run pytest tests/unit -q`
- [ ] Frontend build (if touched): `cd web/spa && npm run build`
- [ ] API smoke:
  - `curl http://127.0.0.1:8000/api`
  - `curl http://127.0.0.1:8000/api/core/v1/system/status`
  - `curl http://127.0.0.1:8000/api/dev/debug/camera/status`

## 5) Commit hygiene

- [ ] Commit message is bilingual (Chinese title / English title).
- [ ] Content matches the title; no unrelated bulk changes in the same commit.
- [ ] Breaking changes: scope and migration notes are explicit.
