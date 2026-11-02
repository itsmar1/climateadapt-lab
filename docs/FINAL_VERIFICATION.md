# Final Verification (P-final, 2026-11-01)

How to read this file: every numbered claim below is **CONFIRMED** — run in this
session with the real output quoted — unless it is explicitly labelled REPORTED or
UNVERIFIED. Full-suite context: Windows 11, PowerShell, repo-root `.venv`
(Python 3.11.17, uv-managed).

## 1. Backend test suite

Command (repo root):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

The direct interpreter is the same `.venv` interpreter `uv run pytest` would use;
`uv run` was avoided because its implicit sync would strip the vision tools, which
are installed outside `uv.lock` (see §8).

Result (verbatim final line):

```text
84 failed, 773 passed, 1 skipped, 80 warnings in 1113.59s (0:18:33)
```

Failures by file (sums to exactly 84):

| File | Failed |
|---|---|
| tests/test_api.py | 19 |
| tests/test_api_spi.py | 18 |
| tests/test_api_era5.py | 17 |
| tests/test_api_chirps.py | 16 |
| tests/test_api_scenarios.py | 12 |
| tests/test_api_demo.py | 2 |

Cause, identical for all 84 (sample, verbatim):

```text
E  PermissionError: [WinError 10013] Une tentative d'accès à un socket ...
```

The sandbox blocks `listen()`/`socketpair()`, which breaks Starlette `TestClient`
(KI-34, pre-existing and environmental). There are **zero assertion failures**:
all 35 vision tests and every non-API test pass. The suite is green except for
this sandbox block; the owner must still confirm green on an unsandboxed machine.

