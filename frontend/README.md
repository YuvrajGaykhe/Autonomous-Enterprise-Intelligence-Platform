# AI CEO HQ — frontend

This is the web frontend of the AI CEO system: a pixel-art agent office plus the CEO's inbox of
briefs, with a plain **Classic view** of the same data. It reads and writes only through the
existing FastAPI routes under `/api/v1`, and it changes no backend code.

The authority for this track is `CONTEXT/FRONTEND_SPECIFICATION.md`. This file covers the commands.

> **Status: F3 (the office).** `/` is the 3D office: every room, the agents at their desks with
> name tags and bulbs, SIGNALS_AGENT's board showing real signals, the staff directory, and the
> panels as drawers over the world. Classic view shows the same data as plain pages. Nothing in the
> office moves yet: walking, episodes and replays come in F4.

## Prerequisites

- **Node 24 LTS.** `.nvmrc` pins it, so run `nvm use` in this folder.
- **The backend's virtualenv.** Run `make install` in the repository root. The tooling runs
  `.venv/bin/alembic`, `.venv/bin/python` and `.venv/bin/uvicorn` from there.
- **A reachable PostgreSQL,** configured as the backend configures it (`DATABASE_URL`, or
  `POSTGRES_*` in the environment or the repository `.env`). The Docker stack's PostgreSQL works.
- **Google Chrome,** for the end-to-end tests. Playwright drives the installed Chrome
  (`channel: 'chrome'`) and downloads no browser.

## Commands

Run the `make` targets from the repository root, and the `npm` scripts from this folder.

| Make target             | npm script                   | What it does                                                                                 |
| ----------------------- | ---------------------------- | -------------------------------------------------------------------------------------------- |
| `make frontend-install` | `npm ci`                     | Install the dependencies exactly as locked                                                   |
| `make frontend-backend` | `npm run backend`            | Recreate `<database>_frontend` from clean and serve the working-tree API on `127.0.0.1:8010` |
| `make frontend-dev`     | `npm run dev`                | Vite on `127.0.0.1:5173`, proxying `/api` to `127.0.0.1:8010`                                |
| `make frontend-test`    | `npm run check`              | `tsc`, ESLint, Prettier, then every Vitest layer with coverage                               |
| `make frontend-build`   | `npm run build`              | Build for production, then the bundle report                                                 |
| `make frontend-e2e`     | `npm run e2e`                | Build, then the Playwright tests over `<database>_frontend_e2e`                              |
| —                       | `npm run perf`               | Build, then measure the office's frame time and draw calls for 30 s (the performance record) |
| —                       | `npm run record-fixtures`    | Re-record `tests/fixtures/` from the real API                                                |
| —                       | `npm run generate-api-types` | Regenerate `src/api/generated/openapi.d.ts` from the recorded `openapi.json`                 |

For local development, run `make frontend-backend` in one terminal and `make frontend-dev` in
another. Then open http://127.0.0.1:5173.

## The office

| Address              | Shows                                                |
| -------------------- | ---------------------------------------------------- |
| `/`                  | The office                                           |
| `/?agent=<agent-id>` | The office with that agent's panel open, as a drawer |
| `/?inbox=1`          | The office with the CEO inbox open                   |
| `/brief/<brief-id>`  | One brief, over the office                           |

The office also reads `pixel=0` (smooth toon instead of pixel art), `still=1` (render only when
something changes, for screenshots) and `perf=1` (the frame-time overlay). The HUD's **Office |
Classic** switch opens the same page in the other view (a Classic brief page becomes that brief
over the office), and the browser remembers the choice, as it remembers **Pixel | Smooth**. An open
panel is modal: close it to reach the HUD. When WebGL cannot start, or its context is lost twice,
the app opens the Classic twin of the address with a notice.

The view controls turn the camera in 90° steps (**Q** and **E**), zoom through three stops (**+**
and **−**), move it (the arrow keys, or a drag) and reset it (**0**). The **staff directory** lists
every agent with its state in words, and is the keyboard path to every panel. The world is a lazy
chunk: Classic view never downloads it.

## Classic view

| Address                      | Shows                                                                                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `/classic`                   | The API's health, and the agents with their roles                                                                                               |
| `/classic/inbox`             | The CEO inbox: one snapshot, one row per brief, executive-worthy first                                                                          |
| `/classic/briefs/<brief-id>` | Every section of one brief, the decision panel and the decision chain                                                                           |
| `/classic/agents/<agent-id>` | One agent's real output: a connector's source name, or `memory`, `linker`, `signals`, `sales`, `support`, `reconciler`, `brief-writer` or `ceo` |

