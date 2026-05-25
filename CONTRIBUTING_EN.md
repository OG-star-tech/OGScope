# Contributing to OGScope

English | [中文](CONTRIBUTING.md)

Thank you for your interest in OGScope. We welcome contributions of all kinds.

## How to contribute

### Reporting bugs

1. Search [Issues](https://github.com/OG-star-tech/OGScope/issues) for duplicates.
2. If none, open a new issue with:
   - Clear description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment (OS, Python version, etc.)
   - Logs or screenshots if relevant

### Feature requests

1. Open an issue describing the use case.
2. Wait for maintainer feedback before large work.

### Code contributions

1. **Fork** the repository and clone your fork.
2. **Branch from `develop`**: `git checkout develop && git pull && git checkout -b feature/your-feature-name`
3. **Dev dependencies**:
   ```bash
   poetry install
   poetry run pre-commit install
   ```
4. **Implement** following project style; add tests; update docs.
5. **Validate**:
   ```bash
   poetry run pytest
   poetry run black ogscope tests
   poetry run ruff check ogscope tests
   poetry run mypy ogscope
   ```
   For API/architecture changes, also run through [Architecture Quick Checklist](docs/development/ARCHITECTURE_QUICK_CHECKLIST_EN.md).
6. **Commit** with bilingual messages when possible:
   - Title: `Chinese one-liner / English one-liner`
   - Body: a few paired bullets
   - Prefixes: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:`
7. **Push** and open a **Pull Request** using the template.

## Style

### Python

- **Black** formatting (88 columns)
- **Ruff** linting
- Type hints (**MyPy**)
- **PEP 8** baseline

### Documentation

- Markdown
- Full-width punctuation for Chinese text (except inside English fragments)
- Runnable code samples

### Tests

- New features need tests
- Aim for meaningful coverage on touched code
- Use markers: `unit` / `integration` / `hardware`

### API change policy (important)

- Stable contract: `"/api/core/v1/*"`.
- Developer APIs: `"/api/dev/*"` only—do not bring back `"/api/debug/*"`, `"/api/analysis/*"`, `"/api/system/*"`.
- `routes.py` is HTTP-only; logic belongs in `domain/*` and `core/application/*`.
- Update contract docs together with code:
  - `docs/contracts/core-rest-v1.md` / `docs/contracts/core-rest-v1_EN.md`
  - `docs/contracts/dev-rest-v1.md` / `docs/contracts/dev-rest-v1_EN.md`
  - `docs/contracts/core-compatibility-matrix.md` (inline bilingual)

## Git branch model

| Branch | Purpose |
|--------|---------|
| `main` | Stable release; merge from `develop` via PR only |
| `develop` | **Single integration branch**; default for daily work and board sync |
| `feature/*` | Features/refactors; branch from `develop`, delete after merge |
| `fix/*` | Small fixes; merge to `develop`; hotfix to `main` when urgent |

Flow: `feature/*` → PR → `develop` → periodic PR → `main`.

**Deprecated**: `dev` and `dev-latest` dual integration branches.

## Workflow

1. Pick or file an issue  
2. Develop and test locally  
3. Open a PR  
4. Review  
5. Merge into `develop` (and `main` for releases)

## Review expectations

- Correct behavior
- Style compliance
- Adequate tests
- Docs updated
- Breaking changes called out with migration notes

## Community

- Be respectful
- Give constructive feedback
- Help newcomers

## Getting help

- [Documentation index](docs/README_EN.md) | [中文](docs/README.md)
- [Development docs (中文)](docs/development/README.md) / [English](docs/development/README_EN.md)
- [GitHub Discussions](https://github.com/OG-star-tech/OGScope/discussions)

Thank you for contributing.