Vision subset (same session):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_vision_*.py -q -p no:cacheprovider
# 35 passed
```

## 2. Linter

```powershell
.\.venv\Scripts\ruff.exe check .
# All checks passed!
```

Exit 0. Ruff is part of the locked dev environment, so this equals
`uv run ruff check .` (re-run after the last P-final edit; see §12 report).

## 3. Frontend (React + Vite)

Toolchain: system Node is v16.13.1 (below Vite 8's requirement), so all three
gates ran under the git-ignored portable toolchain `node-tmp/`
(Node v26.13.0 + npm 11.20.0), repo root on `PATH`, working directory
`frontend/`.

| Gate | Result |
|---|---|
| `npm run lint` | exit 0, no eslint findings |
| `npm run test` | `Test Files 14 passed (14)`, `Tests 79 passed (79)`, 83.23 s |
| `npm run build` | `built in 1.34s`; `dist/` 3 files, 283,480 bytes total |

This resolves the 79-vs-72 Vitest discrepancy (KI history mentioned 72):
**79 is the current CONFIRMED count.**

## 4. Dependency licences (read from installed metadata, 2026-11-01)

Backend (`.venv`, `License-Expression`/`License` field, truncated to 60 chars
where the field holds full text):

| Package | Licence (installed metadata) |
|---|---|
| alembic, anyio, fastapi, pydantic, pytest, PyYAML, SQLAlchemy | MIT |
| cdsapi, qdrant-client, sentence-transformers, xarray | Apache-2.0 |
| click, Flask, h5py, httpx, pandas, pypdf, scikit-learn, starlette, uvicorn | BSD-3-Clause (rasterio: BSD) |
| mlflow | Apache-2.0 licence header in metadata |
| numpy | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| scipy | BSD licence header in metadata |
| torch | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause ... |
| tqdm | MPL-2.0 AND MIT (dual) |
| matplotlib | PSF-style licence text in metadata |
| Jinja2 | not declared in installed metadata |

Frontend (`frontend/node_modules/*/package.json` `license` field):

| Package | Licence |
|---|---|
| react, react-dom, vite, eslint, vitest, openapi-fetch, openapi-typescript | MIT |
| typescript | Apache-2.0 |

Notes:

- No GPL/AGPL dependency. Closest cases: tqdm is weak-copyleft MPL-2.0 dual
  with MIT (file level); matplotlib wheels bundle FreeType under
  FTL-or-GPL-2.0-or-later at the user's choice.
- fiona/shapely/geopandas are not installed in `.venv` (not dependencies).
- Jinja2's upstream licence was not re-checked; only the metadata gap is
  recorded here.

## 5. Docker + CI

```powershell
docker compose config --quiet   # COMPOSE_CONFIG_EXIT:0
```

Compose file parses (fresh CONFIRMED 2026-11-01; a benign
`Error loading config file ... Access is denied` warning about the user-level
docker config also prints under the sandbox).

- Docker client 29.8.2 is present, but the **daemon is down** (verbatim):
  `failed to connect to the docker API at npipe:////./pipe/docker_engine ...
  The system cannot find the file specified.` Image build and container start
  are therefore still UNVERIFIED — owner action unchanged (KI-30).
- CI workflow (`.github/workflows/ci.yml`) is authored and tracked (YAML
  parses: jobs `backend`, `frontend`) but has never executed on GitHub —
  UNVERIFIED.

## 6. Security review (P-final)

Own checks, all CONFIRMED 2026-11-01:

- Tracked `*.env*` files: only `.env.example` + `frontend/.env.example`.
  Key values are empty (`CLIMATEADAPT_BASETEN_API_KEY=`, `BASETEN_API_KEY=`);
  `.env.docker.example` (600 B, placeholder-only, key line commented) is now
  un-ignored by `.gitignore` and ready for the owner to stage — not yet staged.
- `.env` has never appeared in git history (`git log --all -- .env` is empty).
- `remote_run.json` was committed once (2e589c9, 469 lines) and is now removed
  from the index (file kept in the working tree). Its committed blob
  (17,771 chars) and one committed `data/agent_runs/*.json` blob
  (24,137 chars) contain zero lines matching key/token/secret/path patterns.
- Tracked-code greps: no private-key blocks; no real-looking key prefixes
  (only `"[REDACTED]"` test fixtures and the prose false positive
  "task-aligned"); no hardcoded user paths in `src/`, `scripts/`, `tests/`.
- `.gitignore` covers `.env`, `data/` (blanket), `corpus/**/*.pdf`,
  `corpus/**/*.txt`, `corpus/raw/`, `node-tmp/`, `remote_run.json`,
  `pytest-of-dell/`; verified with `git check-ignore`.
- Working tree is clean of run debris: `git status` shows only intended
  modifications/deletions plus the two new P-final docs; zero untracked files
  outside ignored paths.
- Local `.env` bodies were never opened (variable names + empty values only).

Could NOT be fully checked: the scan is pattern-based over tracked files plus
targeted blob/history probes — a full `git log -p` dump was not reviewed, so a
secret in a novel format could in principle be missed. No live-service state
(CDS account, Baseten keys, `%USERPROFILE%\.cdsapirc`) was touched at all.

## 7. Streamlit disposition

`git grep -i -n streamlit` returns 15 lines (CONFIRMED 2026-11-01):

| Location | Lines | Nature |
|---|---|---|
| AGENTS.md | 1 | standing prohibition (rule, not obsolete) |
| docs/handoff/AUDIT_REPORT.md | 4 | frozen 2026-10-30 audit ledger |
| docs/handoff/KNOWN_ISSUES.md | 4 | KI-27 decision history + this disposition |
| docs/handoff/MUSE_CODE_TASK_PROMPTS.md | 4 | frozen prompt texts incl. the P-final prompt itself |
| docs/handoff/PROJECT_CONTEXT.md | 2 | overridden-decisions log |

Zero in code/tests/scripts/frontend. Nothing was deleted: the audit report is
dated evidence and must not be rewritten; the rest is intentional rule +
history (KI-27).

## 8. Deliberately not run

- `uv sync --extra dev`: would strip the vision tools (MLflow, h5py,
  scikit-learn), which are installed in `.venv` outside `uv.lock` because the
  sandbox blocks uv's network access. Owner action: add a `vision` extra and
  run `uv lock` on a networked machine; use `uv run --no-sync` meanwhile.
- A second full suite after the P-final doc edits: P-final touched no
  `src/`/`tests/`/`scripts/`/`frontend/src` code, so the §1 run stands.

## 9. What remains UNVERIFIED (owner actions)

1. Full backend suite green on an unsandboxed machine (84 API tests blocked
   here by WinError 10013).
2. Docker image build + container start (`docker compose up --build`; daemon
   was down here).
3. CI's first GitHub execution.
4. CDS retry behavior under a real failure (deliberately never attempted).
5. Live Baseten behavior beyond the small 2026-10-30 smoke runs; numeric
   rate/context limits and credit balance.
6. Corpus licence verification on landing pages (KI-23); 3 missing manual PDFs
   (KI-18); RAG label review (KI-19).
7. Full-data (82k-row) vision training — the evaluated run used a seeded 20k
   subset; the same command reproduces it (see `docs/VISION_BASELINE.md`).

## 10. P20 addendum (2026-11-02; §1–§9 above are frozen P-final evidence)

Frontend-only change; backend untouched (§1 counts stand). New frontend
dependencies (installed-manifest `license` fields, CONFIRMED):

| Package | Licence |
|---|---|
| leaflet 1.9.4 | BSD-2-Clause |
| react-leaflet 5.0.0, @react-leaflet/core 3.0.0 | **Hippocratic-2.1** (ethical-source, not OSI-approved — see KI-36) |
| @types/leaflet 1.9.22 | MIT |

§4's "No GPL/AGPL dependency" still holds; its implied
permissive-everywhere claim no longer does (README carries the exception).
Bundle impact: `vite build` JS 440.58 kB (gzip 132.44 kB) vs P-final
`dist/` 283,480 bytes total. Gates: `eslint .` exit 0, 96/96 Vitest
(16 files, 77.65 s), `tsc` clean, 7/7 Playwright (1.4 min, system
Chrome). Map tiles are key-free OSM standard tiles with on-map attribution
per the Tile Usage Policy (read 2026-11-02); no geocoding; no CSP exists to
update. Screenshots in `docs/screenshots/` show blank tile backgrounds
because `tile.openstreetmap.org` times out in the sandbox — re-capture on a
networked machine (command in README).

## 11. P21 addendum (2026-11-02; submission-readiness re-verification)

Docs-only change (no `src/`/`tests/`/`scripts/`/`frontend/src` edits, so the
P20 frontend gates stand on identical code: 96/96 Vitest, 7/7 Playwright,
`tsc`/eslint/build clean).

- Backend suite re-run fresh: `84 failed, 792 passed, 1 skipped, 82 warnings
  in 1710.73s (0:28:30)` — same 84 sandbox socket-blocked API tests
  (19/16/2/17/12/18 per file, all `PermissionError: [WinError 10013]`),
  zero assertion failures. Ran as `uv run --no-sync pytest -q` with
  `UV_CACHE_DIR` redirected to git-ignored `node-tmp/uv-cache` (sandbox
  blocks the global uv lock; `--no-sync` per README, so vision tools outside
  `uv.lock` are not stripped). Owner must still run the suite once
  unsandboxed and expect fully green.
- `uv run ruff check .` (same env): **All checks passed!**, exit 0.
- Secret scan: no private-key blocks anywhere; tracked `*.env*` files are
  `.env.example` + `.env.docker.example` only, both with empty key values;
  live keys exist solely in git-ignored `.env` / `.env.docker` (contents not
  reproduced anywhere). No `.pdf`, `.env`, sqlite, `data/`, `corpus/raw/`,
  or run-debris paths are tracked (`git ls-files` checked).
- Docker/CI status: backend image + `/health` REPORTED OK by the owner
  (post-`libexpat1`/`libgomp1`, commit `670d74c` in tree); frontend image
  build, compose serving, and CI's first GitHub run remain UNVERIFIED.
- `.env.docker.example` (placeholder-only, key line empty) is now tracked —
  the §6 pre-share item asking to stage it is done.
