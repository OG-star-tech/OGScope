# OGScope Script Authoring and Invocation Standard

English | [中文](SCRIPT_STANDARDS.md)

This standard keeps `scripts/` and future `deploy/` helpers consistent, reducing maintenance cost and operational risk for external integrations.

## 1. Scope and boundaries

- OGScope scripts manage only OGScope installation, updates, removal, diagnostics, and repair.
- Do not embed deployment logic for a specific downstream product.
- External integrators own combined-stack orchestration; OGScope exposes stable script entry points and health checks.

## 2. Unified command model

Recommended future entry point:

```bash
./scripts/stackctl.sh <command> [options]
```

Standard commands:

- `install`: first installation, including minimal and extended modes
- `update`: incremental update
- `uninstall`: removal
- `doctor`: read-only diagnostics
- `repair`: allowlisted repairs
- `status`: current runtime and version summary

## 3. Arguments

Scripts should support these common arguments where applicable:

- `--yes`: non-interactive confirmation for CI and automation
- `--dry-run`: inspect without writing files or restarting services
- `--json`: machine-readable output
- `--verbose`: detailed progress logs
- `--strict`: treat warnings as failures

Invalid arguments must return the argument-error exit code. Destructive actions require explicit confirmation unless `--yes` is supplied.

## 4. Exit codes

- `0`: success
- `2`: invalid arguments
- `3`: preconditions not met, such as dependencies, permissions, or environment
- `4`: execution failed
- `5`: partial success with incomplete actions

## 5. Idempotency and safety

- Scripts must be idempotent and must not damage an already working installation when rerun.
- Changes to `systemd`, `/etc/*`, or networking must identify the target, support a dry run, and provide a recovery path on failure.
- Never print passwords, tokens, private keys, or other secrets to logs.

## 6. Output and logging

- Human-readable critical messages should be bilingual.
- JSON output must include at least `success`, `code`, `summary`, and `checks` or `actions`.
- Use stable `INFO`, `WARN`, and `ERROR` prefixes for important steps.

## 7. Files and naming

- Use `kebab-case` script names.
- Put entry scripts in `scripts/` and reusable functions in `scripts/lib/`.
- Prefer shared functions over duplicated system operations.

## 8. Privilege handling

- Check privileges when the top-level script starts; do not elevate unexpectedly in the middle of a workflow.
- Group root operations and explain them before execution.
- Handle `sudo -n` failures with a clear message and a manual recovery command.

## 9. External integration

OGScope remains a core capability provider. It guarantees:

- stable install, update, and uninstall entry points;
- diagnosable health and configuration state;
- the `core/v1` and [subordinate mode](../contracts/subordinate-mode_EN.md) contracts.

Combined deployment and product orchestration belong to the external integrator.

## 10. Minimum checks before committing script changes

- Run `bash -n` for every changed shell script.
- Run the target script with `--help` or an equivalent argument check.
- When runtime paths change, validate:

```bash
systemctl status ogscope
curl -s http://127.0.0.1:8000/health
```
