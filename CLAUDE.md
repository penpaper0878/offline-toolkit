# Repository guide

This repository holds two independent projects. Work on one at a time and do not mix their files.

| Folder | Project |
|---|---|
| `civillabpro/` | **CivilLabPro OS**: Indian civil engineering platform (FastAPI, PostgreSQL / SQLite, React). |
| everything else (`docs/`, `worker/`, `resources/`, `scripts/`) | **Offline Toolkit**: a personal offline desktop utility. See the root `README.md`. |

## Working on CivilLabPro OS

Before changing anything, read `civillabpro/docs/PROJECT_MEMORY.md` (status, next steps, decisions, conventions). Extend the existing architecture; do not replace it. After any piece of work, update that file's status, log and next steps, plus the backlog and the module note.

Rules that hold for every change:

* Build one module or element at a time, complete: domain engine, hand check, tests, API, screen, documents. No placeholder code.
* Engineering code is pure (`app/engineering/`, `app/modules/*/domain/`): no framework imports. A test enforces this.
* Every formula line cites its clause and every limit is a check with a verdict. Code interpretations go in `civillabpro/docs/CODE_REGISTER.md`.
* A new structural element is a domain module plus a registry entry. If it seems to need a new endpoint, table or screen, fix the registry pattern instead.
* Every engine has an independent hand check in `tests/handcheck/`.
* Every service filters by organisation; another tenant's record is "not found".

Checks to run before committing:

```bash
cd civillabpro/backend && . .venv/bin/activate && ruff check app tests alembic && pytest
cd civillabpro/frontend && npm run typecheck && npm test && npm run build
```

The root `.gitignore` ignores `fonts/` and `models/`; `civillabpro/.gitignore` re-includes them.