Every page keeps `as_of` in its address (`as_of=2026-09-18` or `as_of=auto`). When a date has
more than one snapshot, `snapshot=<first 12 characters of the fingerprint>` chooses one. Every
panel has **Show the API call**, which lists the route, status, duration and `X-Request-ID` of each
request behind it.

## Isolated databases

The development database is never used (spec R-F-1). Each run of the tooling recreates its own
database from clean:

1. drop and create `<configured database>_frontend` (development) or `_frontend_e2e`
   (end-to-end tests and fixture recording);
2. `alembic upgrade head`;
3. `scripts/ingest_demo.py`;
4. serve `app.main:app`;
5. assess at `2026-09-18`.

These guarantees hold:

- **Refusals.** Any other database name is refused. A busy port is refused, never shared. An
  unreachable PostgreSQL exits with status 2, with no fallback.
- **No leaks.** Nothing prints a connection URL or a credential. Nothing touches Docker.
- **No overlap.** The end-to-end tests and the fixture recorder share `_frontend_e2e`, so never run
  them at the same time.

## Tests

| Layer      | Where              | Gate                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ---------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit       | `tests/unit/`      | `src/api/**` and `src/domain/**` at 100% of lines, branches, functions and statements                                                                                                                                                                                                                                                                                                                                                                                                           |
| Component  | `tests/component/` | Every surface in all four states (loading, empty, error, success); MSW answers from the recorded fixtures only                                                                                                                                                                                                                                                                                                                                                                                  |
| Contract   | `tests/contract/`  | Every fixture parses strictly. The briefs carry the specification's payload hashes and fingerprint. CUST-007's narrative equals `tests/golden/vs01_cust007_brief.txt` byte for byte. The generated types are current, and every Zod type is assignable to its OpenAPI type                                                                                                                                                                                                                      |
| Guards     | `tests/guards/`    | Covers no fake data, no score, notices, the Appendix A copy, and the secret-scanner naming rule                                                                                                                                                                                                                                                                                                                                                                                                 |
| Tooling    | `tests/tools/`     | Covers the isolation guard, the settings precedence, and exit status 2 without PostgreSQL                                                                                                                                                                                                                                                                                                                                                                                                       |
| End-to-end | `tests/e2e/`       | Runs against the real API over the isolated database. The office: its states, its board, panels opened from the directory, a tag and a click in the world, the brief overlay, the view switch, the WebGL fallback and a lost context. Classic: the inbox, a brief, approve, reject with supersede, both 409 families, unknown outcomes, Auto and an API that is down. Axe runs on every Classic page and every office panel. The office runs first, because Classic's scenario writes decisions |
| Visual     | `tests/e2e/`       | Screenshots on the clean database: Classic pages within 1% of pixels, the office at `?still=1` within 5% plus a check that the canvas is not blank. After a Chrome update, review the difference, then re-record the baselines with `npx playwright test --update-snapshots`                                                                                                                                                                                                                    |
| Bundle     | `npm run build`    | Initial JavaScript (all Classic view loads) ≤ 250 KB gzip; the lazy world chunk ≤ 900 KB gzip; world assets ≤ 5 MB                                                                                                                                                                                                                                                                                                                                                                              |

## Rules worth knowing

- **Fixtures.** They come only from the real API, via `npm run record-fixtures`, and are never edited
  by hand. `PROVENANCE.json` records where they came from. Nothing under `src/` may import from
  `tests/` or `tools/`. Every recorded brief lives in `briefs.json`, the one fixture file the
  repository secret scanner's allow-list names. `decision-flow.json` is recorded after writes, so
  MSW serves it only to tests that ask for it.
- **Naming.** No name the frontend chooses may contain `password`, `secret`, `token`, `api_key` or
  their variants. The repository secret scanner reads every tracked file. Design variables are
  called **theme variables**. The only exemption is a key the backend itself defines, listed in
  `tests/guards/guards.test.ts`.
- **Retries.** A POST is never retried automatically. After an unknown outcome, the app re-reads
  before it offers a retry.
- **No score.** Risk is shown only as its band word, with no numbers.
