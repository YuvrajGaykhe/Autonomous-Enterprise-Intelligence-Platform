# AI CEO HQ — Frontend Specification

**Version:** v1, 2026-09-28
**Track:** F, phases F0–F7
**Baseline:** `733b19b`
**High-level description:** `CONTEXT/FRONTEND_OFFICE_PLAN.md`

> **Status of this document.** This document **is the frontend track's authorisation**, in the way that §0.4–§0.8
> of `VS01_IMPLEMENTATION_PLAN.md` authorised M5–M9. It covers:
> - decisions D-F-1…D-F-19 (§1);
> - the review items R-F-1…R-F-8 (§18);
> - nothing wider.
>
> **It governs F1–F7's implementation.** The plan remains the high-level description and the rationale. Where the
> plan is coarser, or differs, this document governs. §17 lists the plan's statements that were corrected while
> this document was written.
>
> - **2026-09-28.** The owner approved the plan. The owner directed every recommendation made in the questioning
>   round, and every open item O-1…O-7 (now D-F-13…D-F-19).
> - **2026-09-28.** Writing this document against the committed code, and against the local stack observed through
>   read-only GETs, exposed eight material details. They were put to the owner as R-F-1…R-F-8, each with a
>   proposal. **The owner accepted all eight the same day. They are now DIRECTED** (§18).
>
> **F1 has not started.** It begins only on the owner's instruction. Before that, this document and the plan are
> committed together as F0 (`F0: finalize frontend specification`).
>
> **The backend stays frozen.** The anchors verified at `733b19b` on 2026-09-28 are listed in §3. **The frontend
> track changes no production code, configuration, migration, data file, backend test, backend script or Docker
> file** (D-F-11). The only exception is the named repository-level files of §4.

**Classification**, as in §0.7 and §0.8:

| Label | Meaning |
|---|---|
| **DIRECTED** | Decided by the owner on 2026-09-28 |
| **DERIVED** | Forced by frozen code or by a committed convention, which is named |
| **OBSERVED** | Measured on the repository at `733b19b`, or on the local stack through read-only GETs, on 2026-09-28 |
| **PROPOSED** | A name, a constant, a layout or a mechanism that the directed decisions need but do not fix. It stands unless replaced, and replacing it reopens nothing |

The eight material items were put to the owner as R-F-1…R-F-8 and are now DIRECTED (§18). Every PROPOSED item that
remains is a name, a constant, a format, a layout detail or a tooling mechanism.

---

## Contents

