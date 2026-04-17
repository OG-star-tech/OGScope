# OGScope Core Contract Compatibility Matrix

| OGScope | Contract Path |
|---|---|
| 0.1.x | `/api/core/v1/*` |

## Backward Compatibility Rule

- Keep existing response keys stable.
- New keys must be optional/additive.
- Breaking changes must publish a new path version (for example `/v2/`).
