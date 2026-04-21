# Dev REST Domain v1

English | [中文](dev-rest-v1.md)

This document describes OGScope **developer-domain** APIs (internal). They are **not** part of the customer-facing stable contract.

## Surface split

- Stable contract (customer-visible): `/api/core/v1/*`
- Developer domain (internal debug and experiments): `/api/dev/*`

## Main path groups

- Debug tools: `/api/dev/debug/*`
  - Camera debug, presets, recordings, systemd logs
- Analysis lab: `/api/dev/analysis/*`
  - Asset pool, experiment records, offline/online solving and parameter trials

## Documentation entrypoints

- Standard OpenAPI: `/docs` (default)
- Developer OpenAPI: `/docs/dev`
- Full OpenAPI: `/docs/all`

## Compatibility policy

- The developer domain may iterate and refactor; stability across major revisions is not guaranteed.
- Customer integrations must rely only on `core/v1` and its versioning policy.