1. [Decisions D-F-1…D-F-19](#1-decisions-d-f-1d-f-19)
2. [Scope](#2-scope)
3. [Baseline and anchors](#3-baseline-and-anchors)
4. [Allowed and frozen paths](#4-allowed-and-frozen-paths)
5. [Toolchain and dependencies](#5-toolchain-and-dependencies)
6. [API consumption contract](#6-api-consumption-contract)
7. [Domain rules](#7-domain-rules)
8. [Product surfaces](#8-product-surfaces)
9. [The office](#9-the-office)
10. [Accessibility](#10-accessibility)
11. [Security, privacy and honesty](#11-security-privacy-and-honesty)
12. [Tests, fixtures and isolation](#12-tests-fixtures-and-isolation)
13. [Baseline, regression and the gate](#13-baseline-regression-and-the-gate)
14. [Phases, gates and commits](#14-phases-gates-and-commits)
15. [Acceptance criteria](#15-acceptance-criteria)
16. [Known limitations](#16-known-limitations)
17. [Corrections to the plan](#17-corrections-to-the-plan)
18. [Review items R-F-1…R-F-8](#18-review-items-r-f-1r-f-8)
19. [Phase records](#19-phase-records)
20. [Appendix A: fixed copy](#appendix-a-fixed-copy)

---

## 1. Decisions D-F-1…D-F-19

All are **DIRECTED**, 2026-09-28. D-F-1…D-F-12 came from the questioning round; D-F-13…D-F-19 are the plan's open
items O-1…O-7, each resolved as recommended.

| ID | Decision | Where it is applied |
|---|---|---|
| D-F-1 | Agents stand for real VS-01 components. Ambient idle motion is allowed. A **working** pose plays only while a real request is in flight, or during a labelled replay of recorded results. Every value in a panel or an in-world label comes from an API response | §9.4–§9.6, AC-F-1, AC-F-2 |
| D-F-2 | Risk is shown only as the ordinal band (NONE, WATCH, ELEVATED, CRITICAL), with the rules and signals behind it. There is no numeric score and no percentage anywhere | §7.1, AC-F-3 |
| D-F-3 | The CEO inbox holds every brief in the API's ranking order, with executive-worthy briefs pinned first. Inbox items are called **briefs**, never "tickets" | §7.2, AC-F-4 |
| D-F-4 | Future slices are locked, labelled rooms. A new agent joins through a "NEW HIRE!" ceremony | §9.1, §9.13 |
| D-F-5 | The office is real 3D, rendered as pixel art through three.js's pixel pass. A switch turns pixelation off for a smooth-toon look | §9.8 |
| D-F-6 | The office is the home screen, and clicks open data panels. A **Classic view** shows the same data as plain pages | §8, AC-F-7 |
| D-F-7 | The CEO approves or rejects a whole brief, with a note. A later decision can supersede an earlier one | §7.5, §8.5 |
| D-F-8 | The hosted site is writable against a disposable demo database, with a documented reset | §14 F5 |
| D-F-9 | There is no fixed deadline. Phases advance by gates | §14 |
| D-F-10 | The track follows the M-milestone discipline with gates sized for UI work. There are no mutation audits for UI code | §13, §14 |
| D-F-11 | No backend code changes in F0–F6. Only the repository-level files of §4 are added or edited | §4, AC-F-9 |
| D-F-12 | The look follows the owner's reference image: a pixel-art office in a 3/4 top-down view, `SNAKE_CASE` name tags, glowing cyan hand-off arrows, "?" bubbles, a glow on active agents, a memory robot and a "NEW HIRE!" moment | §9.3 |
| D-F-13 | The product name is **AI CEO HQ** | Appendix A |
| D-F-14 | "Run assessment" defaults to the explicit date `2026-09-18`. An **Auto (latest ticket)** option sends `as_of: null` | §6.6, §8.2 |
| D-F-15 | Makefile targets, `.gitignore` lines and one README section are authorised exactly as §4 lists them | §4 |
| D-F-16 | `.dockerignore` gains the line `frontend/node_modules` at F5. This is a Docker change, approved | §4 |
| D-F-17 | Vercel runs the API on Python 3.12 if the full backend suite is clean in a fresh 3.12 venv. Otherwise it runs as a container service built from the existing Dockerfile | §14 F5, R-F-8 |
| D-F-18 | A pixel font is used for in-world tags only. Panels use a clean sans, and ids and hashes use a monospace font | §9.3 |
| D-F-19 | Sound is off by default. When on, it plays soft keyboard clicks and a stamp sound | §9.12 |

---

## 2. Scope

### Track IN-SCOPE

1. The `frontend/` application: the office, the panels, Classic view and the HUD.
2. Its tests, its tooling, and the lifecycle tooling for its own isolated databases (R-F-1).
3. The repository-level files of §4:
   - Makefile targets;
   - `.gitignore` lines;
   - one README section;
   - one `.dockerignore` line;
   - `vercel.json`.
4. `frontend/THIRD_PARTY_NOTICES.md`, and the files and assets it lists (MIT-adapted code, CC0 models).
5. Hosting on Vercel with Neon Postgres (F5), each outward action separately approved (§14).

### Track OUT-OF-SCOPE

- Any change under the frozen paths of §4, including:
  - every file in `app/`, `config/`, `migrations/`, `data/`, `tests/` and `scripts/`;
  - the Docker files;
  - `pyproject.toml`;
  - `.env.example`.
- A new API route, a CORS policy, authentication, or an event stream. Each would need its own backend milestone
  (F7).
- A numeric score, per-action approval, language-model features, multiplayer, 2D sprite art or Next.js (plan §14).
- Reading, writing, migrating or seeding the **development** database (R-F-1).
- Any agent for VS-02 onward. Those appear only as locked rooms.
- Any push, deployment, account creation or external resource without the owner's explicit approval for that
  action.

---

## 3. Baseline and anchors

All values below are **OBSERVED** at `733b19b` on 2026-09-28.

| Anchor | Value |
|---|---|
| `HEAD` | `733b19b5a0b79a6fbd1ac96cc819ceff419564c7`, authored by YuvrajGaykhe |
| `origin/main` | `2b6deb3a14d49a5566de1fab2b3fa0c085dab056`, so local `main` is 9 commits ahead and unpushed |
| Golden brief | `tests/golden/vs01_cust007_brief.txt`, sha256 `87d1398661b0c30037ddc33e9acfd36db321ac9d0a36e04eadc3be9039ea9dce` |
| Migration head | exactly one, `070e4968a497` |
| `TEMPLATE_VERSION` | `"1"` |
| Pinned Layer 1 fingerprint (`csv_demo`) | `1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00` |
| Briefs at `as_of 2026-09-18` on the clean dataset | exactly 3, with payload hashes: <br>CUST-007 (CRITICAL) `e93c29cfb6094284d7ea6fe84bf966ad0b40995fccdc4e2a671b502a7f16c946` <br>CUST-025 (WATCH) `08c99ced40996611c8f7bb4ea48e918fabe0e9cd68390122d0f86faa50738770` <br>CUST-036 (WATCH) `a6240ac1edd4890724568adc7a8bd8f99add305638b9dcb179429ae67d06b637` <br>The other 47 customers are NONE |
| Tracked files | 368 |
| Strategy document | `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md` is modified and never staged; its diff sha256 begins `94e4e5b2f65616f6` |
| Backend suite, as the README quotes it | 6771 tests: unit 5287, contract 185, integration 1214, e2e 85. `app/` coverage 100% over 7456 statements. ruff 69, mypy 9, secret scan 0. **Re-measured at F1's baseline step** |

**Local toolchain (OBSERVED):**
- Node `v23.10.0`, npm `11.18.0`, no pnpm (R-F-5);
- system `python3` 3.13.2;
- the repository `.venv` is Python 3.11.5 (per the M9 record).

**Local stack (OBSERVED through read-only GETs only):**
- `ai-ceo-api`, `ai-ceo-mock-source` and `ai-ceo-postgres` are up and healthy.
- The API image was created on 2026-09-27 and serves `/api/v1/risk/*`.
- **The development database is not the clean dataset.** `GET /entities/customers` reports 52 customers, not 50.
  Its newest assessments are at `as_of 2026-09-27`, under fingerprint `3305b0d9…`, not the pinned `1d891b0b…`.
  This forces R-F-1.

---

## 4. Allowed and frozen paths

| Path | The track may | Phase | Scope of the change |
|---|---|---|---|
| `CONTEXT/FRONTEND_SPECIFICATION.md` | create, then append | F0; each phase | F0 creates it. Each phase appends only its record to §19, and its §18 status line if one changes |
| `CONTEXT/FRONTEND_OFFICE_PLAN.md` | create | F0 | Its status header and the corrections of §17. **Frozen after F0** |
| `frontend/**` | create, edit | F1–F7 | As §5–§12 specify |
| `Makefile` | edit | F1, F5 | New targets only (§4.1). No existing target, recipe or help line is changed |
| `.gitignore` | append | F1 | Exactly: `frontend/node_modules/`, `frontend/dist/`, `frontend/coverage/`, `frontend/test-results/`, `frontend/playwright-report/`, `frontend/.vercel/` |
| `README.md` | edit | F5 | One new section, `## Frontend and demo`, placed after the VS-01 section. The rules of R-F-4 apply. No existing line changes |
| `.dockerignore` | append | F5 | The single line `frontend/node_modules` (D-F-16) |
| `vercel.json` | create | F5 | Vercel Services and rewrites (§14 F5) |
| `app/`, `config/`, `migrations/`, `alembic.ini`, `data/` | **frozen** | — | `733b19b` |
| `tests/` (the whole backend suite, including `tests/golden/` and `tests/fixtures/`) | **frozen** | — | `733b19b`. **No backend test evolution is authorised.** A phase whose work would need one stops and asks |
| `scripts/` | **frozen** | — | `733b19b`. No new script: the G2 boundary scans `scripts/` (DERIVED, `tests/unit/test_g2_security_boundary.py`) |
| `Dockerfile`, `docker-compose.yml`, `docker/`, `.env.example`, `pyproject.toml` | **frozen** | — | `733b19b` |
| `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md` | **never touched and never staged** | — | the owner's uncommitted change |
| Every other `CONTEXT/` file | **frozen** | — | `733b19b` |

### 4.1 Makefile targets

The names are PROPOSED. The shape is DERIVED from `tests/unit/test_i1_verify_units.py` and
`tests/unit/test_i2_readme.py`:
- every new target is added to `.PHONY`;
- every new target has a recipe;
- every new target is listed by `make help` as `make <target>`;
- no recipe line starts with a bare `python`, `python3`, `pytest`, `alembic`, `ruff`, `mypy`, `black` or `pip`.
  Backend tools run as `.venv/bin/<tool>`.

| Target | Phase | Recipe (PROPOSED) |
|---|---|---|
| `frontend-install` | F1 | `npm --prefix frontend ci` |
| `frontend-backend` | F1 | Recreates the isolated `<POSTGRES_DB>_frontend` database from clean and serves the working-tree API on `127.0.0.1:8010` (R-F-1): `npm --prefix frontend run backend` |
| `frontend-dev` | F1 | `npm --prefix frontend run dev` (Vite, proxying `/api` to `127.0.0.1:8010`) |
| `frontend-test` | F1 | `npm --prefix frontend run check`: typecheck, lint, unit, component and contract tests with coverage |
| `frontend-e2e` | F2 | `npm --prefix frontend run e2e` (Playwright against its own `<POSTGRES_DB>_frontend_e2e`) |
| `frontend-build` | F1 | `npm --prefix frontend run build` (production build and budget report) |
| `demo-reset` | F5 | Resets the **hosted** demo database (§14 F5). It asks for explicit confirmation and prints no credential |

---

## 5. Toolchain and dependencies

- **Node:** 24 LTS (R-F-5), pinned by `frontend/.nvmrc` (`24`) and `package.json` `engines.node` (`>=24 <25`).
- **Package manager:** npm, with `frontend/package-lock.json` committed. Installs use `npm ci`, so the frontend
  **is** locked, unlike the Python side. That difference is deliberate.
- **Approved dependencies (DIRECTED set, names PROPOSED).** Majors are recorded at F1 install. The majors named
  here are floors, confirmed in Claw3D's August 2026 manifest.
  - **Runtime:**
    - `react`, `react-dom` (19)
    - `react-router`
    - `@tanstack/react-query` (5)
    - `zustand`
    - `zod`
    - `three` (≥ 0.183)
    - `@react-three/fiber` (9)
    - `@react-three/drei` (10)
    - `@react-three/postprocessing`, `postprocessing`
    - `tailwindcss` (4), `@tailwindcss/vite`
    - `radix-ui` (the primitives shadcn/ui components are copied onto)
    - `class-variance-authority`, `clsx`, `tailwind-merge`
    - `lucide-react`
    - `@fontsource/*` for the three font families of D-F-18
  - **Development:**
    - `typescript`
    - `vite`, `@vitejs/plugin-react`
    - `vitest`, `@vitest/coverage-v8`, `jsdom`
    - `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`
    - `msw`
    - `@playwright/test`, `@axe-core/playwright`
    - `eslint`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y`
    - `prettier`
    - `openapi-typescript`
    - `pg`, `@types/pg` (isolated-database tooling only, R-F-1)
    - `@types/three`
  - **Any package not listed is a stop-and-ask.** A transitive dependency is not a new package.
- **No runtime third-party requests:**
  - fonts are self-hosted through Fontsource;
  - there is no CDN, no analytics and no telemetry;
  - the only network origin at runtime is the page's own.
- **Vendored code:** code adapted from MIT projects lives in `frontend/src/vendor/`. Each file there keeps its
  upstream copyright header and is listed in `THIRD_PARTY_NOTICES.md` with its repository, path, commit and a
  summary of the changes.

---

## 6. API consumption contract

### 6.1 Origin (DIRECTED; DERIVED from D-F-11)

- Every request uses a relative path under `/api/v1/`.
- **Development:** a Vite proxy sends `/api` to `FRONTEND_API_TARGET`, which defaults to `http://127.0.0.1:8010`
  (R-F-1).
- **Production:** the same origin, through Vercel Services (§14 F5).
- **The backend never enables CORS.** No `VITE_*` variable carries a secret, because Vite embeds `VITE_*` values
  in the client bundle.

### 6.2 The client (`src/api/client.ts`)

- **JSON:** every request sends `Accept: application/json`. A POST sends `Content-Type: application/json`.
- **`X-Request-ID`:** it is read from every response, successful or not, and carried on the result or the error
  (DERIVED from `app/api/request_id.py`).
- **Error envelope** (DERIVED from `app/api/errors.py`): a non-2xx JSON body is
  `{"error": {"code", "message", "details", "request_id"}}`. It maps to
  `ApiError { status, code, message, details, requestId }`.
  - A network failure becomes `NetworkError`.
  - A non-JSON or unexpected body becomes `ContractError`.
- **Validation:** every response body is parsed with Zod before use. A parse failure is a `ContractError`, which
  renders the error state with the request id. **Partially valid data is never rendered.**
- **Retries:**
  - A GET is retried at most twice, with backoff, on a network error or a 5xx. It is never retried on a 4xx.
  - **A POST is never retried automatically** (§7.6, R-F-7).
- **Timeouts (PROPOSED):**
  - GET, 15 s;
  - `POST /risk/assessments`, 60 s;
  - other POSTs, 30 s.

### 6.3 Route catalogue (DERIVED from `app/api/v1/*.py`)

The frontend calls these routes and no others.

| Method and path | Used by | Parameters sent |
|---|---|---|
| `GET /api/v1/health` | HUD, MEMORY | — |
| `GET /api/v1/sources` | roster (§9.2), connector panels | — |
| `GET /api/v1/sources/{source}/health` | connector bulbs and panels | — |
| `GET /api/v1/ingestion/runs` | connector panels | `limit`, `offset` |
| `GET /api/v1/ingestion/runs/{run_id}` | connector panels | — |
| `GET /api/v1/ingestion/runs/{run_id}/errors` | connector panels | `limit`, `offset` |
| `POST /api/v1/ingestion/runs` | connector "Run ingestion" (R-F-6, F4) | `{"source": <source>}` only |
| `GET /api/v1/entities/{type}` for all seven types | MEMORY totals; names; ticket, deal, employee and document detail | `limit` (≤ 500), `offset`, `source_system` |
| `GET /api/v1/metrics/ingestion` | MEMORY | — |
| `POST /api/v1/risk/assessments` | HUD "Run assessment" | `{"as_of": <date or null>, "source_system": "csv_demo"}`. `customer_source_id` is never sent |
| `GET /api/v1/risk/assessments` | inbox, band counts, snapshots | `as_of`, `limit` (≤ 500), `offset` |
| `GET /api/v1/risk/assessments/{assessment_id}` | SIGNALS, SALES, SUPPORT panels | — |
| `GET /api/v1/risk/briefs/{brief_id}` | inbox status chips, brief detail, LINKER, RECONCILER and BRIEF_WRITER panels | — |
| `POST /api/v1/risk/briefs/{brief_id}/decision` | decision panel | `{actor, decision, note, payload_hash, supersedes_id}` |
| `GET /api/v1/risk/briefs/{brief_id}/decisions` | decision chain | — |

**Writes are exactly three:** assessments, decisions and (from F4) ingestion runs. The developer links `/docs`,
`/redoc` and `/openapi.json` are plain anchors and are never fetched by the app.

### 6.4 The brief payload (DERIVED from `VS01_IMPLEMENTATION_PLAN.md` §0.6.13.1)

- **Source of truth:** `src/api/schemas/briefPayloadV1.ts` mirrors §0.6.13.1 key for key.
  - The 12 top-level keys, as `.strict()` objects.
  - The frozen projections with their listed key sets: `signals` (17 keys), `reconciliation` (9), positions,
    conflicts, resolutions, `worthiness`, citations, and the `support_evidence` (6 keys) and `commercial_evidence`
    structures.
  - `Evidence.rule_id` is the only optional key.
- **Types:** decimals are strings and dates are `YYYY-MM-DD` strings. Integers are integers; a float anywhere is a
  `ContractError`.
- **Version check:** `payload_version !== 1` renders the **Unsupported brief** state (Appendix A) and no section of
  the brief. The payload is frozen at version 1 ("any change … forces version 2", `app/decisions/payload.py`).
- **The payload is never re-hashed client-side.** `payload_hash` is always the one the API returned.

### 6.5 Pagination

- Every list call pages with `limit=500` until `offset + items.length >= total`.
- No code assumes that one page is everything, even though today every entity type fits in one page (the largest
  has 80 rows).

### 6.6 Status semantics (DERIVED from `app/api/v1/risk.py`)

- **`POST /risk/assessments`:**
  - **201** means at least one result was created: the office plays a live episode.
  - **200** means every result already existed: the banner "Already assessed" plays instead (Appendix A).
- **Stored status:** `BriefResponse.status` is the stored column (`DRAFT`) and is never updated. **The UI shows
  `decision_status`, never `status`, as a brief's state.** `status` appears only in the brief's Technical section.

### 6.7 Server-state keys and invalidation (PROPOSED)

| After | Invalidate |
|---|---|
| A decision succeeds or conflicts | that brief; its decisions; the inbox |
| An assessment run returns | the assessment lists (every `as_of`); the inbox |
| An ingestion run returns | ingestion runs; metrics; entity totals; source health |

---

## 7. Domain rules

The modules in `src/domain/` are pure: no React, no three.js and no I/O. Their line and branch coverage is 100%.

### 7.1 Bands (DERIVED from `app/intelligence/contract.py` `RiskBand`)

- The order is NONE < WATCH < ELEVATED < CRITICAL. A band is always shown with its word and an icon; colour is
  never the only signal.
- The colours are PROPOSED: slate, yellow, orange and red.
- The legend carries the fixed line "A band is a policy artefact, not a probability." (Appendix A).
- **No function in `src/` produces a number from a band** for display.

### 7.2 Snapshots and the inbox (R-F-2)

- **Snapshot key:** `(as_of, source_system, layer1_fingerprint, rules_version, linker_version)`. These are all
  fields of `AssessmentListItem` (DERIVED).
- **The inbox shows one snapshot.**
  - After a run in this browser session, it shows that run's snapshot: the one containing the returned
    `assessment_id`s.
  - Otherwise it shows the first snapshot, in API order, at the selected `as_of`.
  - When the selected `as_of` has more than one snapshot, a selector lists them by short fingerprint and versions.
- **Rows:**
  - There is one row per brief id in `brief_ids`, over the snapshot's assessments.
  - Rows follow the assessments' API order, then the order within `brief_ids`.
  - Executive-worthy rows are then **stably** moved first, so API order is kept inside each group.
  - The API order within a snapshot is the ranking key (DERIVED from `_LISTING_ORDER`,
    `app/persistence/repositories/risk_queries.py`).
- **Each row shows:**
  - the band chip;
  - the executive badge;
  - `decision_status`, from `GET /risk/briefs/{id}`;
  - the customer's name and id (names from `GET /entities/customers`, matched on `source_id`; a missing name shows
    the id alone);
  - `policy_version` and `template_version`, only when an assessment has more than one brief.
- **Empty states:**
  - No assessment at the `as_of`: the empty state with the CTA "Run assessment".
  - Assessments but no brief: "No customer is at WATCH or above on this date." (Appendix A).

### 7.3 The brief view model (`src/domain/briefView.ts`)

Each section maps to exact payload paths (DERIVED from §0.6.13.1). Every path is prefixed by `payload.` unless it
names a `BriefResponse` field.

| Section | Source |
|---|---|
| Identity | `customer.id`; name via entities; `scope.source_system`, `scope.as_of`, `scope.layer1_fingerprint`; `payload_version`, `versions.rules`, `versions.linker`, `versions.policy` |
| Risk state and why | `band`, `satisfied_rules`, `reconciliation.worthiness` |
| Signals and derivations | `signals`; `support_evidence.derivations`; `support_evidence.escalation_window`; `support_evidence.ticket_span` |
| Evidence: tickets | `support_evidence.tickets[]`, each with its `evidence` |
| Evidence: documents | `document_evidence[]` |
| Evidence: deals | `commercial_evidence.deals[]` |
| Evidence: cited quotes | `cited_spans[]`, with the text of §7.4 |
| Commercial context per currency | `signals.active_deals`, `signals.exposure_by_currency` (no cross-currency total, §7.7), `signals.active_project_count` |
| Conflict and resolution | `reconciliation.conflicts`, `reconciliation.resolutions` |
| Recorded dissent | `reconciliation.dissent` |
| Policy and contract | `cited_spans`, `signals.contract_document_ids` |
| Chronic backlog | `support_evidence.backlog_ticket_ids` |
| Recommended actions | `reconciliation.resolved_positions`, in order |
| Escalation path | `support_evidence.escalation_path` |
| Narrative | `BriefResponse.narrative`, shown **verbatim**, monospace, not re-rendered |
| Technical | `BriefResponse.id`, `assessment_id`, `status`, `policy_version`, `template_version`, `payload_hash`, `citations.length` |

### 7.4 Cited text (DERIVED from the brief's limitations and from Python string semantics)

- A document's citable text is `title + "\n" + body_text`, taken from `GET /entities/documents`.
- `[start, end)` are **Python string indices, which count Unicode code points.** JavaScript indexes UTF-16 code
  units. The slice is therefore taken over `Array.from(text)`, never with `String.prototype.slice`.
- **Test:** for the recorded CUST-007 fixture, the three quotes equal the three quoted phrases in the golden brief's
  section 7 exactly.
- Display caps a quote at 500 code points and marks a longer one as truncated, following the brief's own cap.

### 7.5 The decision chain (DERIVED from `app/decisions/approval.py`)

- **The chain** is `GET …/decisions` `items`, in order. The head is the last item. An empty chain is shown as
  "No decisions recorded for this brief yet." (Appendix A).
- **The request body:**
  - `payload_hash` is the brief's own;
  - `supersedes_id` is the head's `id`, or `null` when the chain is empty;
  - `actor` is the trimmed name, 1–255 characters;
  - `note` is the trimmed text, up to 2000 characters, with an empty note sent as `null`;
  - `decision` is `APPROVED` or `REJECTED`.

### 7.6 Error handling (DERIVED from `app/decisions/approval.py`, `app/api/errors.py` and `risk.py`)

| Response | Shown | Then |
|---|---|---|
| 409 `DECISION_CONFLICT` with reason `SUPERSEDES_REQUIRED`, `PREDECESSOR_NOT_HEAD` or `CONCURRENT_DECISION` | "Someone recorded a decision on this brief meanwhile." | Reload the chain. Keep the chosen decision and the typed note; the user resubmits against the new head |
| 409 `DECISION_CONFLICT` with reason `PREDECESSOR_NOT_ON_BRIEF` | The generic defect message and the request id | Reload the chain |
| 409 `PAYLOAD_HASH_CONFLICT` with reason `REQUEST_HASH_MISMATCH` | "This brief changed since you opened it." | Reload the brief; keep the note |
| 409 `PAYLOAD_HASH_CONFLICT` with reason `STORED_PAYLOAD_MISMATCH` | "This brief's stored payload no longer matches its hash, so decisions on it are refused." | Disable the decision form for that brief and show the request id |
| 422 `SCOPE_UNRESOLVED` | "No support ticket exists to resolve the date from. Choose an explicit date." | Stay on the HUD |
| 422 `INVALID_REQUEST` | The field messages | Stay |
| 404 `BRIEF_NOT_FOUND` or `ASSESSMENT_NOT_FOUND` | The not-found state | Offer to return to the inbox |
| 500 on a POST | "Nothing was written." and the request id | Offer a retry. A POST owns one transaction and rolls back on failure (DERIVED, `risk.py`) |
| **Network failure or timeout on a POST** | "The result is unknown." | **Re-read first** (R-F-7): the chain for a decision, the list at that `as_of` for an assessment, the runs for an ingestion. Offer a retry only if the re-read shows the write did not land |

### 7.7 Money (DERIVED; the backend states "Decimal amounts are JSON strings, never floats")

- Amounts are formatted from their decimal **string**: digit grouping and fixed scale are applied by string
  manipulation. An amount is never parsed to a float for arithmetic.
- Amounts are shown per currency. **A cross-currency total is never computed.**

### 7.8 Dates (DERIVED)

- `as_of` and `created_date` are calendar dates. They are displayed as the string they are, and never passed
  through `Date` in the local time zone, which can shift the day.
- `decided_at` is an ISO timestamp. It is shown in local time, with UTC in a tooltip.

---

## 8. Product surfaces

### 8.1 URL scheme (PROPOSED)

| URL | Shows |
|---|---|
| `/` | the office |
| `/?agent=<agent-id>` | the office with that agent's panel open |
| `/?inbox=1` | the office with the CEO inbox open |
| `/brief/<brief-id>` | brief detail over the office |
| `/classic`, `/classic/inbox`, `/classic/briefs/<brief-id>`, `/classic/agents/<agent-id>` | Classic view |

- **Common query parameters:**
  - `as_of=YYYY-MM-DD`;
  - `snapshot=<first 12 hex characters of the fingerprint>`;
  - `pixel=0`;
  - `still=1` (freezes ambient motion for tests and screenshots);
  - `perf=1` (frame-time overlay).
- **Agent ids:** a connector's id is its source name (for example `csv_demo`). The others are `memory`, `linker`,
  `signals`, `sales`, `support`, `reconciler`, `brief-writer` and `ceo`.

### 8.2 HUD

- The product name (D-F-13).
- A health light from `/health`.
- The `as_of` selector. It defaults to `2026-09-18` and offers **Auto (latest ticket)** (D-F-14).
- **Run assessment**.
- Office/Classic toggle, Pixel/Smooth toggle, sound toggle (off, D-F-19), and a "?" tour.
- A **Replay** button that replays the selected snapshot's recorded results (§9.5).

### 8.3 Agent panels

Each panel has:
- a header: avatar, name tag, module path;
- a one-line role (Appendix A);
- the agent's real output;
- evidence links;
- the four states of §8.7;
- **Show the API call**: the route, status, duration and `X-Request-ID` of every request behind the panel.

The content per agent is fixed by §9.2.

### 8.4 Brief detail

- The sections of §7.3, in order.
- Every evidence item links to its record. A ticket, deal or employee opens a detail popover built from the
  entities list, and a document opens its citable text with the span highlighted.
- In the office, clicking a ticket id highlights SUPPORT_AGENT's desk. Clicking a document id highlights
  LINKER_AGENT's desk.

### 8.5 Decision panel

- Two choices, **Approve** and **Reject**; a note field (≤ 2000); and "Your name" (1–255).
- The name is remembered in this browser only, as a convenience (§11).
- The fixed line "Identity is recorded, not authenticated. Nothing is executed." always shows (Appendix A).
- The submit button reads "Record decision". It is disabled while the request is in flight or while the form is
  invalid.

### 8.6 Decision chain

- A vertical timeline, numbered ①, ②, and so on.
- Each entry shows actor, decision, note, `decided_at` and the first 12 characters of `payload_hash` (the full hash
  on hover). A `supersedes ①` link points at the entry it superseded.
- In the office, the same chain is pinned to the CEO's corkboard as notes, with APPROVED or REJECTED stamps.

### 8.7 The four states

Every panel and every Classic page has all four:
- **Loading:** skeletons. In the office, the agent keeps its desk and shows a "…" bubble.
- **Empty:** the fixed copy for that surface (Appendix A).
- **Error:** the message, the code and the request id, with **Retry** for a GET.
- **Success.**

---

## 9. The office

### 9.1 Rooms

The room set is DIRECTED; the grid and positions are PROPOSED (plan §4.1).

- **Open rooms:**
  - Data Dock, with the connector agents and MEMORY;
  - Evidence Lab (LINKER_AGENT);
  - Signals Desk (SIGNALS_AGENT);
  - Analyst Bullpen (SALES_AGENT, SUPPORT_AGENT);
  - Debate Table (RECONCILER_AGENT);
  - Brief Studio (BRIEF_WRITER);
  - CEO Corner Office;
  - Break Area, which is the destination for ambient motion.
- **Locked rooms (D-F-4):**
  - Pipeline Room: "Opens with VS-02";
  - Account 360: "Opens with VS-03";
  - War Room: "Opens with VS-04";
  - Copilot Desk: "Opens with VS-05".

### 9.2 The roster

The mapping is DIRECTED; props and colours are PROPOSED.

- The roster is the fixed VS-01 set below, **plus one connector agent per entry of `GET /sources`, in API order.**
  Connectors are never hard-coded.
- The About panel states that these are rule-based agents (Appendix A).

| Agent | Component | Panel content |
|---|---|---|
| `<SOURCE>_AGENT` (for example `CSV_DEMO_AGENT`) | `app/connectors/*` | Capabilities (`/sources`), the health result (`/sources/{s}/health`), the latest runs with per-entity counts and status, errors per run, and "Run ingestion" (R-F-6) |
| `MEMORY` | Layer 1 PostgreSQL | `/health`; the `total` of each of the 7 entity types; `/metrics/ingestion`; the snapshot's `layer1_fingerprint` |
| `LINKER_AGENT` | `app/evidence/linker.py` | The selected brief's `document_evidence` (basis, confidence, matched token, span) and its `cited_spans` with text |
| `SIGNALS_AGENT` | `app/intelligence/signals.py`, `bands.py` | The assessment's `signals`, `satisfied_rules` and band, plus the brief's `support_evidence.derivations`. Its monitor shows the real signal values |
| `SALES_AGENT` | `app/analysts/commercial.py` | Positions with `function == "SALES"` from `GET /risk/assessments/{id}` |
| `SUPPORT_AGENT` | `app/analysts/support_risk.py` | Positions with `function == "SUPPORT"` |
| `RECONCILER_AGENT` | `app/decisions/reconciler.py`, `policy.py`, `conflicts.py` | `reconciliation.conflicts`, `resolutions` (policy, `prevailing`, `rationale`, evidence), `dissent`, `worthiness` |
| `BRIEF_WRITER` | `app/decisions/brief.py`, `payload.py` | Narrative (verbatim), `payload_hash`, `policy_version`, `template_version`, citation count |
| CEO desk | `app/decisions/approval.py` | The inbox (§7.2), then brief detail, the decision panel and the chain. **The CEO is the human user; the desk is never animated as deciding** |

**The selected customer.** Panels that show one customer's data show the **selected brief's** customer. By default
that is the inbox's first row. Opening any brief makes it the selected one.

### 9.3 Visual language (D-F-12, D-F-18)

- **Name tags:** a black pill with white monospace capitals. They are HTML overlays and are never pixelated.
- **Antenna bulb:**
  - grey for IDLE;
  - cyan for WORKING;
  - amber for WAITING;
  - green for DONE;
  - red for ERROR.

  Each colour comes with a glyph as well.
- **Glow:** a green outline, only on an agent in WORKING or HANDOFF.
- **Bubbles:**
  - "?" for WAITING;
  - "…" while loading;
  - an action caption, which is always the data-backed text of §9.5.
- **Neon arrows:** cyan for hand-offs and red for a conflict. The label is always a §9.5 caption.
- **Palette:** a warm wood floor, cream walls and saturated role colours; neon for data flow.
- **Fonts:** a pixel face for in-world tags, a clean sans for panels, and monospace for ids and hashes. All are
  OFL, served through Fontsource. The families are PROPOSED: Silkscreen, Inter and JetBrains Mono.

### 9.4 Agent state machine (D-F-1)

| State | Entered when | Look |
|---|---|---|
| IDLE | By default, and after DONE or ERROR has shown for its dwell time | Ambient motion (§9.7); grey bulb; no glow |
| WORKING | A tracked request that belongs to this agent's stage is in flight (live), or its replay step starts | Typing or working pose; cyan bulb; glow; caption |
| HANDOFF | Its replay step emits an arrow | Walk to the receiver, or point; the arrow with its label |
| WAITING | The CEO desk has at least one PENDING brief in the shown snapshot (CEO desk only) | "?" bubble; amber bulb |
| DONE | Its replay step completes | Cheer pose; green bulb; confetti, only on a decision |
| ERROR | Its request failed | Red bulb; the error in its panel |

### 9.5 Episodes (`src/domain/episodes.ts`)

An episode is an ordered list of steps. **Every step carries `source: { route, path }`**, where `route` is the
request and `path` the JSON path of the value it shows.

**A step is emitted only when its data exists.** Unit tests assert this for every recorded fixture, and assert
that a no-conflict brief yields no conflict step.

**The assessment episode.** It is built after `POST /risk/assessments` returns, or on **Replay**, from:
- `GET /risk/assessments?as_of=` for the snapshot;
- `GET /risk/briefs/{id}` for its briefs;
- `GET /risk/assessments/{id}` for the featured assessment.

The **featured brief** is the inbox's first row. The steps, in the code's stage order (DERIVED,
`app/decisions/assessment.py`):

| # | Agent | Caption (data path) | Emitted only if |
|---|---|---|---|
| 1 | MEMORY | `SNAPSHOT <first 8 of layer1_fingerprint>` (list item) | the snapshot has at least one assessment |
| 2 | LINKER_AGENT | `<n> LINKS · <customer>` (`document_evidence.length` of the featured brief) | n > 0 |
| 3 | SIGNALS_AGENT | `<k> CRITICAL · <k> ELEVATED · <k> WATCH · <k> NONE` (band counts over the snapshot's list items; zero counts omitted) | always, given step 1 |
| 4 | SALES_AGENT, SUPPORT_AGENT | each function's first `proposed_action` in `reconciliation.ordered_positions` | that function has a position |
| 5 | SALES_AGENT ⇄ SUPPORT_AGENT (red arrow) | `CONFLICT <object_ref>` (`reconciliation.conflicts[i]`) | conflicts is non-empty |
| 6 | RECONCILER_AGENT | `<policy_id> → <prevailing.function> PREVAILS` (`reconciliation.resolutions[i]`) | resolutions is non-empty |
| 7 | BRIEF_WRITER → CEO desk | `BRIEF <customer>`, one delivery per inbox row | the snapshot has briefs |
| 8 | CEO desk | tray count = the number of inbox rows, and WAITING if any is PENDING | always, given step 7 |

**The ingestion episode (F4, R-F-6).** A connector agent is WORKING while `POST /ingestion/runs` is in flight.
Afterwards the arrow to MEMORY reads the run's own outcome (its status and per-entity counts) from the response. A
`NOOP` run says so.

**The decision episode.** A 201 lands the APPROVED or REJECTED stamp on the CEO desk and adds a corkboard note.
Confetti plays only for APPROVED.

### 9.6 Live and replay (D-F-1)

- **Live.** While a POST is in flight, the agents of the POST's stages are WORKING in stage order, with the caption
  `ASSESSING…` or `INGESTING…`. No intermediate value is shown, because none exists yet.
- **Replay.** After the response (201), or on Replay, the episode plays under the banner
  "Replay of recorded results · as_of <date>".
- **Already assessed.** On a 200 the banner is "Already assessed: replaying recorded results" (Appendix A).
- **The banner is present for the whole replay.** Dismissing it ends the replay.

### 9.7 Ambient motion

- Ambient walks go only between desks and Break Area destinations.
- Ambient motion **never** sets glow, a caption or a non-grey bulb.
- It is **deterministic**: a seeded pseudo-random generator, with the seed taken from a hash of the agent id.
  `?still=1` freezes it.

### 9.8 Rendering (D-F-5; parameters PROPOSED)

- **Camera:** orthographic. The elevation is 35°, the yaw starts at 45°, and rotation snaps in 90° steps. There are
  3 zoom stops, and camera positions snap to the pixel grid.
- **Pixel pass:** three.js `RenderPixelatedPass`, with `pixelSize` 3 at device pixel ratio 1 (scaled with DPR and
  zoom), `normalEdgeStrength` 0.3 and `depthEdgeStrength` 0.4, which are the pass's defaults.
- **Smooth toggle:** it bypasses the pass.
- **Materials:** `MeshToonMaterial` with a 3-step gradient.
- **Overlays:** drei `<Html>` for tags, bubbles and arrow labels.
- **Furniture:** CC0 glTF binaries (`.glb`) from Kenney or KayKit, instanced where repeated.

### 9.9 Characters

- Built procedurally from primitives, about 2.5 heads tall.
- Poses: stand, walk, sit, type, present and cheer.
- Each role has a distinct silhouette and prop:
  - a hard hat for connectors;
  - a robot body for MEMORY;
  - a magnifier for the linker;
  - an abacus for signals;
  - a suit and chart for sales;
  - a headset for support;
  - a wig and gavel for the reconciler;
  - a typewriter for the brief writer.
- The CEO chair stays empty; the user is the CEO.
- Any code adapted from agent-office or Claw3D goes in `src/vendor/` (§5).

### 9.10 Performance budget (PROPOSED numbers; the budget itself is DIRECTED by D-F-10's gates)

| Measure | Budget |
|---|---|
| Frame time on the reference machine at 1920×1080, every agent moving, over 30 s via `?perf=1` | median ≤ 16.7 ms, p95 ≤ 25 ms. The reference machine is the owner's laptop, and its model is recorded |
| Draw calls | ≤ 150 |
| World assets (models and textures) | ≤ 5 MB |
| Initial JavaScript (Classic view path) | ≤ 250 KB gzip |
| World chunk | ≤ 900 KB gzip, loaded lazily |

**Classic view never downloads the world chunk.**

### 9.11 Fallbacks

- If a WebGL context cannot be created, or is lost twice in a session, the app switches to Classic view with the
  WebGL notice (Appendix A).
- **Reduced motion:** under `prefers-reduced-motion`, walking becomes instant placement, and confetti, pulsing and
  camera easing are off.

### 9.12 Sound (D-F-19)

- Sound is off by default and persists per browser.
- When on, it plays soft keyboard clicks while an agent is WORKING and a stamp sound on a decision.
- Sounds are synthesised with Web Audio; there are no audio files.

### 9.13 Locked rooms and NEW HIRE (D-F-4)

- `src/domain/roster.ts` marks each room locked or unlocked.
- Unlocking a room is part of the future slice's own frontend phase.
- The "NEW HIRE!" ceremony plays once per agent per browser. Its flag is kept in `localStorage` inside try/catch;
  when storage is unavailable, the ceremony simply plays again.

---

## 10. Accessibility

- Panels and Classic view meet **WCAG 2.2 AA**. `@axe-core/playwright` reports 0 serious and 0 critical violations
  on every Classic route and every panel.
- **Staff directory:** a keyboard-reachable list of every agent mirrors the office. Enter opens the agent's panel.
  It is the accessible path to everything the canvas shows.
- Focus is always visible. Panels trap focus while open and return it on close.
- Colour never carries meaning alone (bands, bulbs, stamps).
- Reduced motion is respected (§9.11).

---

## 11. Security, privacy and honesty

- **No secrets exist in the frontend.** No `VITE_*` variable carries a secret (§6.1).
- **Naming rule (R-F-3; DERIVED from `scripts/secret_scan.py`).**
  - No identifier or object key in frontend source, configuration or fixtures contains `password`, `passwd`,
    `pwd`, `secret`, `token`, `api_key`, `api-key`, `apikey`, `access_key` or `private_key`.
  - "Design tokens" are called **theme variables**.
  - `tests/unit/test_g2_secret_hygiene.py::test_the_repository_has_no_committed_secrets` scans **every tracked
    file**, so a finding in `frontend/` fails the backend suite.
- **Browser storage** is used for conveniences only, always inside try/catch:
  - `aiceohq.actorName`;
  - `aiceohq.view`;
  - `aiceohq.pixel`;
  - `aiceohq.sound`;
  - `aiceohq.hired.<agent-id>`.
- **Runtime requests** go to the page's own origin only (§5).
- **Honesty copy** is fixed text (Appendix A), and AC-F-15 checks it. The copy states:
  - identity is not authenticated and nothing is executed;
  - the agents are rule-based, with no language model in VS-01;
  - a band is not a probability;
  - replays are replays.
- **Data:** the hosted demo holds only the synthetic `data/demo` dataset.

---

## 12. Tests, fixtures and isolation

### 12.1 Layers

| Layer | Tool | Covers | Gate |
|---|---|---|---|
| Unit | Vitest | `src/domain/**`, `src/api/**` | 100% lines and branches |
| Component | Vitest, Testing Library, MSW | every panel and Classic page, in all four states | 0 failed, 0 skipped |
| Contract | Vitest | Zod schemas against the recorded fixtures (§12.2) | 0 failed |
| End-to-end | Playwright | real API, isolated database (§12.3) | 0 failed, 0 skipped |
| Accessibility | `@axe-core/playwright` inside e2e | §10 | 0 serious, 0 critical |
| Visual | Playwright screenshots | Classic routes, pixel-exact within `maxDiffPixelRatio` 0.01; the office at `?still=1`, within 0.05, plus a non-blank canvas check | 0 failed |
| Performance | `?perf=1`, recorded by hand | §9.10 | within budget |
| Bundle | build report | §9.10 | within budget |
| Guards | Vitest | §12.4 | 0 failed |

### 12.2 Recorded fixtures

- **Where they come from:** only from the real API, served over the isolated clean database of R-F-1 at `as_of
  2026-09-18`. The recording tool is `frontend/tools/record-fixtures.ts` (PROPOSED name).
- **Where they live:** `frontend/tests/fixtures/`, with a `PROVENANCE.json` holding the commit, the routes, the
  `as_of`, the database revision and the recording time.
- **Validity checks,** run as contract tests:
  - the CUST-007, CUST-025 and CUST-036 `payload_hash` values equal §3's;
  - `payload.scope.layer1_fingerprint` equals the pinned fingerprint;
  - **CUST-007's `narrative` is byte-identical to `tests/golden/vs01_cust007_brief.txt`.** That file is read, never
    written.
- **Fixtures never reach the product.** ESLint's `no-restricted-imports` forbids `src/**` importing from
  `tests/**`.

### 12.3 Isolated databases (R-F-1)

- **Names:** `<POSTGRES_DB>_frontend` for development and `<POSTGRES_DB>_frontend_e2e` for end-to-end tests.
- **Every run recreates its database from clean.** The tooling:
  1. drops and creates the database through `pg`;
  2. runs `.venv/bin/alembic upgrade head`;
  3. runs `.venv/bin/python scripts/ingest_demo.py`, with `DATABASE_URL` pointing at the isolated database;
  4. serves the working-tree app with `.venv/bin/uvicorn app.main:app` on `127.0.0.1:8010` for development, or an
     OS-assigned port for end-to-end tests;
  5. runs the assessment through `POST /api/v1/risk/assessments`.
- **Invariants:**
  - **The tooling refuses any database name without its suffix.** It never opens the development database, and
    never touches the Docker containers.
  - If PostgreSQL is unreachable, it exits with status 2 and **never falls back.**
  - It prints no credential. It reads connection settings from the environment or the repository `.env`.
- **Concurrency:** end-to-end tests never run concurrently with themselves. They may run alongside the backend
  suite, because the database names differ.

### 12.4 Guards (tests)

- **No fake data:** `src/` contains no customer, ticket, deal, document, employee or project id literal. The pattern
  is `\b(CUST|TKT|DEAL|DOC|EMP|PRJ)-\d{3}\b`, checked outside comments.
- **No score:** `src/` renders no percentage and no `/100` next to a band.
- **Notices:** every file in `src/vendor/` and every model in `public/models/` is listed in
  `THIRD_PARTY_NOTICES.md`.
- **Honesty:** every Appendix A string exists exactly once in `src/`, and its surface renders it.
- **Naming:** no identifier matches §11's list. This is checked with the secret scanner's own `SECRET_NAME` pattern,
  copied as a test constant with the scanner's path and commit cited.

---

## 13. Baseline, regression and the gate

**F1's first step measures the baseline** read-only, before any file is created:
- every §3 value;
- the full backend suite (counts per layer, coverage, ruff, mypy, secret scan);
- the untracked and staged state.

A difference from §3 is reported, not accommodated.

**Every phase gate runs and reports the following.**

1. **Frontend:**
   - `tsc --noEmit` 0;
   - ESLint 0 errors and 0 warnings;
   - Vitest counts per layer, 0 failed and 0 skipped, with coverage;
   - Playwright counts, 0 failed and 0 skipped, from F2;
   - axe;
   - bundle sizes;
   - the performance record, from F3.
2. **The backend is untouched:**
   `git diff --stat 733b19b -- app config migrations alembic.ini data tests scripts Dockerfile docker-compose.yml docker .env.example pyproject.toml`
   is empty.
3. **Repository scans:** the four backend test files that read the whole repository pass in the backend `.venv`:
   - `tests/unit/test_g2_secret_hygiene.py`;
   - `tests/unit/test_i2_readme.py`;
   - `tests/unit/test_i1_verify_units.py`;
   - `tests/unit/test_docker_packaging.py`.
4. **Secret scan over the phase's files:** `scripts/secret_scan.scan_text` over every new or changed file, before
   staging. After the owner approves staging, `make secret-scan` over the staged tree. Both report 0 findings.
5. **Anchors:** the golden sha, the one migration head, and the strategy document's diff sha all equal §3.
6. **`git status`** shows only the phase's allowed paths (§4) and the strategy document.

**The full backend suite** runs at F1's baseline, at the F5 gate and at the F6 gate. Its counts must equal the
baseline.

**The pass condition.** Every measurement equals the baseline, except the frontend's own counts and sizes. Any
other difference stops the phase. **No failure is tolerated in the interim.**

---

## 14. Phases, gates and commits

| Phase | Entry condition | Work | Exit gate | Commit, on the owner's explicit approval |
|---|---|---|---|---|
| **F0 — Specification** | The plan approved, 2026-09-28 | This document; the plan's status header and §17 corrections | The self-review: only the two `CONTEXT/` files changed, nothing is staged, the strategy document is untouched, and `scan_text` finds 0 in both files. **Then STOP for the owner's review.** R-F-1…R-F-8 are resolved | `F0: finalize frontend specification` (these two files only) |
| **F1 — Foundation** | Commit F0 exists; R-F resolved; Node 24 installed; the owner's go | (a) The read-only baseline (§13). (b) Scaffold `frontend/` (§5); `.nvmrc`; lockfile; ESLint, Prettier, Vitest, Playwright, Tailwind and shadcn/ui setup. (c) `src/api/client.ts`, generated OpenAPI types, the Zod schemas (§6.4). (d) The isolated-database tooling and `make frontend-backend` (§12.3). (e) Recorded fixtures and their contract tests (§12.2). (f) Router, TanStack Query, theme variables, fonts, the HUD, the Classic shell, the four states. (g) The §4.1 F1 Makefile targets and the `.gitignore` lines | §13's gate. A Playwright smoke test: the HUD shows `/health` from the isolated API. Contract tests prove the fixtures' provenance | `F1: add the frontend foundation` |
| **F2 — Classic view** | Commit F1 exists | All of `src/domain/` (§7); every panel (§8.3–§8.7) as Classic pages; deep links; Show the API call; `make frontend-e2e` | The gate. End-to-end: assess at `2026-09-18`; CUST-007 pinned `CRITICAL · EXECUTIVE`; CUST-025 and CUST-036 follow; approve CUST-007; the chain and status update. Then reject with supersede; both 409 families (§7.6); an empty chain; an API-down state. axe is clean | `F2: add the classic view` |
| **F3 — The office** | Commit F2 exists | Rooms, furniture, `THIRD_PARTY_NOTICES.md`, camera, pixel pass, the Smooth toggle; agents in place with tags, bulbs and click targets; panels as drawers; the SIGNALS monitor; the staff directory; the WebGL fallback | The gate. The performance budget (static scene). Classic view never loads the world chunk (network assertion). Screenshots at `?still=1` | `F3: build the office` |
| **F4 — Life** | Commit F3 exists | The walk grid and A\* (vendored from Claw3D); ambient motion (§9.7); episodes (§9.5); the Director; live and replay banners (§9.6); ingestion from the UI (R-F-6); the decision stamp; reduced motion; sound | The gate. Episode unit tests (every step's `source` resolves in its fixture; no step without data). End-to-end: Run assessment, then the replay, then 3 briefs in the tray, then approve from the office. The performance budget (every agent moving) | `F4: bring the office to life` |
| **F5 — Hosting** | Commit F4 exists; **each external action separately approved** (creating the Vercel project, Neon, environment variables, every deployment) | (a) The full backend suite in a fresh Python 3.12 venv, recorded, which decides D-F-17's path (R-F-8). (b) `vercel.json` (§6.1 origins; `/api/(.*)`, `/docs`, `/redoc` and `/openapi.json` to the API service; everything else to the web service; `excludeFiles` for `tests/**`, `data/fixtures/**`, `data/quarantine/**`, `CONTEXT/**`, `frontend/**`). (c) The `.dockerignore` line. (d) Neon migrated and seeded from the owner's machine; `make demo-reset`, proven twice. (e) A firewall rate-limit rule on `POST /api/*`, where the plan allows it. (f) The README section (R-F-4) | The gate. A Playwright smoke test against the preview URL: health, inbox, open a brief, approve, reset, then clean again. The full backend suite at baseline | `F5: host the frontend and API on Vercel` |
| **F6 — Polish** | Commit F5 exists | The three-step tour, responsive behaviour (below 768 px goes to Classic), empty-state art, a copy review, a performance pass, a timed demo rehearsal (≤ 5 minutes) on the hosted site | The gate. Every AC-F criterion (§15) with its evidence. The full backend suite at baseline | `F6: polish the demo` |
| **F7 — Industry-readiness** | **Separate backend milestones approved and closed first** (authentication, roles, an inbox read endpoint) | Out of this document's authority beyond its outline. It needs its own specification section | — | — |

**Phase records.** Each phase's commit appends that phase's record to §19: what was built, the gate's
measurements, and any owner rulings. There is no separate closure commit (D-F-10, UI-sized).

**The commit rules are unchanged since M5.**
- Nothing is staged, committed, pushed, amended or rebased without the owner's explicit approval.
- Each commit stages files by explicit path.
- The author and committer are the owner's identity.
- No commit carries an attribution trailer.
- The strategy document is never staged.
- A push, and a deployment, each need their own approval.

---

## 15. Acceptance criteria

The track passes only if every criterion holds.

| # | Criterion | Evidence |
|---|---|---|
| AC-F-1 | Every value in a panel or an in-world label traces to an API response. `src/` holds no domain data | §12.4 guards; episode `source` tests |
| AC-F-2 | A WORKING pose occurs only during an in-flight tracked request or a bannered replay | Director unit tests; F4 end-to-end |
| AC-F-3 | Risk appears only as the four-level band, with its word. There is no score or percentage | §12.4 guard; component tests |
| AC-F-4 | Inbox order equals §7.2's rule over the API order | Unit tests on recorded lists; F2 end-to-end |
| AC-F-5 | On a clean isolated database at `2026-09-18`: CUST-007 is pinned `CRITICAL · EXECUTIVE`; CUST-025 and CUST-036 follow; approving creates the decision; the chain and `decision_status` update | F2 end-to-end |
| AC-F-6 | Every §7.6 response renders its row's message and behaviour, and no typed note is lost | Component and end-to-end tests |
| AC-F-7 | Classic view renders every surface without WebGL and without downloading the world chunk | F3 network assertion; Classic end-to-end |
| AC-F-8 | The world meets §9.10, and a WebGL failure falls back to Classic view | Performance record; fallback test |
| AC-F-9 | The backend is untouched, and the backend suite is at baseline | §13 items 2, 3 and the full-suite runs |
| AC-F-10 | The hosted site is same-origin with no CORS, and `demo-reset` has been proven twice | F5 record |
| AC-F-11 | `THIRD_PARTY_NOTICES.md` is complete | §12.4 guard |
| AC-F-12 | §10 holds: axe clean, keyboard reachable, reduced motion | axe results; tests |
| AC-F-13 | The secret scan is 0 over every tracked file, including `frontend/` | §13 item 4; the backend hygiene test |
| AC-F-14 | Every surface has all four states | Component tests |
| AC-F-15 | Every Appendix A string is present, and shown where specified | §12.4 guard; component tests |
| AC-F-16 | The fixtures are genuine: their hashes, fingerprint and golden narrative equal §3 | Contract tests |
| AC-F-17 | Isolation holds: no frontend tooling opens the development database, and a run without PostgreSQL exits 2 with no fallback | Tooling tests. The development database's customer count and newest assessment, read before and after F1's and F2's gates, are equal |

---

## 16. Known limitations

These are carried into the phase records.

- **The actor is not authenticated** until F7. On the hosted site anyone can record a decision, which is why the
  database is disposable (D-F-8).
- **Live mode cannot show intermediate progress.** The API emits no events, so live mode shows WORKING poses and
  then replays the recorded result.
- **Episodes dramatise the featured brief only.** The other briefs are delivered without a debate scene.
- **The inbox makes N + 1 requests,** and entity joins happen client-side. That is acceptable at 3 briefs and
  233 rows; F7 names the backend endpoint that removes it.
- **Mock sources are unreachable on the hosted site.** Their agents show the real failed health check.
- **The performance budget is measured on one machine.** Office screenshots use a tolerance, because WebGL output
  varies by GPU.
- **Vercel Services is in beta.** F5's fallback is two projects with a rewrite (plan §8.2).

---

## 17. Corrections to the plan

These plan statements were corrected in `FRONTEND_OFFICE_PLAN.md` before F0, and this document governs them.

1. **Plan §7, row "Layer 1 fingerprint".** It cited `payload.scope.entity_counts`. The payload's `scope` has
   exactly three keys (§0.6.13.1). Entity counts come from the entities' `total`.
2. **Plan §7, row for the brief panels.** It placed `tickets`, `escalation_path`, `derivations`, `ticket_span` and
   `backlog_ticket_ids` at the payload's top level. They sit under `payload.support_evidence`, and deals sit under
   `payload.commercial_evidence.deals`.
3. **Plan §4.4, step 4.** It spoke of "other WATCH and ELEVATED briefs". At `2026-09-18` there are exactly two
   others, both WATCH (CUST-025 and CUST-036), and no ELEVATED.
4. **Plan §8.2 and F5.** They mentioned a "Python version pin" file. R-F-8 proposes no repository-level pin.
5. **Plan §8.1.** It assumed the Docker stack serves frontend development. R-F-1 replaces that with an isolated
   database and the working-tree API.

---

## 18. Review items R-F-1…R-F-8

All eight were put to the owner as proposals. **On 2026-09-28 the owner accepted every proposal as written. They
are now DIRECTED and authoritative.** Each keeps its finding, so the reason for its resolution survives.

| # | Finding | Resolution (DIRECTED 2026-09-28) |
|---|---|---|
| **R-F-1** | The development database is not the clean dataset (§3: 52 customers; fingerprint `3305b0d9…`; assessments at `2026-09-27`). Fixtures recorded from it could never match the golden brief, and developing against it would mix the owner's state with test writes | The frontend gets **its own isolated databases** (§12.3), recreated from clean, served by the working-tree API on `127.0.0.1:8010` (development) or an OS-assigned port (e2e). The tooling never opens the development database or the Docker containers, and **never falls back**; it exits 2. This mirrors R-M9-1 |
| **R-F-2** | `GET /risk/assessments` orders by `as_of`, then fingerprint and versions, before the ranking key. Two snapshots at one `as_of` therefore interleave in blocks, and "current" cannot be read from the list. An assessment may also have several briefs ("None is current: every brief is listed") | The inbox shows **one snapshot** chosen by §7.2's rule, with a selector when there are several, and **one row per brief** |
| **R-F-3** | `test_the_repository_has_no_committed_secrets` scans every tracked file, including `frontend/**` and `package-lock.json`. `scripts/secret_scan.py`'s quoted-assignment rule flags any `…token…`/`…secret…` name assigned a quoted value of 8+ characters with no spaces. That includes "design tokens" and some lockfile entries. The scanner, its allow-list and the test are frozen | Apply §11's naming rule, and scan every phase's files before staging (§13 item 4). **A finding that cannot be renamed away (for example in the lockfile) stops the phase.** The owner then chooses between pinning another version and authorising an allow-list entry, which would be a backend test-and-scanner evolution with its own approval |
| **R-F-4** | `test_i2_readme` accepts only `make`, `docker`, `cp`, `curl`, `alembic`, `pytest`, `python`, `python3`, `git`, `source`, `psql`, `export`, `uvicorn` and `pip` in README `bash` blocks. It bans "TODO", "TBD" and "Coming soon", and requires every named `make` target to exist | The README's `## Frontend and demo` section prints **only `make` commands** in `bash` blocks, and avoids the banned words. The npm-level commands are documented in `frontend/README.md`, which no backend test reads |
| **R-F-5** | Local Node is `v23.10.0`, an odd-numbered release with no long-term support | Pin **Node 24 LTS** (§5). Installing it is an owner action before F1 |
| **R-F-6** | The plan animates connectors working, but only an ingestion request makes them work. `POST /ingestion/runs` is a write. It is idempotent: an unchanged source yields a `NOOP` run | F4 adds **Run ingestion** to a connector's panel, **enabled only when that source's health check is OK**. It sends `{"source": …}` only. It is the third and last write (§6.3) |
| **R-F-7** | A POST that times out or loses the network has an unknown outcome. A blind retry could record a second decision | On an unknown outcome, **re-read before offering a retry** (§7.6). No POST is ever retried automatically |
| **R-F-8** | Vercel runs Python 3.12–3.14 and reads the version from `pyproject.toml` or `.python-version`. A root `.python-version` of `3.12` would also steer local `uv` and pyenv environments away from the owner's 3.11 `.venv` | **No repository-level Python pin.** F5 sets the version in the Vercel service configuration if supported; otherwise it relies on Vercel's documented default (3.12, which satisfies `requires-python >=3.11`) and records the runtime version it observes. `pyproject.toml` stays frozen |

---

## 19. Phase records

*Each phase's commit appends its record here.*

### F0 — Specification: CLOSED 2026-09-28

**What F0 produced.**
- This document, v1.
- `CONTEXT/FRONTEND_OFFICE_PLAN.md`, with its APPROVED status header and the five corrections of §17.

No other file changed.

**Owner rulings, 2026-09-28 (DIRECTED).**
1. The plan is approved, with every recommendation from the questioning round (D-F-1…D-F-12).
2. The open items O-1…O-7 are resolved as recommended (D-F-13…D-F-19).
3. The review items R-F-1…R-F-8 are resolved as proposed (§18).
4. Commit F0.

**The gate (§14 F0), measured before the commit.**
- The staged tree holds exactly the two files above, both added. Nothing under any frozen path of §4 differs from
  `733b19b`: 0 tracked changes outside `CONTEXT/`.
- The strategy document is unstaged, and its diff sha256 still begins `94e4e5b2f65616f6`. The golden brief's
  sha256 still begins `87d1398661b0c300`.
- `scripts/secret_scan.scan_text` finds 0 in each file. The staged-tree `make secret-scan` recipe reports 367 files
  scanned, 3 binary files skipped and 0 findings.
- The four repository-scanning backend test files of §13 item 3 pass with the two files staged: 256 passed and
  0 failed. There are 2 warnings, both the known third-party anyio/starlette deprecations.
  - They were run in the repository `.venv` with the pytest cache, the bytecode cache, the ruff and mypy caches and
    the coverage file all kept out of the repository.
- Every internal link in both files resolves to a heading.

**Not run in F0:** the full backend suite. F0 changes documentation only. The full suite first runs at F1's
baseline step (§13).

**Next:** F1, which starts only on the owner's instruction. Its entry condition includes installing Node 24 LTS
(R-F-5).

### F1 — Foundation: CLOSED 2026-09-28

**What F1 produced.**
- `frontend/`, 86 files:
  - **Toolchain:** Node 24 pinned by `.nvmrc`, `engines` and `package-lock.json`; TypeScript strict, ESLint, Prettier,
    Vitest, Playwright, Tailwind 4 and three copied shadcn/ui primitives.
  - **API layer:** `src/api/client.ts` (§6.2), one module per route family of §6.3, the Zod schemas
    (`briefPayloadV1.ts` mirrors §0.6.13.1 key for key), and `src/api/generated/openapi.d.ts`, generated from
    the recorded `/openapi.json`.
  - **Tooling:** the isolated-database tooling (`tools/lib/isolated.ts`, `tools/backend.ts`, R-F-1), the fixture
    recorder (`tools/record-fixtures.ts`) and the bundle report (`tools/bundle-report.ts`).
  - **Fixtures:** 11 recorded exchange files, `openapi.json` and `PROVENANCE.json` (§12.2).
  - **App:** the router, TanStack Query, theme variables, the three font families, the HUD, the Classic shell and
    the four states.
  - **Tests:** five Vitest layers and the Playwright smoke test.
  - **Docs:** `THIRD_PARTY_NOTICES.md` and `README.md` (the npm-level commands, R-F-4).
- `Makefile`: `frontend-install`, `frontend-backend`, `frontend-dev`, `frontend-test` and `frontend-build`. Each is
  added to the first `.PHONY` block, given a recipe and listed by `make help`. No existing target, recipe or help
  line changed.
- `.gitignore`: exactly the six lines of §4.
- `scripts/secret_scan.py`: one `ALLOWED_FINDINGS` entry (owner ruling 3). This is the only change under a
  frozen path.

**Owner rulings, 2026-09-28 (DIRECTED).**
1. **Packages outside §5.** `@types/react`, `@types/react-dom` and `@types/node` are approved as development
   dependencies. They are type-only; React 19 ships no types, and `tools/` and the configurations run on Node.
2. **Browser.** Playwright uses the installed Google Chrome (`channel: 'chrome'`), and no browser is downloaded.
   Carried forward: Chrome updates itself, so F2's and F3's screenshot baselines may need re-approval after a
   Chrome update.
3. **R-F-3 stop, resolved by an allow-list entry.**
   - **The finding.** In the real CUST-007 brief, each of the three `ID_TOKEN` links has the key
     `matched_token` with the value `CUST-007`. The frozen scanner's `quoted_secret_assignment` rule flags that:
     a name containing `token`, and a value of exactly 8 characters with no placeholder marker. The key is the
     API's own, so it cannot be renamed away.
   - **The ruling.** Every recorded brief lives in one file, `frontend/tests/fixtures/briefs.json`. One entry is
     pinned to that path, the rule and fingerprint `f98ec4491f30` (the value `CUST-007`), with the reason
     "recorded API fixture: matched_token is the synthetic customer source id CUST-007".
   - **What the edit is.** It is data only (+2 lines), made on the owner's approval as an exception to D-F-11 and
     to §4's frozen `scripts/`. Because of it, the full backend suite was re-run at the gate.
4. **The naming guard (§12.4).** It exempts only keys the frozen backend defines, each listed with the code that
   emits it. Today that is only `matched_token` (`app/intelligence/contract.py`, `DerivedLink.to_payload`). A test
   asserts that each exemption is really emitted by that file and really mirrored by the payload schema. Every
   name the frontend chooses is still checked.

**Choices made in F1 (PROPOSED; each stands unless replaced).**
- **Majors at install (§5).**
  - React 19.3, React Router 8.4, TanStack Query 5.104, Zod 4.6, three 0.186, R3F 9.8, drei 10.7, Tailwind 4.3,
    Vite 8.3, Vitest 5.0, Playwright 1.63.
  - **TypeScript 5.9.3, not 7:** typescript-eslint 8.70 requires `<6.1` and openapi-typescript 7.13 requires `^5`.
  - **ESLint 9.39.5, not 10:** eslint-plugin-jsx-a11y 6.10 peers stop at ESLint 9. npm reports 9.39.5 as no longer
    supported; this is carried forward.
- **The HUD in F1** carries the product name, the health light and the `as_of` selector.
  - Run assessment moves to F2, with the inbox that shows its result and the unknown-outcome re-read it needs.
  - The Office/Classic, Pixel/Smooth and sound toggles, Replay and the tour arrive with the phases that build what
    they control.
- **Routes.** `/` opens Classic view, keeping the query, until F3's office exists. Auto is written in the URL as
  `as_of=auto`.
- **A 5xx without the API's error envelope** (a proxy or gateway answering for an unreachable API) is a
  `NetworkError`. A GET retries it; for a POST, it is an unknown outcome (§7.6).
- **Fixture recording** uses `<database>_frontend_e2e` on an OS-assigned port, so it never collides with a running
  `make frontend-backend`. It must not run at the same time as the end-to-end tests.
- **The no-fake-data guard** also matches `PROJ-nnn` and `ORG-nnn`, because the dataset's project and organisation
  ids use those prefixes. The `PRJ` of §12.4 matches none of them.
- **Tests beyond the spec's minimum.**
  - A contract test re-hashes each recorded payload under a port of M1's `canonical_json`, as a test-only
    provenance proof. The product never re-hashes (§6.4).
  - A type-level test proves every Zod response type is assignable to its generated OpenAPI type.
- **End-to-end** tests serve the production build through `vite preview`, so F3's network assertion on the world
  chunk can use the same setup.

**The baseline (§13), measured read-only before any file was created.**
- `HEAD` is `21ded97` (the F0 commit) and `origin/main` is `2b6deb3`, 10 ahead.
- Tracked files: 370, which is §3's 368 plus F0's two.
- The golden sha begins `87d1398661b0c300`, the one migration head is `070e4968a497`, and the strategy
  document's diff sha begins `94e4e5b2f65616f6`.
- **The full backend suite equals §3:** 6771 passed (unit 5287, contract 185, integration 1214, e2e 85), with 0
  failed and 0 skipped. `app/` line coverage is 100% over 7456 statements, with 2 warnings (the known anyio and
  starlette deprecations). Ruff reports 69, mypy 9, and the secret scan 0 findings over 367 files scanned plus 3
  binary.
- **The development database** (read-only GETs) has 52 customers and 1 assessment, at `as_of 2026-09-27` with
  fingerprint `3305b0d9…`.

**The gate (§13).**
1. **Frontend.**
   - `tsc` reports 0 on both projects, ESLint 0 errors and 0 warnings, and Prettier is clean.
   - **Vitest:** 182 passed, 0 failed, 0 skipped. By layer: unit 62, component 23, contract 41, guards 34,
     tools 22.
   - **Coverage:** `src/api/**` and `src/domain/**` are at 100% of lines, branches, functions and statements.
     All of `src/` is 98.8% of statements. The remainder is `main.tsx`'s bootstrap, which the end-to-end tests
     exercise, a `NavLink` inactive branch and `Button`'s unused `asChild`.
   - **Playwright:** 3 passed and 0 skipped. The HUD shows `GET /api/v1/health` from the isolated API, and the
     displayed request id equals the response's `X-Request-ID`. `/` opens Classic view at `2026-09-18`. axe reports
     0 serious and 0 critical violations on `/classic`.
   - **Bundle:** initial JavaScript is 145.5 KB gzip of the 250 KB budget, and CSS is 16.8 KB gzip. Fonts are
     loaded on use. There is no world chunk yet.
   - **`make frontend-install`** (`npm ci`) installs cleanly from the lockfile with 0 vulnerabilities. npm 11 skips
     two install scripts (msw's optional postinstall and fsevents'); nothing depends on them.
2. **The backend.** `git diff --stat 733b19b -- app config migrations alembic.ini data tests scripts Dockerfile
   docker-compose.yml docker .env.example pyproject.toml` lists only `scripts/secret_scan.py | 2 ++` (ruling 3).
   **The full backend suite was re-run on that tree, and it equals the baseline:** 6771 passed (unit 5287,
   contract 185, integration 1214, e2e 85), with 0 failed and 0 skipped. `app/` coverage is 100% over 7456
   statements, with the same 2 warnings. Ruff reports 69 over `app/ tests/ scripts/`, and mypy 9.
3. **The four repository-scanning backend test files** pass on the staged tree: 256 passed and 0 failed, with the
   2 known warnings. They ran in the repository `.venv`, with the caches and the coverage file kept out of the
   repository.
4. **The secret scan.**
   - `scan_text` over all 89 new or changed files reports 0 findings with the allow-list. Without it, there are
     exactly the three `briefs.json` findings, all with fingerprint `f98ec4491f30`.
   - The scan also caught a made-up credential in `tests/tools/isolated.test.ts`. It was renamed to a value
     carrying the scanner's `fake` placeholder marker, not allow-listed (R-F-3).
   - **Staged `make secret-scan`:** 453 files scanned, 3 binary files skipped (456 tracked, which is 370 + 86)
     and 0 findings.
5. **Anchors.** The golden sha, the one migration head `070e4968a497` and the strategy diff sha all equal §3.
6. **`git status`** shows only `frontend/`, `Makefile`, `.gitignore`, `scripts/secret_scan.py` (ruling 3) and the
   unstaged strategy document.

**AC-F-17.**
- The development database's `GET /risk/assessments` and `GET /entities/customers` responses are byte-identical
  before and after the gate.
- A run without PostgreSQL exits 2, before any migration and without printing a credential. Tooling tests cover
  both `record-fixtures` and `frontend-backend`.
- `<database>_frontend` and `<database>_frontend_e2e` now exist on the local server. Every run recreates them.

**Fixture provenance.**
- Recorded at `21ded97` over `ai_ceo_layer1_frontend_e2e` at revision `070e4968a497`, `as_of 2026-09-18`. The
  backend paths were clean.
- The three payload hashes and the pinned fingerprint equal §3. CUST-007's narrative equals the golden brief byte
  for byte.

**Not run in F1.**
- F2's end-to-end scenario, the visual tests and the performance record. Their surfaces do not exist yet.

**Next:** F2, which starts only on the owner's instruction.

### F2 — Classic view: CLOSED 2026-09-28

**What F2 produced.**
- **Domain (`src/domain/`, §7).** Pure modules for bands, snapshots and the inbox, the brief view,
  cited text, the decision chain and request, what a failed write means (§7.6), money, timestamps,
  the roster and rooms, and evidence records. `asOf.ts` is F1's.
- **API layer.** Query options for every route of §6.3 that F2 reads. Each result carries the calls
  behind it, for **Show the API call**, and the §6.7 invalidations are functions. One addition,
  `countAssessments`, reads a total with a single-row `GET /risk/assessments`. The client now
  exports its error-envelope schema, so the contract tests can parse recorded refusals.
- **Pages.** Classic view is complete:
  - `/classic`: the health report, the About panel and the staff directory;
  - `/classic/inbox`: the CEO inbox;
  - `/classic/briefs/<brief-id>`: every §7.3 section, the decision panel and the chain;
  - `/classic/agents/<agent-id>`: each agent of §9.2, including one per configured source.
  - Every panel has all four states and **Show the API call**. Evidence links open the cited
    record or the document text with the span marked, in dialogs that trap and return focus.
- **HUD.** **Run assessment**, with the outcome of the session's latest run under the top bar.
- **Session state** (zustand, never persisted): the latest run, the selected brief, and the briefs
  refused for `STORED_PAYLOAD_MISMATCH`. The decider's name is kept in `aiceohq.actorName` (§11).
- **Tests.** Five unit files, five component files, contract additions and the end-to-end
  scenario `tests/e2e/classic.spec.ts`, with six screenshot baselines.
- **Fixtures.** Re-recorded at `1cf8e55` (the F1 commit), with two new files:
  - `decision-flow.json`: on the first brief, recorded after everything else because it writes.
    It holds an approval; refusals for `SUPERSEDES_REQUIRED`, `REQUEST_HASH_MISMATCH`,
    `PREDECESSOR_NOT_ON_BRIEF` and `INVALID_REQUEST`; a rejection that supersedes the approval;
    `PREDECESSOR_NOT_HEAD`; the chain of two; and three 404s. MSW serves it only to tests that
    ask for it, because it describes a later state of the database.
  - `auto-run.json`: an Auto run (201), the date it resolved to (`2026-08-27`), that snapshot, and
    `SCOPE_UNRESOLVED`. The recorder obtains that refusal by asking Auto for `rest_mock`, which the
    isolated database never ingests. The app itself sends only `csv_demo`.
  - Every recorded brief body is in `briefs.json`: the three at `2026-09-18`, then the Auto
    snapshot's four.
- `Makefile`: `frontend-e2e` (§4.1). It is added to `.PHONY`, listed by `make help` and given a
  recipe. No existing line changed.
- `frontend/README.md`: the F2 status, the Classic addresses and the visual-test rule.

**Owner rulings.** The owner approved staging and committing F2 on 2026-09-28. No other ruling was
needed. One R-F-3 stop arose and was resolved inside ruling 3 of F1:
- **The finding.** The first recording put brief bodies into `decision-flow.json` (the decided
  brief) and `auto-run.json` (the Auto snapshot's briefs). `scan_text` then reported 6 findings,
  all with fingerprint `f98ec4491f30`, in those two files. The allow-list entry names
  `briefs.json` only.
- **The resolution.** The recorder now writes every brief body into `briefs.json` and nowhere
  else, and it no longer records the decided brief. `scripts/secret_scan.py` is unchanged.
- **The check.** Without the allow-list, `briefs.json` now has 6 findings, all `f98ec4491f30`: three
  each from CUST-007's briefs at `2026-09-18` and at `2026-08-27`. A contract test asserts that no
  other fixture file holds a brief body.

**Choices made in F2 (PROPOSED; each stands unless replaced).**
- **The copy.** Classic view replays nothing, so it shows neither of F4's replay banners (Appendix
  A). A run that answers 200 reads "Already assessed at <date>: all <n> results existed, so nothing
  was written." The §7.6 defect message reads "The API refused this decision because this page sent
  an inconsistent request. Nothing was written."
- **Auto in the inbox.** Under Auto, the inbox shows the snapshot of this session's Auto run. Before
  any Auto run it says how to get one. The frontend does not work out the latest ticket's date
  itself, because that would duplicate `app/intelligence/scope.py`.
- **Unknown outcomes (R-F-7).**
  - **Run assessment.** Before the POST, the page counts the assessments at the run's `as_of`, or at
    every date for Auto. After an unknown outcome it counts again: the run landed only if the total
    grew. The POST is idempotent, so the retry offered otherwise cannot write twice. If the count
    before the POST fails, nothing is sent.
  - **A decision.** The page re-reads the chain. The decision landed only if an entry matches the
    sent actor, decision, note, hash and predecessor. If another decision moved the head instead,
    the page shows the §7.6 stale-head message.
  - If a re-read fails, the page offers **Check again**, never a retry.
- **The inbox renders only when every brief of the snapshot has loaded.** Partially loaded data is
  never rendered.
- **The selected customer (§9.2)** is the brief last opened in this session, while it is in the
  inbox shown; otherwise it is the inbox's first row.
- **Connector panels** list the source's 10 most recent runs; each run's errors load on request.
- **Money and probability.** A deal's `probability` is shown as the payload states it
  (`probability 90`); `src/` adds no percent sign (D-F-2). The API's own rationale and narrative
  text is shown verbatim, and it states a deal probability as "90.00%" and a threshold as "80%".
  Those strings come from the backend. They are not a risk score, and no guard can apply to them.
- **The narrative block** grows with the page rather than scrolling inside itself, because axe
  reports an internally scrolling `pre` as `scrollable-region-focusable` (serious).
- **The end-to-end environment** is fixed at a 1280×800 viewport, the UTC time zone, the `en-GB`
  locale and the light scheme. The six screenshots are the overview, the inbox, CUST-007's brief,
  and the MEMORY, RECONCILER_AGENT and CSV_DEMO_AGENT panels. They mask only the overview's request
  id and the connector's timestamps.
- **New tests beyond the spec's minimum.** Contract tests assert that the decision flow holds every
  refusal kind, and that no fixture file but `briefs.json` holds a brief body. Unit tests check that
  every S1–S15 line, derivation, quote and money line equals its golden-brief counterpart.

**The gate (§13).**
1. **Frontend.**
   - `tsc` reports 0 on both projects, ESLint 0 errors and 0 warnings, and Prettier is clean.
   - **Vitest:** 381 passed, 0 failed, 0 skipped. By layer: unit 142, component 116, contract 67,
     guards 34, tools 22.
   - **Coverage:** `src/api/**` and `src/domain/**` are at 100% of lines, branches, functions and
     statements. All of `src/` is 98.1% of statements (1125 of 1147) and 93.4% of branches.
   - **Playwright:** 20 passed, 0 skipped, on two consecutive runs over a recreated database. The
     17 new tests cover:
     - the six screenshots;
     - CUST-007 pinned `CRITICAL · EXECUTIVE`, with CUST-025 and CUST-036 following;
     - Run assessment at `2026-09-18` answering 200;
     - the golden narrative and quotes, and a document span dialog;
     - approve, then reject with supersede, with the chain and `decision_status` checked through
       the API;
     - 409 `DECISION_CONFLICT` (`PREDECESSOR_NOT_HEAD`), provoked by a decision recorded directly
       through the API;
     - 409 `PAYLOAD_HASH_CONFLICT` (`REQUEST_HASH_MISMATCH`), provoked by rewriting the request's
       hash in the browser;
     - an empty chain;
     - an unknown outcome that landed, and one that did not;
     - Auto (201 at `2026-08-27`, four briefs);
     - an API that is down, and its recovery.
   - **axe:** 0 serious and 0 critical on `/classic`, `/classic/inbox`, CUST-007's brief, all 11
     agent pages and an open evidence dialog.
   - **Bundle:** initial JavaScript is 181.0 KB gzip of the 250 KB budget, and CSS is 18.2 KB gzip.
     Vite warns that the one chunk is over 500 KB minified (604 KB raw). The budget is measured in
     gzip, and F3's lazy world chunk splits the bundle anyway.
2. **The backend.** `git diff --stat 733b19b -- app config migrations alembic.ini data tests scripts
   Dockerfile docker-compose.yml docker .env.example pyproject.toml` lists only
   `scripts/secret_scan.py | 2 ++` (F1, ruling 3). F2 changes nothing under a frozen path. The full
   backend suite is not run in F2 (§13 runs it at F1, F5 and F6).
3. **The four repository-scanning backend test files** pass on the staged tree: 256 passed and
   0 failed, with the 2 known warnings. They ran in the repository `.venv`, with the caches and the
   coverage file kept out of the repository.
4. **The secret scan.**
   - `scan_text` over all 76 new or changed files reports 0 findings: 70 text files and 6 PNG
     baselines skipped as binary.
   - **Staged `make secret-scan`:** 496 files scanned, 9 binary files skipped (505 tracked, which is
     456 + 49 new) and 0 findings.
5. **Anchors.** The golden sha, the one migration head `070e4968a497` and the strategy diff sha all
   equal §3.
6. **`git status`** shows only `frontend/`, `Makefile`, this document and the unstaged strategy
   document.

**AC-F-17.**
- The development database's `GET /risk/assessments` and `GET /entities/customers` responses are
  byte-identical before and after F2's gate (52 customers; 1 assessment, at `as_of 2026-09-27`).
- F2 used `<database>_frontend_e2e`, for the recorder and the end-to-end tests, and
  `<database>_frontend`, for a manual check through `make frontend-backend`. It used nothing else.

**Not run in F2.**
- The performance record, the office screenshots and the world-chunk network assertion (F3).

**Next:** F3, which starts only on the owner's instruction.

### F3 — The office: CLOSED 2026-09-29

**What F3 produced.**
- **The office page (`src/office/`, in the main chunk).**
  - `/`, `/?agent=<agent-id>`, `/?inbox=1` and `/brief/<brief-id>` sit under one parent route, so
    the 3D world is created once and survives moving between them.
  - The page probes for WebGL 2 before it loads the world. It holds the staff directory (a sidebar),
    the view controls, and the panels: an agent's panel and the CEO inbox as right-hand drawers, a
    brief as a large overlay. Each panel is a modal dialog that traps focus and, on close, returns
    it to its opener, or to the office after a deep link.
  - A visually hidden text twin states what the canvas draws beyond the agents: SIGNALS_AGENT's
    board and the CEO's corkboard.
- **The office's model (`useOfficeModel`).** Each agent's state comes from the requests behind its
  own panel, which TanStack Query then shares with the panel:
  - a connector: its source's health check (`unhealthy` is ERROR);
  - MEMORY: `GET /health`;
  - LINKER_AGENT, RECONCILER_AGENT and BRIEF_WRITER: the selected brief;
  - SIGNALS_AGENT, SALES_AGENT and SUPPORT_AGENT: the selected brief's assessment;
  - the CEO desk: WAITING while the shown snapshot holds a PENDING brief.

  A loading request shows the "…" bubble and a failed one ERROR, with the message and code in the
  staff directory. **No agent is ever WORKING in F3**: no request is tracked as a stage until F4's
  Director (D-F-1).
- **The world (`src/world/`, the lazy chunk).**
  - Rooms, walls, furniture and agents are built in code from primitive parts, and each shape and
    finish is drawn as one instanced mesh. Materials are toon with a 3-step gradient; one warm key
    light casts the shadows.
  - The orthographic camera (§9.8) and three's `RenderPixelatedPass`, then its `OutputPass`. Smooth
    bypasses both.
  - SIGNALS_AGENT's board is a canvas texture turned to face the camera. It draws the selected
    customer's S1–S15 and band from `GET /risk/assessments/{id}`, clipping a long value on the board
    only.
  - The CEO's tray holds one sheet per inbox row (up to 8), and the corkboard one note per decision
    on the selected brief (up to 6), stamped by the decision (§8.6).
  - Name tags with their bulb glyphs, bubbles and room signs are DOM over the canvas. The world
    projects their anchors each frame.
  - Click targets around every agent, the CEO's desk and the board. A white floor ring marks the open
    panel's agent, an amber one the evidence highlight (§8.4).
  - `?perf=1` shows the frame time and draw calls of the last 30 seconds.
- **Domain (`src/domain/`).** New pure modules, all at 100%:
  - `views.ts`: the office and Classic addresses and their twins, the remembered view, `pixel`,
    `still` and `perf`;
  - `floorPlan.ts`: rooms, walls and doors, seats, furniture and signs;
  - `officeCamera.ts`: the yaw, zoom stops and pixel sizes, fitting, snapping and panning;
  - `agentLook.ts`: states, bulbs, glyphs and glow, and readiness into state;
  - `monitor.ts`: the board; `seed.ts`: the seeds of §9.7; `perf.ts`: the record's statistics;
  - `roster.ts` gains `evidenceDesk`.
- **HUD.** **Office | Classic**, and in the office **Pixel | Smooth**. Each choice is remembered
  (`aiceohq.view`, `aiceohq.pixel`, §11). Panel links, the product name and Run assessment's inbox
  now stay in the view the reader is in.
- **Classic view** shows the WebGL notice (Appendix A) after a fallback.
- **Tooling.** `npm run perf` (`tools/perf-record.ts`) measures the record below. The bundle report
  now checks the world chunk and the world assets too.
- **Tests.** Three unit files (`views`, `office`, `world`), two component files (`office`,
  `labels`) and `tests/e2e/office.spec.ts`, with three office baselines. The smoke test now opens
  the office at `/`. The six Classic baselines were re-recorded, because the HUD gained the view
  switch.
- `frontend/README.md` and `THIRD_PARTY_NOTICES.md` describe the office. No file outside
  `frontend/` and this record changed.

**Owner rulings.** None were needed while F3 was built. On 2026-09-29, after checking the running
site, the owner approved staging and committing F3. The owner also directed how the agents move in
F4. F4's record carries that ruling.

**Choices made in F3 (PROPOSED; each stands unless replaced).**
- **Procedural furniture, not CC0 glTF files (§9.8).** §9.8 names Kenney or KayKit `.glb` models.
  Downloading them is an outward action that needs its own approval, and the world did not need
  them. The world therefore ships no model or texture file: `public/models/` does not exist, the
  world assets are 0 MB, and the notices list none. Swapping in a CC0 pack later is local to
  `src/world/kit/furniture.ts`, after that approval.
- **Labels without drei's `<Html>`.** drei renders each label in a React root of its own. Under
  React 19, unmounting those roots logged "Attempted to synchronously unmount a root while React
  was already rendering". The labels are now plain DOM in the page's tree, placed by one projection
  pass each frame. `@react-three/drei` and `@react-three/postprocessing` stay installed but are not
  imported; whether F4 needs them is F4's decision.
- **Rendering numbers.**
  - Zoom stops 1, 1.5 and 2.25, with pixel sizes of 3, 4 and 5 CSS pixels (times the device pixel
    ratio).
  - The camera target snaps to whole cells in the camera's plane.
  - PCF shadows, updated once per frame before the beauty render rather than again for the pass's
    normal render. No tone mapping, so the palette stays flat.
- **Walls.** The two outer walls on the camera's far side stand 2.4 tall, with windows. Every other
  wall is a 0.9 partition, so the floor stays in view at every yaw. Locked rooms have closed doors:
  striped barriers and a padlock.
- **Layout and input.**
  - The staff directory is a sidebar, not an overlay, so it never hides a room.
  - Panels are modal (§10). The HUD is unreachable while one is open, so closing it comes first.
  - The keys (Q and E, plus and minus, the arrows, 0) work anywhere on the office page except in a
    field or an open panel.
- **The fallback** also covers a world that throws, for example a chunk that fails to load. It keeps
  the reader in Classic view for the session.
- **The evidence highlight** lasts 10 seconds, as a pulsing amber ring, never the working glow.
- **Test infrastructure.**
  - Playwright runs the office first and then Classic, as two projects. The office writes nothing,
    and its screenshots need the database before Classic's scenario records decisions. Baselines
    keep their names.
  - Component tests get a 20-second test timeout and a 5-second `findBy`/`waitFor` limit. At F3's
    baseline, with the machine at a load average of 21, F2's own suite showed 10 timeouts under
    `npm run check`, all passing on the rerun. The change is to timing only.
  - The React Compiler's `immutability` and `refs` lint rules are off for `src/world/**` only.
    three.js objects are mutable by design, and React Three Fiber changes them in effects and frame
    callbacks.

**The baseline (§13), measured read-only before any file was created.**
- `HEAD` and `origin/main` are both `39c2fe3` (the F2 commit), 0 ahead and 0 behind. There are 505
  tracked files.
- The golden sha begins `87d1398661b0c300`, the one migration head is `070e4968a497`, and the
  strategy document's diff sha begins `94e4e5b2f65616f6`.
- **Frontend:** `vitest run` passed all 381. The first `npm run check`, at a load average of 21,
  showed 10 timeouts in F2's own tests. They all passed on the rerun (see the test-infrastructure
  choice above).
- **The development database** (read-only GETs) had 52 customers and 1 assessment, at `as_of
  2026-09-27`.

**The gate (§13).**
1. **Frontend.**
   - `tsc` reports 0 on both projects, ESLint 0 errors and 0 warnings, and Prettier is clean.
   - **Vitest:** 472 passed, 0 failed, 0 skipped. By layer: unit 196, component 153, contract 67,
     guards 34, tools 22.
   - **Coverage:** `src/api/**` and `src/domain/**` are at 100% of lines, branches, functions and
     statements (698 statements, 346 branches). All of `src/` outside `src/world/` is 98.0% of
     statements. `src/world/` is 43.1%: its part kit is 96–100% under unit tests, and its React
     Three Fiber components run only in the end-to-end tests.
   - **Playwright:** 31 passed, 0 skipped, on two consecutive runs over a recreated database. The
     11 new office tests cover:
     - the office at `?still=1` in pixel art and in smooth toon, and turned and zoomed in, each
       within 5% of its baseline, with a canvas of more than 40 colours;
     - Classic view never requesting a script beyond `index.html`'s, and the office requesting
       exactly the `Office` chunk;
     - each agent's state in its tag and in the directory, and the locked rooms' signs;
     - SIGNALS_AGENT's board against CUST-007's assessment, read from the API directly;
     - a panel opened from the directory with Enter, focus trapped and returned;
     - panels opened by a name tag, by a click on MEMORY's body and on the CEO's desk;
     - the inbox, a brief over the office, and the evidence highlight;
     - the view switch, the remembered Classic choice, and the way back;
     - a device without WebGL, sent to the Classic twin with the notice and no world chunk;
     - a WebGL context lost once and survived, then lost again, falling back.
   - **axe:** 0 serious and 0 critical on the office with the MEMORY drawer, with the CEO inbox, and
     with CUST-007's brief, as well as on every Classic page as before.
   - **Bundle:** initial JavaScript is 189.6 KB gzip of the 250 KB budget (F2: 181.0). The world
     chunk is 247.2 KB gzip of 900 KB, and the world assets are 0 of 5 MB. CSS is 19.1 KB gzip.
   - **Performance** (`npm run perf`: the static scene, `?perf=1`, 1920×1080 at device pixel ratio
     1, 30 seconds per mode after a 3-second warm-up). The reference machine is the owner's
     MacBook Air (15-inch, M2, 2023; `Mac14,15`, 8 GB), running the installed Chrome 153 headless
     on ANGLE Metal (Apple M2).

     | Mode | Frames | Median | p95 | Draw calls | Triangles |
     |---|---|---|---|---|---|
     | Pixel | 1799 | 16.70 ms | 17.60 ms | 62 | 101,814 |
     | Smooth | 1800 | 16.70 ms | 17.40 ms | 37 | 65,478 |

     Both are within §9.10 (median ≤ 16.7 ms, p95 ≤ 25 ms, ≤ 150 draw calls). The median is the
     display's 60 Hz frame. F4 measures again with every agent moving.
2. **The backend.** `git diff --stat 733b19b -- app config migrations alembic.ini data tests scripts
   Dockerfile docker-compose.yml docker .env.example pyproject.toml` lists only
   `scripts/secret_scan.py | 2 ++` (F1, ruling 3). F3 changes nothing under a frozen path, and
   nothing outside `frontend/` but this record. The full backend suite is not run in F3 (§13 runs
   it at F1, F5 and F6).
3. **The four repository-scanning backend test files** pass on the staged tree: 256 passed and
   0 failed, with the 2 known warnings. They ran in the repository `.venv`, with the caches and the
   coverage file kept out of the repository.
4. **The secret scan.** `scan_text` over every new or changed path reports 0 findings: 70 text
   files (this record included), 9 PNG baselines skipped as binary, and one deleted file
   (`src/app/HomeRedirect.tsx`, whose job the office page took over).
   - **Staged `make secret-scan`:** 541 files scanned, 12 binary files skipped (553 tracked, which
     is 505 + 49 new − 1 deleted) and 0 findings.
5. **Anchors.** The golden sha, the one migration head `070e4968a497` and the strategy diff sha all
   equal §3.
6. **`git status`** shows only `frontend/`, this document and the unstaged strategy document.

**AC-F-17.**
- The development database's `GET /risk/assessments` and `GET /entities/customers` responses are
  byte-identical before and after F3's gate (52 customers; 1 assessment, at `as_of 2026-09-27`).
- F3 used `<database>_frontend_e2e`, for the end-to-end tests and the performance record, and
  `<database>_frontend`, for a manual check through `npm run backend`. It used nothing else.

**Known in F3, carried forward.**
- React Three Fiber logs three's own deprecation warning for `THREE.Clock` once per load. It comes
  from the library, not from this code.
- The office's baselines follow Chrome and the GPU, like Classic's (F1, ruling 2).

**Not run in F3.**
- The full backend suite (F5, F6).
- Anything that moves: walks, episodes, replays, the decision stamp and sound (F4).

**Next:** F4, which starts only on the owner's instruction.

### F4 — Life: CLOSED 2026-09-29

**The owner's ruling on motion (DIRECTED 2026-09-29).** After checking F3's running site the owner
directed how the agents move, and F4 is built on it:
- an agent at work is at its desk;
- an agent handing something to another agent **walks to that agent**;
- an agent not at work is in the **Break Area**, and the Break Area gets more to do;
- agents work only during a real run and a bannered replay; the HUD gets a **Replay** button, and
  nothing replays on its own (a finished run replays its own results).

The ruling refines §9.4–§9.7 without replacing them: WORKING and HANDOFF still occur only during an
in-flight tracked request or a bannered replay (D-F-1, AC-F-2), and ambient walks still go only
between desks and Break Area places (§9.7).

**What F4 produced.**
- **Walking (`src/domain/walkGrid.ts`, `walker.ts`, `layout.ts`).** A walk grid of 0.25-unit cells
  cut from the floor plan: walls block except at open doors, locked doors stay shut, and furniture
  blocks its footprint grown by an agent's reach. A\* over eight neighbours, never cutting a blocked
  corner, then pulled tight. Only the largest free region counts as open floor, so no walk ends in a
  pocket shut in by furniture, or in a locked room. An agent walks at 4 units a second and hurries,
  up to 1.8 times that, when a cue needs it somewhere by a given moment.
- **The Break Area (`breakArea.ts`, `floorPlan.ts`, `kit/furniture.ts`).** Eighteen places, one
  agent each: the coffee machine, the water cooler, the fridge, the arcade cabinet, the vending
  machine, both ends of the ping-pong table, the window, three sofa seats, an armchair, three bean
  bags, two café chairs, and MEMORY's charging pad. New furniture, all procedural: a fridge, an
  arcade cabinet, a ping-pong table, a TV console, a lounge rug, an armchair, bean bags, a café table
  and chairs, a pizza box and a charging pad. MEMORY is a robot: it takes standing places only.
- **Ambient life (`ambient.ts`).** An idle agent takes a free place, stays 7 to 16 seconds after
  arriving, then walks to another. Choices come from a generator seeded by the agent's id, so the
  same office always starts the same way. `?still=1` keeps every agent at its first place.
- **Episodes (`episodes.ts`, §9.5).** The assessment episode's eight stages and the ingestion
  episode, each step with `source: { route, path }`, each emitted only when its data exists.
- **The Director (`director.ts`).** A pure timeline per show:
  - **live** while a POST is in flight: the stage agents walk to their desks and light up in stage
    order, captioned `ASSESSING…` or `INGESTING…`;
  - **hold** between the POST's answer and its replay: at their desks, idle;
  - **replay** under the banner: everyone in the episode first walks to their desk; each stage
    works at its desk with its caption; **a finished stage walks its result to the next stage's
    agents under a cyan arrow labelled with its own caption**; the analysts meet at the debate
    table for a conflict under a red arrow; the RECONCILER rules; BRIEF_WRITER carries the briefs
    to the CEO's tray, one sheet per inbox row; everyone cheers; the show ends and they walk back to
    the Break Area.
- **The world (`src/world/`).** `Crowd.tsx` draws every body as instanced parts rewritten each
  frame, with limbs that swing (walk, type, work, present, play, sip, cheer, carry), the working
  glow's hull, the bulb, and a carried sheet. Name tags, bubbles, click targets and the open panel's
  ring follow each body. `Arrows.tsx` draws the neon arcs, `Stamp.tsx` the decision stamp and the
  approval's confetti. An idle agent in the Break Area wears a smaller tag.
- **The page.** The Director store (`src/state/director.ts`); the replay banner, which ends the
  replay when dismissed; the HUD's **Replay** and **Sound** (office only); **Run ingestion** in a
  connector's panel (R-F-6); the stamp after a recorded decision; Web Audio clicks and a stamp's
  thump when sound is on (§9.12).
  - **Run assessment in the office** no longer opens the inbox drawer over the world: the run
    replays, and its status line links **Show the inbox**. Classic view opens the inbox as before.
  - **Run ingestion** is offered only while the source's health check says `healthy`. An answer
    that never arrived, or a 500, is an unknown outcome: the panel re-reads the source's runs
    before it offers a retry (R-F-7).
- **Tests.** `tests/unit/life.test.ts` (47), `tests/component/life.test.tsx` (19), additions to
  `world.test.ts` and `queries.test.ts`, and `tests/e2e/life.spec.ts`, a third Playwright project
  that runs after Classic. `npm run perf` now measures during a replay (see below).
- **Fixtures.** `tools/record-fixtures.ts` also records `POST /api/v1/ingestion/runs` for
  `csv_demo`, last, into `ingestion-run.json` (a `NOOP` run). Every fixture was re-recorded; apart
  from the new file, only ids, timestamps and request ids changed.
- **Docs.** `frontend/README.md` describes the office's life, and `THIRD_PARTY_NOTICES.md` now says
  the walk grid was written here, not adapted. No file outside `frontend/` and this record changed,
  and F4 adds no dependency.

**Owner rulings.** The motion ruling above. No other ruling was needed while F4 was built.

**Choices made in F4 (PROPOSED; each stands unless replaced).**
- **The walk grid is written here, not vendored from Claw3D (§14's F4 row, §9.9).** Fetching
  Claw3D's module is an outward action that needs its own approval, and a grid A\* is small. So
  `src/vendor/` still does not exist and the notices list no code.
- **drei and postprocessing stay unused.** `@react-three/drei`, `@react-three/postprocessing` and
  `postprocessing` are installed but not imported. Removing them is a dependency change, left for
  the owner.
- **Motion numbers.** Walk speed 4 units a second, hurrying up to 1.8 times that; a Break Area stay
  of 7 to 16 seconds. One frame walks at most 0.5 seconds' worth, so a long pause (a hidden tab,
  where Chrome slows animation frames to about one a second) resumes as a short step, not a jump
  across the office.
- **Nobody walks under `still` or reduced motion.** Agents are placed where the timeline puts them
  at once, limbs keep their pose without swinging, and no confetti flies (§9.11). Under `perf=1`
  an idle agent moves on within 0.3 seconds of arriving, so the performance record has every agent
  moving.
- **Test infrastructure.**
  - Playwright gains a third project, `life`, which runs after Classic: it records a decision and
    an ingestion run, which Classic's screenshots must not see.
  - The component setup ends any show and clears the stamp between tests, and restores the
    Director's clock.
  - `npm run perf` starts a Replay after the warm-up and fails if the replay ends before the 30
    seconds do.
- **The Classic baseline `agent-csv-demo`** was re-recorded: CSV_DEMO_AGENT's panel gained the Run
  ingestion card. The other five Classic baselines are unchanged. The three office baselines were
  re-recorded, because idle agents now stand in the Break Area rather than at their desks.

**The baseline (§13), measured read-only at F4's start.**
- `HEAD` is `2b43522` (the F3 commit) and `origin/main` is `39c2fe3`, so local `main` is 1 ahead.
  There are 553 tracked files.
- **The development database** (read-only GETs): 52 customers and 1 assessment, at `as_of
  2026-09-27`. Both responses were saved for AC-F-17.
- Every fixture was saved before re-recording, to compare the new recording against.

**The gate (§13).**
1. **Frontend.**
   - `tsc` reports 0 on both projects, ESLint 0 errors and 0 warnings, and Prettier is clean.
   - **Vitest:** 547 passed, 0 failed, 0 skipped. By layer: unit 252, component 171, contract 68,
     guards 34, tools 22.
   - **Coverage:** `src/api/**` and `src/domain/**` are at 100% of lines, branches, functions and
     statements (1311 statements, 598 branches). All of `src/` outside `src/world/` is 97.1% of
     statements and 98.0% of lines; `src/lib/sound.ts` is the gap, because jsdom has no Web Audio.
     `src/world/` is 33.7%: its part kit is 98.9% under unit tests, and its React Three Fiber
     components run only in the end-to-end tests.
   - **Playwright:** 39 passed, 0 skipped, on two consecutive runs over a recreated database. The
     8 new life tests cover:
     - every agent not at work in the Break Area with a smaller tag, and strolling on;
     - Run assessment at `2026-09-18`: the "already assessed" banner, the agents walking to their
       desks, MEMORY's snapshot handed to LINKER_AGENT under a cyan arrow, the analysts' conflict
       over DEAL-001 under a red arrow, the RECONCILER's ruling, the tray filling to 3, and
       everyone back in the Break Area when the show ends;
     - approving CUST-007 from the office: the stamp, the chain one longer, and the corkboard's
       new note;
     - Replay under its banner, ended by dismissing it, and placed at once under reduced motion;
     - Run ingestion from CSV_DEMO_AGENT's panel (a `NOOP` run), handed to MEMORY in the replay,
       and the button disabled for the unhealthy `odoo_mock`.
   - **axe:** 0 serious and 0 critical on the replay banner over the office and on the ingestion
     outcome in CSV_DEMO_AGENT's drawer, as well as on every page checked before.
   - **Bundle:** initial JavaScript is 198.7 KB gzip of the 250 KB budget (F3: 189.6). The world
     chunk is 253.0 KB gzip of 900 KB (F3: 247.2), and the world assets are 0 of 5 MB. CSS is
     19.5 KB gzip.
   - **Performance** (`npm run perf`: every agent moving, measured for 30 seconds during a Replay,
     `?perf=1`, 1920×1080 at device pixel ratio 1, after a 3-second warm-up). The reference machine
     is F3's: the owner's MacBook Air (`Mac14,15`, M2, 8 GB), running the installed Chrome 153
     headless on ANGLE Metal (Apple M2).

     | Mode | Frames | Median | p95 | Draw calls (max) | Triangles (max) |
     |---|---|---|---|---|---|
     | Pixel | 1795 | 16.70 ms | 18.10 ms | 74 | 118,186 |
     | Smooth | 1797 | 16.70 ms | 18.20 ms | 43 | 75,518 |

     Both are within §9.10 (median ≤ 16.7 ms, p95 ≤ 25 ms, ≤ 150 draw calls). Against F3's static
     scene, p95 rose by 0.5 and 0.8 ms and the draw calls by 12 and 6.
2. **The backend.** `git diff --stat 733b19b -- app config migrations alembic.ini data tests scripts
   Dockerfile docker-compose.yml docker .env.example pyproject.toml` lists only
   `scripts/secret_scan.py | 2 ++` (F1, ruling 3). F4 changes nothing under a frozen path. The full
   backend suite is not run in F4 (§13 runs it at F1, F5 and F6).
3. **The four repository-scanning backend test files** pass on the staged tree: 256 passed and
   0 failed, with the 2 known warnings (the working tree gave the same). They ran in the repository
   `.venv`, with the caches and the coverage file kept out of the repository.
4. **The secret scan.** `scan_text` over every new or changed path reports 0 findings: 67 text
   files (this record included) and 4 PNG baselines skipped as binary. Nothing was deleted.
   - **Staged `make secret-scan`:** 564 files scanned, 12 binary files skipped (576 tracked, which
     is 553 + 23 new) and 0 findings.
5. **Anchors.** The golden sha, the one migration head `070e4968a497` and the strategy diff sha all
   equal §3.
6. **`git status`** shows only `frontend/`, this document and the unstaged strategy document.

**AC-F-17.**
- The development database's `GET /risk/assessments` and `GET /entities/customers` responses are
  byte-identical before and after F4's gate (52 customers; 1 assessment, at `as_of 2026-09-27`).
- F4 used `<database>_frontend_e2e`, for the fixtures, the end-to-end tests and the performance
  record, and `<database>_frontend`, through the `make frontend-backend` started for the owner's
  check of F3, to look at the office in a browser. It used nothing else.

**Known in F4, carried forward.**
- React Three Fiber still logs three's `THREE.Clock` deprecation once per load.
- The office's baselines follow Chrome and the GPU, like Classic's.
- The Break Area's strolls are seeded but depend on frame timing, so the end-to-end test checks
  that agents move, not where they go.

**Not run in F4.**
- The full backend suite (F5, F6).

**Next:** F5 (hosting), which starts only on the owner's instruction, with each external action
approved separately.

### F5 — Hosting: CLOSED 2026-10-01

**The hosted demo:** https://ai-ceo-hq-chi.vercel.app, the Vercel project
`yuvraj-gaykhes-projects/ai-ceo-hq` (the name `ai-ceo-hq` was taken, so Vercel added `-chi`).

**Owner rulings (2026-09-30).**
1. **F4 committed first** (`6b0e52b`), which is F5's entry condition.
2. **Deployments come from the Vercel CLI and a clean export, not from GitHub.** Each deployment
   uploads `git archive` of `HEAD` plus the phase's changed and new files, and nothing else. The
   CLI would otherwise upload a plain `.env`: it skips only `.env.local` and `.env.*.local`, the
   repository has a local `.env` with database credentials, and §4 allows no `.vercelignore`. The
   export refuses to build if any other file, or any `.env`, would be included. Nothing is pushed.
3. **Singapore.** The API's function runs in `sin1`, and Neon in AWS `ap-southeast-1`, near the
   reviewers in India.
4. **The gate runs on the production domain, not a preview URL (a departure from §14).** Vercel's
   standard Deployment Protection puts every preview and generated deployment URL behind a Vercel
   login, so Playwright and `make demo-reset` cannot reach them. The production domain is public in
   any case.
5. Each external action was approved as it came: creating the project and the first deployment;
   connecting Neon (done by the owner, who accepted Neon's terms); each production redeployment; and
   the hosted smoke test's write followed by the second reset.

**D-F-17: the Python runtime, not a container (R-F-8).** A fresh `uv` venv on CPython 3.12.13, built
from `pyproject.toml` with `.[dev]` (FastAPI 0.142.2, SQLAlchemy 2.0.54, pandas 3.0.6, pydantic
2.13.5, psycopg2-binary 2.9.13), ran the full backend suite: 6771 passed (unit 5287, contract 185,
integration 1214, e2e 85), 0 failed and 0 skipped, `app/` 100% over 7456 statements, the 2 known
warnings. There is no repository-level Python pin. Vercel's build log says "Using Python 3.12 from
pyproject.toml", so the observed runtime is the version the suite passed on. PyYAML, which `app/`
imports, reaches Vercel only through `uvicorn[standard]`'s extras.

**What F5 produced.**
- **`vercel.json`** (Vercel Services, checked against Vercel's configuration reference and its own
  Vite + FastAPI example):
  - `web`: `frontend/`, the Vite preset, and a rewrite of every path to `/index.html` inside the
    service, so deep links load the app. Built files are served before rewrites apply;
  - `api`: the repository root, the FastAPI preset, entrypoint `app.main:app`, with its function in
    `sin1` and `excludeFiles` for `tests/**`, `data/fixtures/**`, `data/quarantine/**`, `CONTEXT/**`
    and `frontend/**`;
  - top-level rewrites send `/api/(.*)`, `/docs`, `/redoc` and `/openapi.json` to `api`, and every
    other path to `web`. The API receives the original path, so `/api/v1/...` is unchanged. An
    unknown `/api` path gets the API's own 404, not the web page.
- **`make demo-reset`** (D-F-8). It needs `DEMO_DATABASE_URL`, the demo database's direct
  connection string, and `DEMO_URL`, the site, and exits 2 without either. It asks the reader to
  type `reset`; any other answer changes nothing. It then runs `.venv/bin/alembic downgrade base`
  and `upgrade head` against `DEMO_DATABASE_URL`, and `POST /api/v1/ingestion/runs` for
  `csv_demo` and `POST /api/v1/risk/assessments` at 2026-09-18 against `DEMO_URL`. It prints the
  two statuses and no credential, and it ignores `DATABASE_URL` and the `POSTGRES_*` settings.
- **`.dockerignore`** gains the line `frontend/node_modules` (D-F-16).
- **`README.md`** gains `## Frontend and demo`, after the VS-01 section: the frontend, running it
  locally, the hosted demo and its address, `make demo-reset`, and a five-minute demo. Its `bash`
  blocks hold only `make` commands (R-F-4). `frontend/README.md` lists `npm run smoke:hosted`.
- **Frontend.**
  - On the hosted site the mock sources' panels keep their real failed health check and show
    Appendix A's "This mock source runs in local mode only." Before F5 no surface rendered it.
    `isMockSource` (`src/domain/roster.ts`) knows the mocks by the backend's own names (`odoo_mock`,
    `rest_mock`). `src/lib/hosting.ts` reads `VITE_VERCEL_ENV`, which Vercel sets while it builds
    the Vite preset and a local build leaves unset. It carries no secret (§6.1).
  - **The performance budget's comparison** now rounds frame times to 0.01 ms first. Frame times
    are differences of timestamps, so a 16.7 ms frame can come out as `16.700000000000728`. That
    made F5's first record print a median of 16.70 ms and still say "OVER budget". A unit test
    covers both sides of the edge.
- **The hosted smoke test.** `playwright.hosted.config.ts` and `tests/hosted/hosted.spec.ts`, run by
  `npm run smoke:hosted` against `AICEOHQ_HOSTED_URL`, with no global setup. Three `@clean` tests
  only read:
  - one origin without CORS: health, `/openapi.json`, `/docs`, a deep link and the office;
  - the clean dataset: 50 assessments, the three briefs with §3's payload hashes and the pinned
    fingerprint, CUST-007's golden narrative, and no decision;
  - the inbox, and the mock sources' caption.

  One `@write` test records an approval of CUST-007. The config also accepts `vercel dev` on a
  loopback port, to rehearse.
- **Tests.** `tests/component/hosted.test.tsx` (3), and additions to `tests/unit/roster.test.ts` and
  `tests/unit/office.test.ts`.

**Choices made in F5 (PROPOSED; each stands unless replaced).**
- **`demo-reset` ingests and assesses through the hosted API.** Plan §8.2 had the owner's machine
  run the ingestion. Here the ingestion runs next to the database, through the existing route with
  the same defaults as `scripts/ingest_demo.py` (every entity, page size 100). The rehearsals below
  prove the result is the same: §3's payload hashes and the pinned fingerprint. Only the
  migrations run from the owner's machine.
- **The mock-source caption keys on the source's name**, because the API calls `odoo_mock` type
  `mock` and `rest_mock` type `rest`.

**Rehearsals, before any outward action.**
- `make demo-reset` against the isolated `<database>_frontend`, with `DEMO_URL` a local API:
  - an answer other than `reset`: nothing changed;
  - twice after recording a decision, and once from an empty database: each finished in about
    3 seconds with 50 assessments, §3's three payload hashes, the pinned fingerprint, and empty
    chains.
- `vercel dev -L` on a clean export, pointed at `<database>_frontend`, routed exactly as above.
  Without `DATABASE_URL` the application's defaults would name the development database, so a
  wrapper set it and no request was sent before it did. Through it: the hosted smoke 4/4, then
  `demo-reset`, then `@clean` 3/3. Under `vercel dev` the web service's rewrite also catches
  Vite's development modules, so the rehearsal copy left it out. The rewrite itself is proven on
  the deployment.

**The deployment.**
- Each deployment uploaded 582 files: `git archive 6b0e52b` plus 14 F5 files, with no `.env` and no
  ignored file. The build ran `npm ci` and `npm run build` for `web` (the bundle report within
  budget) and `uv` for `api`.
- **Vercel made the first deployment production**, although it was asked for as a preview:
  a new project's first deployment always is. It served the site with no database until Neon was
  connected. Two more production deployments followed: one to pick up `DATABASE_URL`, and one after
  the password reset below. Standard Deployment Protection (Vercel Authentication) covers the
  preview and generated URLs.
- Responses carry `x-vercel-id: bom1::sin1`: the edge in Mumbai, the function in Singapore.
- **Neon** was connected by the owner through the Vercel Marketplace: the Free plan,
  `ap-southeast-1`, Production and Preview. Its variables are sensitive, so no command line can
  read them back (`vercel env run` and `pull` receive empty values). `make demo-reset` therefore
  takes the connection string from the owner's own clipboard, in the owner's terminal.
- **The database password was reset once.** The owner pasted a connection string into the chat.
  It was not used, and the owner reset the password from Neon's Connect dialog, which pushed the
  new value to Vercel's variables; a redeployment picked it up. The string in the chat no longer
  works.
- **The rate limit.** The owner published one Vercel Firewall rule on 2026-10-01: a request whose
  path starts with `/api/` and whose method is `POST` is rate-limited per IP, in a fixed window of
  60 seconds, to 20 requests, and then answered 429. Hobby allows one such rule. It was not
  exercised, because that would have written runs into the demo database.

**The gate (§13).**
1. **Frontend.**
   - `tsc` reports 0 on both projects, ESLint 0 errors and 0 warnings, and Prettier is clean.
   - **Vitest:** 551 passed, 0 failed, 0 skipped. By layer: unit 253, component 174, contract 68,
     guards 34, tools 22. `src/api/**` and `src/domain/**` are at 100% (1313 statements, 598
     branches).
   - **Playwright:** 39 passed, 0 skipped, on two consecutive runs over a recreated database. Two
     earlier runs, at load averages of 30 to 140, each timed out once, on different tests, with no
     assertion failing (7 and 2 passed before them). They are not counted.
   - **axe:** unchanged; it runs inside the end-to-end tests.
   - **Bundle:** initial JavaScript 198.7 KB gzip, the world chunk 253.0 KB, world assets 0, CSS
     19.5 KB: the same as F4.
   - **Performance** (`npm run perf`, as F4: a Replay, every agent moving, 1920×1080, 30 seconds per
     mode, the same machine and Chrome): pixel 1795 frames, median 16.70 ms, p95 17.60 ms, 74 draw
     calls; smooth 1791 frames, median 16.70 ms, p95 17.50 ms, 43 draw calls. Both within §9.10.
2. **The backend.** The frozen-path diff against `733b19b` lists only `scripts/secret_scan.py | 2 ++`
   (F1, ruling 3). **The full backend suite equals the baseline** in the repository `.venv`
   (Python 3.11.5): 6771 passed (unit 5287, contract 185, integration 1214, e2e 85), 0 failed and
   0 skipped, `app/` 100% over 7456 statements, the 2 known warnings. The fresh 3.12 venv gave the
   same (above).
3. **The four repository-scanning backend test files** pass on the staged tree, with the new
   `Makefile`, `README.md` and `.dockerignore`: 256 passed, the 2 known warnings (the working
   tree gave the same).
4. **The secret scan.** `scan_text` over every new or changed path reports 0 findings: 18 text
   files, this record included. **Staged `make secret-scan`:** 570 files scanned, 12 binary files
   skipped (582 tracked, which is 576 + 6 new) and 0 findings.
5. **Anchors.** The golden sha, the one migration head `070e4968a497` and the strategy diff sha all
   equal §3.
6. **`git status`** shows only F5's allowed paths, this document, the unstaged strategy document
   and an untracked `.claude/launch.json`. That file, a preview launch configuration, was created
   by another session on 2026-09-30. It is not F5's and is never staged.

**The hosted gate (AC-F-10).** `AICEOHQ_HOSTED_URL=https://ai-ceo-hq-chi.vercel.app`, on
2026-10-01:
1. `make demo-reset` on the empty Neon database: both `HTTP 201`;
2. `@clean`: 3 passed;
3. the whole smoke test: 4 passed, and CUST-007's chain held one `APPROVED` by "Hosted smoke";
4. `make demo-reset` again: both `HTTP 201`;
5. `@clean`: 3 passed. The site is clean again.

The site is same-origin with no CORS header, and `demo-reset` is proven twice on Neon.

**AC-F-17.**
- The development database's `GET /risk/assessments` and `GET /entities/customers` responses are
  byte-identical before and after F5 (52 customers; 1 assessment, at `as_of 2026-09-27`).
- F5 used `<database>_frontend` (the rehearsals and `vercel dev`), `<database>_frontend_e2e`
  (Playwright and the performance record), the backend suite's own `_test` database, and the
  hosted Neon database. It used nothing else.

**Known in F5, carried forward.**
- The hosted site has no authentication (§16): anyone with the link can record a decision. Reset
  before each review.
- Vercel Services is in beta (§16). The deployment used no fallback.
- Resetting the hosted database needs the owner's connection string, because the integration's
  variables are sensitive.
- The Neon integration also adds `VITE_NEON_AUTH_URL`. Nothing references it, and the built bundle
  contains no Neon address.
- **The live site predates four of F5's edits:** the budget comparison's fix, its unit test, the
  two READMEs' last lines and this record. Only the fix reaches a bundle: the lazy world chunk's
  `?perf=1` overlay, which can still say "OVER" on a 16.70 ms median. The owner approved a
  production deployment from the F5 commit itself, which follows the commit and brings the site
  level with the repository.

**Next:** F6 (polish), which starts only on the owner's instruction.

### F6 — Polish: CLOSED 2026-10-01

**Owner rulings (2026-10-01).**
1. **The tour opens once per browser, on the first visit, and the HUD's "?" opens it again.** Its
   flag is a new browser-storage key, `aiceohq.tour`, kept like §11's others: a convenience, inside
   try/catch. §11's list gains it.
2. **F6 may edit the README's `## Frontend and demo` section, and only that section** (§4 allowed
   README edits in F5 only). R-F-4 still applies.
3. **The timed rehearsal is driven here and watched by the owner,** on the production domain. It
   records one approval, so the owner resets the demo database afterwards.
4. **The unused `@react-three/drei`, `@react-three/postprocessing` and `postprocessing` are
   removed** (F4 had left them for the owner). §5's runtime list loses them.
5. Each outward action was approved as it came: one production deployment of F6's working tree,
   the rehearsal and its one approval, the reset, and (after the commit) a production deployment
   from the F6 commit itself.
6. **The backend suite's intermittent third warning passes the gate and is carried forward**
   (below, under "Known in F6"). The gate counts the run that equals the baseline; the record keeps
   both runs.

**What F6 produced.**
- **The tour (`src/domain/tour.ts`, `src/state/tour.ts`, `src/hud/Tour.tsx`).** Three steps, each
  pointing at a part of the page that both views have:
  1. **Meet the agents** rings the staff directory;
  2. **Watch a run** rings Run assessment (and, in the office, Replay);
  3. **Decide as the CEO** rings the CEO inbox entry.

  It is a modal dialog with Back, Next and "Start exploring", a close button, and Escape. The
  ringed part is lifted above the dimmed page (`data-tour-spot`, styled in the theme; its pulse
  stops under reduced motion). It opens on arrival at either view's home, never on a deep link, and
  closing it by any means marks it seen. The HUD's **Tour** button (a "?" icon and the word) opens
  it at step 1 and gets the focus back when it closes.
- **Small screens (`src/lib/viewport.ts`).** The office needs a window at least 768 pixels wide
  (`min-width: 768px`, followed live). Narrower, every office address goes to its Classic twin,
  the Classic layout says why, and the HUD's view switch offers Classic only (Office is shown
  disabled, with its reason for screen readers). A window narrowed while in the office leaves it
  the same way, and the world chunk is never requested. Two tables that were wider than a
  375-pixel phone (the brief's escalation edges and **Show the API call**) now wrap their long
  identifiers, so no Classic page scrolls sideways.
- **Art (`src/states/art.tsx`).** Six pixel pictures drawn in code, as rows of palette letters
  rendered to SVG rectangles, with no image file and no request: an agent, a desk, an in-tray, a
  corkboard, a filing cabinet and a stamp. The outline takes the text colour, so the art follows
  the light and dark schemes, and every picture is hidden from assistive technology.
  - **Empty states:** the inbox with no assessment or no brief (the tray, also in the agent panels
    that need a selected brief), the empty decision chain (the corkboard), MEMORY with no records
    (the cabinet), a brief or an office agent that is not there (the desk), and Classic's
    not-found page (the agent). Smaller empty states keep F2's icon.
  - **Loading:** while the world chunk downloads, the office shows an agent beside a desk and
    "Setting up the office", with the same status for screen readers as before.
  - **The tour** shows the agent, the desk and the stamp beside its three steps.
- **The copy review.** Every literal in `src/` was searched for claims the system does not make
  ("AI", "intelligent", "smart", "learn", "predict", "probability", "model", "automatic",
  "autonomous", "decides" and the like). Nothing needed a change: "AI" occurs only in the product
  name (D-F-13), "language model" only in the About line that denies one, "probability" only in
  the band legend's denial and as the deals' own CRM field in the evidence, and "automatically"
  only in comments about POSTs never being retried. The tour's copy was written under the same
  rule, and a unit test holds it to it.
- **The performance pass.**
  - The three packages above are gone: 37 entries leave `package-lock.json` (3 direct, 34 that only
    they pulled in). The bundles do not change, because nothing imported them.
  - The measurements are below, under the gate. The tour and the art cost 2.3 KB gzip of initial
    JavaScript. The world chunk and the frame times are unchanged.
  - **The hosted site** was measured with read-only requests. The API's first request after a quiet
    spell took 3.9 seconds (the function starting); later ones took 0.28 to 0.37 seconds, and the
    assessment list 0.9 seconds. The README's demo now says to open the site a minute or two before
    presenting. Hashed assets are served `cache-control: public, max-age=0, must-revalidate`, so a
    return visit revalidates them (Vercel's edge answers from its cache). Marking `/assets/` as
    immutable would need `headers` in `vercel.json`, which §4 does not open in F6; it is carried
    forward, not changed.
- **Docs.** The README's `## Frontend and demo` section: before a review, reset and warm the site;
  step 1 now meets the tour; the rehearsal's time; a phone opens in Classic view. `frontend/README.md`: the F6 status, a
  section on the tour and small screens, and the tests.
- **Tests.**
  - `tests/unit/polish.test.ts` (14): the tour's steps, its first-visit rule and its bounds; its
    copy states no model, no score and no execution, and repeats no Appendix A string; every
    picture is a rectangle in the palette.
  - `tests/component/polish.test.tsx` (15): the tour's three steps and rings in Classic view and in
    the office, no tour on a deep link or for a returning reader, the HUD's Tour, Escape and focus,
    storage that refuses writes; a narrow window's redirect without the world, the view switch, a
    window narrowed and widened live, the WebGL notice winning over the narrow one; each picture
    on its empty state, and the loading art.
  - `tests/e2e/polish.spec.ts` (7), run with the office project because it writes nothing: the tour
    over the real office, with axe; no tour on a deep link; a phone sent from
    `/?agent=linker` to `/classic/agents/linker` without the world chunk; all 13 Classic pages at
    375 × 812 with every **Show the API call** open, no sideways scroll and axe clean; the phone
    inbox's screenshot; the tour on a phone; and 768 pixels getting the office, 767 Classic view.
  - Every end-to-end page now opens as a returning reader's: `tests/e2e/support.ts` exports a
    `test` whose pages mark the tour seen, unless a test sets `tourSeen: false`. The hosted smoke
    test and `npm run perf` do the same, so nothing covers the office while it is measured.

**Choices made in F6 (PROPOSED; each stands unless replaced).**
- The tour's copy and its three spots, above. Its button reads "Tour" beside the "?" icon, so the
  visible label is in its accessible name.
- The tour waits on a deep link: a reader who followed a link to a brief came for that brief.
- The narrow-window notice is new, fixed copy, not Appendix A's: "The 3D office needs a window at
  least 768 pixels wide, so this is Classic view. Every panel works the same." When WebGL has
  failed too, only the WebGL notice shows.
- Which empty states carry art: the main surfaces only, as listed. Smaller ones keep the icon.
- **The screenshot baselines were re-recorded, all nine,** because the HUD gained **Tour** on every
  page and the empty decision chain its corkboard. The differences were reviewed: those two
  changes, and the office's strollers at other places in the Break Area. `phone-inbox.png` is new.

**The rehearsal (the hosted gate).** On 2026-10-01 the F6 working tree was deployed to production
(`dpl_CEFoBLMwVBco8Hd3DJkWs7m3tZS2`; `git archive 457494b` plus F6's 46 files, 591 files in all,
no `.env`), and `@clean` passed 3/3 on it. The owner's browser pane was hidden, which slows a page's
animation frames to about one a second, so the rehearsal ran in the installed Chrome instead
(headless, 1280 × 800, a first visit), following the README's eight steps. Each step waited for what
a presenter waits for, then held 20 seconds for narration; the tour's three steps shared step 1's
20 seconds, and step 3 is narrated over the replay.

| Step | Waited for | Machine time | At |
|---|---|---|---|
| 1. Arrive | the world drawn, the API healthy, the tray at 3, the tour open | 6.8 s | 0:07 |
| 2. MEMORY | its record totals | 0.6 s | 0:28 |
| 3. Run assessment | HTTP 200 and "Already assessed: replaying recorded results" | 4.5 s | 0:53 |
| | the red arrow `CONFLICT DEAL-001`, then `CONF-001 → SUPPORT PREVAILS` | 25.5 s, 2.5 s | 1:21 |
| | the show's end, three briefs in the tray | 16.0 s | 1:37 |
| 4. The CEO's desk | CUST-007 pinned `CRITICAL · EXECUTIVE`, two WATCH | 0.6 s | 1:37 |
| 5. CUST-007's brief | every section and the decision form | 0.8 s | 1:58 |
| 6. Approve | the stamp, and ① "Demo rehearsal" in the chain | 1.2 s | 2:20 |
| 7. Classic view | the inbox and **Show the API call** | 0.8 s | 2:41 |
| 8. The locked rooms | the office drawn again | 1.0 s | 3:02 |

**The whole demo took 3 minutes 22 seconds** (201.7 s), inside the 5 minutes. The replay is 44
seconds from the API's answer to the show's end; every other wait is under 7 seconds. The same
script against the local isolated stack, without narration, took 62 seconds.

After the rehearsal, CUST-007's chain on the live site held the rehearsal's approval and one the
owner recorded while looking at the site. The owner then ran `make demo-reset`:
1. the first attempt stopped while parsing `DEMO_DATABASE_URL` (the clipboard held other text),
   before any connection, and changed nothing;
2. the second answered `HTTP 201` twice (the ingestion and the assessment at 2026-09-18);
3. `@clean` then passed 3/3: the site is clean again.

**The gate (§13).**
1. **Frontend.**
   - `tsc` reports 0 on both projects, ESLint 0 errors and 0 warnings, and Prettier is clean.
   - **Vitest:**
     580 passed, 0 failed, 0 skipped. By layer: unit 267, component 189, contract 68, guards 34,
     tools 22. `src/api/**` and `src/domain/**` are at 100% of lines, branches, functions and
     statements (1317 statements, 598 branches). All of `src/` outside `src/world/` is 97.2% of
     statements and 98.0% of lines. An earlier run, while the load average stood at 19 to 68 (the
     backend suite and the desktop's own work), timed six component tests out at 20 seconds with
     no assertion failing. It is not counted.
   - **Playwright:**
     46 passed, 0 skipped, on two consecutive runs over a recreated database (F5: 39; the 7 new
     are F6's).
   - **axe:** 0 serious and 0 critical on the tour over the office (steps 1 and 3), the tour on a
     phone, and every Classic page at 375 pixels, as well as on every page checked before.
   - **Bundle:** initial JavaScript is 201.0 KB gzip of the 250 KB budget (F5: 198.7). The world
     chunk is 253.0 KB of 900 KB (unchanged) and the world assets 0 of 5 MB. CSS is 19.8 KB gzip
     (F5: 19.5).
   - **Performance** (`npm run perf`, as F4 and F5: a Replay, every agent moving, 1920×1080, 30
     seconds per mode, the owner's MacBook Air `Mac14,15`, the installed Chrome headless on ANGLE
     Metal):

     | Mode | Frames | Median | p95 | Draw calls (max) | Triangles (max) |
     |---|---|---|---|---|---|
     | Pixel | 1793 | 16.70 ms | 17.40 ms | 74 | 118,114 |
     | Smooth | 1798 | 16.70 ms | 17.50 ms | 43 | 75,566 |

     Both are within §9.10, and level with F5 (p95 17.60 and 17.50 ms).
2. **The backend.** The frozen-path diff against `733b19b` lists only `scripts/secret_scan.py | 2 ++`
   (F1, ruling 3). F6 changes nothing under a frozen path.
   **The full backend suite** ran twice in the repository `.venv` (Python 3.11.5): each time 6771
   passed (unit 5287, contract 185, integration 1214, e2e 85), 0 failed and 0 skipped, `app/` 100%
   over 7456 statements. The second run reported the baseline's 2 warnings. The first reported 3;
   the third is intermittent and is described under "Known in F6, carried forward".
3. **The four repository-scanning backend test files:**
   256 passed and 0 failed, with the 2 known warnings, on the staged tree (the working tree gave
   the same). They ran in the repository `.venv`, with the caches and the coverage file kept out
   of the repository.
4. **The secret scan.** `scan_text` over every new or changed path reports 0 findings: 46 paths,
   36 text files and 10 PNG baselines skipped as binary, before this record was written, and 47
   paths with it.
   - **Staged `make secret-scan`:** 578 files scanned, 13 binary files skipped (591 tracked, which
     is 582 + 9 new) and 0 findings.
5. **Anchors.** The golden sha, the one migration head `070e4968a497` and the strategy diff sha all
   equal §3.
6. **`git status`** shows only F6's allowed paths (`frontend/`, the README's section, this
   document), the unstaged strategy document and the untracked `.claude/launch.json`, which is
   never staged.

**The acceptance criteria (§15), with their evidence.** Every criterion holds.

| # | Holds, because |
|---|---|
| AC-F-1 | The guards find no domain id in `src/` (§12.4); every episode step's `source` resolves in its fixture (F4's unit tests). F6's tour and art hold no data at all |
| AC-F-2 | The Director's unit tests and F4's life tests; the rehearsal saw WORKING only inside the bannered replay |
| AC-F-3 | The no-score guard over every literal in `src/`, the tour's copy test, and the component tests of the band chips |
| AC-F-4 | The inbox unit tests over the recorded lists; F2's Classic test and the rehearsal's step 4 |
| AC-F-5 | F2's Classic scenario over a clean isolated database, run twice at this gate; the rehearsal's steps 4 to 6 on the hosted site |
| AC-F-6 | The decision and run component tests for every §7.6 row, and F2's two 409 end-to-end tests |
| AC-F-7 | The office test's network assertion, and F6's: a phone never downloads the world chunk |
| AC-F-8 | The performance record above; the WebGL fallback and lost-context end-to-end tests |
| AC-F-9 | The frozen-path diff, the four repository tests and the full backend suite (item 2) |
| AC-F-10 | F5's record: one origin, no CORS, `demo-reset` proven twice; F6's `@clean` runs before and after the rehearsal |
| AC-F-11 | The notices guard: `src/vendor/` and `public/models/` do not exist, and every shadcn/ui file is listed. F6 adds no third-party code or asset |
| AC-F-12 | axe as above; the staff directory and the tour are reachable by keyboard; the tour returns the focus; reduced motion stops walking, confetti and the tour's pulse |
| AC-F-13 | `scan_text` over F6's paths, the staged `make secret-scan`, and the backend hygiene test over every tracked file |
| AC-F-14 | The component tests: every surface in all four states, F6's art included |
| AC-F-15 | The honesty guard: every Appendix A string once in `src/`, and each rendered where §8 and Appendix A say; the mock-source caption on the hosted site (`@clean`) |
| AC-F-16 | The contract tests: §3's payload hashes, the pinned fingerprint, and CUST-007's golden narrative byte for byte |
| AC-F-17 | The tooling tests (the suffix refusal and exit 2 without PostgreSQL), and the development database below |

**AC-F-17.**
- The development database's `GET /risk/assessments` and `GET /entities/customers` responses are
  byte-identical before and after F6 (52 customers; 1 assessment, at `as_of 2026-09-27`).
- F6 used `<database>_frontend` (the development server and the rehearsal's dry run),
  `<database>_frontend_e2e` (Playwright and the performance record), the backend suite's own
  `_test` database, and the hosted Neon database (the rehearsal). It used nothing else.

**Known in F6, carried forward.**
- **An intermittent third warning in the backend suite.** The first full run at this gate reported
  6771 passed with 3 warnings, not the baseline's 2. The third is pydantic's
  `UnsupportedFieldAttributeWarning`, raised inside
  `tests/integration/test_m8_api.py::test_two_concurrent_identical_requests_converge_on_one_result_set`,
  when two concurrent requests build a schema at once. Nothing under a frozen path, and nothing in
  the repository `.venv`, changed since F5. Run alone eight times, the test gave the third warning
  three times. It is a race in frozen code and its frozen test, not an F6 effect. Removing it would
  be a backend milestone.
- Hashed assets are revalidated on every visit (above).
- The API's first request after a quiet spell takes a few seconds while the function starts.
- On a phone, Classic view's agent list comes before the page's content.
- React Three Fiber still logs three's `THREE.Clock` deprecation once per load.
- The hosted site has no authentication (§16). Reset before each review.

**Next:** F7 (industry-readiness), which needs its own backend milestones approved and closed first.

---

## Appendix A: fixed copy

These strings are DIRECTED (D-F-1, D-F-2, D-F-7, D-F-13). Each appears exactly once in `src/`.

| Where | Text |
|---|---|
| Product name (HUD, title) | `AI CEO HQ` |
| Decision panel | `Identity is recorded, not authenticated. Nothing is executed.` |
| About panel | `These agents are the system's rule-based components. In VS-01, no language model, embedding or prompt produces any part of a brief.` |
| Band legend | `A band is a policy artefact, not a probability.` |
| Replay banner | `Replay of recorded results · as_of <date>` |
| Already-assessed banner | `Already assessed: replaying recorded results` |
| Unknown-outcome message | `The result is unknown. Checking what was recorded…` |
| Empty decision chain | `No decisions recorded for this brief yet.` |
| Inbox, no brief at this date | `No customer is at WATCH or above on this date.` |
| Inbox, no assessment | `No assessment exists for this date yet. Run one from the top bar.` |
| MEMORY, no records | `No records yet: run an ingestion first.` |
| Unsupported brief | `This brief uses payload version <n>, which this frontend does not support.` |
| WebGL fallback notice | `The 3D office could not start on this device, so you are in Classic view. Every panel works the same.` |
| Mock source on hosted site | `This mock source runs in local mode only.` |
| Locked room sign | `Opens with VS-0<n>` |

**Agent role lines** (panel headers):

| Agent | Role line |
|---|---|
| Connector | `Fetches records from one configured source into Layer 1.` |
| MEMORY | `Holds the canonical Layer 1 records every agent reads.` |
| LINKER_AGENT | `Links documents to customers by exact id and exact name.` |
| SIGNALS_AGENT | `Computes each customer's signals and risk band.` |
| SALES_AGENT | `States the commercial position on each customer.` |
| SUPPORT_AGENT | `States the support position on each customer.` |
| RECONCILER_AGENT | `Resolves conflicting positions by a named policy, and keeps the dissent.` |
| BRIEF_WRITER | `Writes the cited brief the CEO decides on.` |
| CEO desk | `You decide. The system recommends; nothing is executed.` |
