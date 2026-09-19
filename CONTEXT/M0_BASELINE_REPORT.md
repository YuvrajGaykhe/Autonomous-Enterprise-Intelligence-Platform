# M0 — Layer 2 Pre-Flight Baseline Report
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**Executed: 2026-09-19 | Recorded by: Yuvraj Gaykhe**
**Status: BASELINE ONLY. No production code, test, migration, schema, config, dataset or Docker file was modified. VS-01 is not started.**

> **Purpose**: record the exact, reproducible state of the system immediately before Layer 2
> implementation begins, so a later audit can compare Layer 1 → M0 → VS-01 → later slices and
> determine precisely what changed at each stage.
>
> **Companion documents**
> - `CONTEXT/AI_CEO_PROJECT_CONTEXT.md` — confirmed project state and Layer 1 record.
> - `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md` — vertical-slice strategy (PLANNED).
> - `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` — VS-01 v2 build plan (PLANNED).

---

## 1. Executive summary

**Verdict: GO WITH CONDITIONS.**

Layer 1 is verifiably frozen, complete and green. Every headline number in the Layer 1 phase
record reproduced exactly on re-measurement: 4139 tests passed, 100% `app/` line coverage over
4460 statements, ruff 69, mypy 9, secret scan 0 findings, working tree clean, migration head
`8bfd73b6af60`. Attribution is clean: all 56 reachable commits are authored and committed as
`YuvrajGaykhe <yuvrajgaykhe.17@gmail.com>`, with no AI attribution anywhere in commit metadata,
messages, notes, tags or tracked files.

Every load-bearing numeric claim in the VS-01 v2 plan was independently recomputed from
`data/demo/` and **verified correct** — S1=4, S2=3 (TKT-075/076/080), S2b=4, S3=5, S4=5 over
2026-08-18→08-31, S6=22, S7=5, S8=3, S10=`performance` 3/5, S11=1 negotiation deal at 90%,
S12=DEAL-001 USD 5,361.44, S13=0. Exactly one customer (CUST-007, Meridian Textiles) satisfies
DOC-003's escalation rule. The conflict VS-01 reconciles is genuinely present in the committed
data. The document-grounding design holds: DOC-003 really carries the rule, DOC-005 really states
the conclusion in prose, and DOC-009 really records the customer tying DEAL-001 to ticket
resolution.

Eight findings are recorded in §14. **One is blocking (M0-F1)** and it is an environment
condition, not a design defect: the live development database does not represent the Layer 1
dataset. It is missing `organizations` (0 of 1) and `documents` (0 of 12) entirely, and carries
four extra rows injected by the malformed acceptance fixture under the *same* `source_system`
(`csv_demo`) as the real demo data. VS-01's entire evidence layer is built on documents; computed
against this database it would produce zero document citations. The remaining seven findings are
non-blocking documentation-accuracy and design-tension items.

---

## 2. Repository / Git state

| Item | Value |
|---|---|
| Current branch | `main` |
| HEAD SHA | `6d7a1cde11162e9fe01ae7363b81b534ff0a5749` |
| HEAD tree SHA | `baa706435d26bba73add8dbf8c2b8898e0a9b977` |
| `origin/main` (local ref) | `945e0bb5ebf5632474afa7aab44eb4d105452283` |
| GitHub `refs/heads/main` (`ls-remote`) | `945e0bb5ebf5632474afa7aab44eb4d105452283` |
| Ahead / behind `origin/main` | **ahead 3, behind 0** |
| Working tree | **clean** (no modified, staged or untracked files) |
| Tags | none |
| Git notes | none |
| Refs | `refs/heads/main`, `refs/remotes/origin/HEAD`, `refs/remotes/origin/main` |
| Remote | `origin` → `https://github.com/YuvrajGaykhe/Autonomous-Enterprise-Intelligence-Platform.git` |
| Total reachable commits | 56 |
| Tracked files | 229 |

### 2.1 Parent chain — verified, not assumed

The chain asserted in the M0 brief was checked against `git log --format='%H %P'` and is exact:

```
945e0bb  docs: finalize I phase context                                  (= Layer 1 release, origin/main)
   ↓
328a0f5  docs: record the post-Layer-1 vertical-slice strategy and the VS-01 plan
   ↓
c4496c7  docs: rebuild the VS-01 plan after an adversarial review (v2)
   ↓
6d7a1cd  docs: align the project context with the VS-01 v2 plan          (= HEAD)
```

All three commits since `945e0bb` are **documentation-only and unpushed**. `git diff --stat
945e0bb..HEAD` touches only `CONTEXT/`. Nothing under `app/`, `tests/`, `migrations/`, `config/`,
`data/`, `docker/` or the root build files differs from the Layer 1 release.

### 2.2 Identity and attribution

- Author identity across all 56 commits: `YuvrajGaykhe <yuvrajgaykhe.17@gmail.com>` — single value.
- Committer identity across all 56 commits: `YuvrajGaykhe <yuvrajgaykhe.17@gmail.com>` — single value.
- Grep over every reachable commit's author, committer, subject and body for `claude`,
  `anthropic`, `Co-Authored-By`, `Claude-Session`, `noreply@anthropic.com`, `Generated with`:
  **zero matches**.

---

## 3. Layer 1 freeze baseline

`945e0bb` is the released Layer 1 baseline. Layer 1 is **frozen**.

### 3.1 What Layer 1 provides

| Concern | Implementation | Files |
|---|---|---|
| Connector architecture | `SourceConnector` Protocol; three GET-only connectors over one demo dataset | `app/connectors/` (base, types, registry, csv, odoo, rest — 2,210 LOC) |
| Canonical model | 7 entity schemas + provenance base | `app/schemas/canonical/`, `app/persistence/models/` |
| Normalization | Config-driven field mapping, type coercion, enum/date/currency/boolean rules, `record_hash` | `app/normalization/` (config, mappings, coercion, pipeline, identifiers, contract, errors) |
| Validation | Quality gate with ERROR/WARNING/INFO severities and quarantine | `app/validation/` (gate, rules, quarantine, config, errors) |
| Reconciliation | FK resolution against persisted canonical state; unresolved FK → NULL + WARNING | `app/ingestion/reconciliation.py`, `app/persistence/repositories/canonical.py` |
| Provenance | 8 universal fields on every canonical row | `app/persistence/models/mixins.py` |
| Ingestion boundary | Run orchestration, batching, raw payload persistence, cursors, status semantics | `app/ingestion/`, `app/persistence/repositories/` |
| API | FastAPI `/api/v1`, 22 operations | `app/api/` |
| Security | URL/path/timeout validation, GET-only same-origin no-redirect client, secret hiding | `app/core/security.py`, `app/core/config.py`, `app/core/database.py` |
| Observability | Structured `log_event` logging + ingestion counters | `app/observability/`, `app/core/logging.py` |

Total: **99 tracked files under `app/`, 11,303 LOC.**

### 3.2 Canonical relationships that actually exist

Verified against the live PostgreSQL schema, not against documentation:

| FK | On delete |
|---|---|
| `deals.customer_id` → `customers.id` | SET NULL |
| `projects.customer_id` → `customers.id` | SET NULL |
| `support_tickets.customer_id` → `customers.id` | SET NULL |
| `employees.organization_id` → `organizations.id` | SET NULL |
| `ingestion_errors.ingestion_run_id` → `ingestion_runs.id` | CASCADE |
| `source_records.ingestion_run_id` → `ingestion_runs.id` | CASCADE |
| `ingestion_cursors.last_successful_run_id` → `ingestion_runs.id` | SET NULL |

**`documents` carries no customer FK and no organization FK.** Owner, assignee and manager
relationships exist only as `source_key` strings joined within one source system. There is no
cross-source entity resolution.

### 3.3 Frozen Layer 1 contracts — what Layer 2 may NOT silently change

1. **The D1 canonical vocabulary** in `config/mappings/normalization.yaml` (§5). Never widened to
   satisfy an analytical need.
2. **`record_hash` semantics** — business fields only; provenance and E1-resolved FKs excluded;
   sorted keys, compact separators, normalised `Decimal`, UTC ISO-8601 (`app/normalization/identifiers.py`).
3. **`canonical_id`** — UUID5 over `(source_system, source_entity, source_id)` under the fixed
   namespace `a1c30e00-b1a7-4e5f-9c3d-1a2b3c4d5e6f`. **Changing the namespace re-keys every persisted row.**
4. **Source identity** — `UNIQUE (source_system, source_entity, source_id)` on all 7 canonical tables.
5. **Migration `8bfd73b6af60`** and the 12 tables it creates. Layer 2 adds new revisions only.
6. **The 22 existing API operations**, their paths, verbs, status codes and response envelopes.
7. **E1 run status semantics** — `SUCCESS` / `PARTIAL_SUCCESS` / `FAILED` / `NOOP`.
8. **Unresolved-FK behaviour** — canonical FK NULL, `source_id` preserved, WARNING recorded.
9. **Read-only connectors** — GET only; no source write-back.
10. **`is_active` scope** — employees, customers, deals, projects only.

### 3.4 The Layer 1 / Layer 2 boundary

```
FROZEN LAYER 1                               NEW LAYER 2 (VS-01)
────────────────────────────────────         ──────────────────────────────────────
app/connectors/   app/normalization/         app/relationships/   app/intelligence/
app/validation/   app/ingestion/             app/analysts/        app/decisions/
app/persistence/models/                      config/intelligence/
app/schemas/canonical/                       migrations/versions/<new>_vs01.py
app/api/v1/{health,sources,ingestion,        app/api/v1/risk.py
            entities,metrics}.py
config/mappings/  config/validation/         5 new tables (§A18)
migrations/versions/{0001,8bfd73b6af60}      6 new routes under /api/v1/risk
data/demo/
```

**Verified absent at M0** (namespace is clear): `app/intelligence`, `app/relationships`,
`app/analysts`, `app/decisions`, `config/intelligence`. No existing route or source file
references `risk`.

---

## 4. Dataset baseline

Source of truth is `data/demo/` (committed CSVs), **not** the development database.

### 4.1 Verified counts

| Entity | Rows | Spec minimum | Met |
|---|---|---|---|
| organizations | **1** | 1 | ✅ |
| employees | **24** | 20 | ✅ |
| customers | **50** | 50 | ✅ |
| deals | **44** | 40 | ✅ |
| projects | **22** | 20 | ✅ |
| support_tickets | **80** | 75 | ✅ |
| documents | **12** | 10 | ✅ |
| **Total canonical rows** | **233** | — | — |

Bad fixture `data/fixtures/csv_demo_bad/`: **8 rows** (4 customers, 4 deals); other five files
are header-only.

`scripts/seed_demo.py --check` → `14 files up to date`, exit 0. **The dataset is byte-reproducible
from its seed.**

### 4.2 Composition

- **Source systems**: 3 declared (`csv_demo`, `odoo_mock`, `rest_mock`), all serving the *same*
  233 rows. `csv_demo` reads the CSVs directly; the other two read them through the mock-source
  container in source-native shapes.
- **Source IDs**: `ORG-001`, `EMP-0NN`, `CUST-0NN`, `DEAL-0NN`, `PROJ-0NN`, `TKT-0NN`, `DOC-0NN`.
- **Canonical IDs**: UUID5, deterministic, stable across re-ingestion.
- **Currencies**: INR 30 / USD 13 / EUR 1 on `deals`. **No FX rate table exists.** `projects.budget`
  carries no currency column at all.
- **Date ranges**: customers created 2023-01-10→2026-03-12 · tickets created 2026-01-06→**2026-08-27**
  · tickets resolved 2026-01-13→2026-08-23 · deals expected close 2023-03-28→2027-04-29 ·
  documents created 2025-06-12→2026-09-01.
- **Lifecycle states**: customers 46 active / 4 inactive · employees 23 active / 1 inactive ·
  deals 30 active / 14 inactive · projects 22 active / 0 inactive · tickets 67 resolved / 13 open.
- **Relationships**: **zero dangling references** across all nine source-key relationships
  (`deals`/`projects`/`support_tickets`→customers, `deals`/`projects`/`customers`/`documents`→employees,
  `support_tickets.assignee_id`, `employees.manager_id`). Every reference resolves.
- **Missing values**: 1 employee with blank `manager_id` (the CEO); 13 tickets with blank
  `resolved_date` (the open ones); 0 blank customer emails.
- **Duplicate behaviour**: none in `data/demo/`. The bad fixture deliberately repeats `CUST-901`.
- **Provenance**: all 8 universal fields populated on every canonical row at ingestion.

### 4.3 Facts that constrain VS-01

| Fact | Value | Consequence |
|---|---|---|
| Dataset clock | Last ticket **2026-08-27** | A 14-day window from a real `now()` is empty. `as_of` must be explicit. |
| Escalation rule satisfiers | **Exactly 1** — CUST-007, 5 tickets in 2026-08-18→08-31 | The demo has a single, document-grounded subject. |
| Ticketless customers | **15 of 50** (11 active + all 4 inactive) | Band `NONE` must be a normal outcome, not an error. |
| Inactive customers | 4 — **zero tickets, zero deals, zero projects** | No negative class; churn modelling is indefensible here. |
| Deal stages present | `qualification` 16, `negotiation` 14, `won` 14 | **No `lost` stage** → no churn label. |
| Customers with deals / projects | 28 / 16 | Executive-worthiness gate has a real population. |
| Document corpus | 12 documents, **3,734 chars** of body text total | Embeddings would be indefensible; exact selection is correct. |

### 4.4 Dataset fingerprint

No dataset fingerprint existed in the repository. Computed for this baseline (§15).

```
data/demo aggregate SHA-256 : 11737bb8fa46c212dc7f5315ba6382d080e2fc1a0a524d3276476b6054ed55f6
```

| File | SHA-256 |
|---|---|
| `customers.csv` | `7d43f4751caa030b076f3c579598057bcce24f93f9637f9e3cab62250991d879` |
| `deals.csv` | `41ba0fe21218a80f92096261e2740010662fbd6f00c4388f5b3978931bb00d42` |
| `documents.csv` | `7035e63d71f5df249f1a56fc5153860c1f8739fc2b311887570496f25228e584` |
| `employees.csv` | `00c3476d9bf2d1917b32e530783ef851e939a66f719db9aa1a8aaf8d9a5f158d` |
| `organizations.csv` | `988fc59b3eec2ae9ccf556e3f8e6cbb6f6a0b6484a00c566578786120bbfcf3e` |
| `projects.csv` | `9e61ae047c43a510d67fb86833b9e498d493ab9d02b0b70ec9d39ace71f3cd6c` |
| `support_tickets.csv` | `255d50a3c7fb7f1f4e2c2173cc374862e40dc89c89c6d1c03fcb1c506f87b9ac` |

---

## 5. Canonical vocabulary baseline

From `config/mappings/normalization.yaml` (`version: 1`), which is validated against the B2
canonical schemas at load. **Unknown labels are rejected, never guessed.**

| Field | Permitted canonical values |
|---|---|
| `deals.stage` | `qualification`, `negotiation`, `won` |
| `support_tickets.priority` | `medium`, `high` |
| `support_tickets.status` | `open`, `resolved` |
| `projects.status` | `planning`, `in_progress` |
| `customers.status` | `active`, `inactive` |
| `employees.status` | `active`, `inactive` |
| `organizations.status` | `active`, `inactive` |

Other constrained vocabulary: `null_tokens` = `null` / `n/a` / `-` (case-insensitive, trimmed);
`boolean_tokens` true = `true`/`yes`/`1`, false = `false`/`no`/`0`; `currency.codes` = 160 ISO-4217
codes; `currency.aliases` = `₹`→INR, `€`→EUR, `£`→GBP (`$` deliberately absent as ambiguous).

Decimal precision is pinned to the B1 columns: `amount` 15,2 · `probability` 5,2 bounded 0–100 ·
`budget` 15,2.

> **Binding for Layer 2.** VS-01 must not silently introduce a new canonical value. Notably
> absent and therefore **unavailable** to any Layer 2 rule: a `lost` deal stage, a `low` or
> `critical` ticket priority, an `in_progress` or `closed` ticket status, a `completed` or
> `cancelled` project status, and any customer status beyond active/inactive. If a later slice
> needs one, it is an explicit architecture decision recorded in the context document and
> accompanied by a dataset change — never an implementation shortcut.

---

## 6. Database / schema baseline

| Item | Value |
|---|---|
| Engine | PostgreSQL 16 (`postgres:16-alpine`) |
| Alembic head | **`8bfd73b6af60`** |
| `alembic_version` in live DB | **`8bfd73b6af60`** (in sync) |
| Revisions | 2 — `0001` (baseline, intentional no-op) → `8bfd73b6af60` (creates all 12 tables) |
| Tables | 12 application + `alembic_version` = 13 |

**Canonical (7):** `organizations`, `employees`, `customers`, `deals`, `projects`,
`support_tickets`, `documents`.
**Operational (5):** `ingestion_runs`, `ingestion_errors`, `source_records`, `connector_configs`,
`ingestion_cursors`.

- **Primary keys**: UUID `id` on every table (`pk_<table>`).
- **Unique constraints**: `uq_<entity>_source_identity UNIQUE (source_system, source_entity, source_id)`
  on all 7 canonical tables; `uq_ingestion_cursors_source_key (source_system, source_entity)`;
  `uq_connector_configs_source_name (source_name)`.
- **Foreign keys**: 7, listed in §3.2.
- **Indexes**: 49 in `public`. Every canonical table indexes `ingestion_run_id` and
  `source_updated_at`; `customers`/`employees` index `email`; `deals`/`projects`/`support_tickets`
  index `customer_id`; `support_tickets` indexes `created_at`; `ingestion_runs` indexes
  `source_system`, `status`, `started_at`; `ingestion_errors` indexes `severity`.
- **Provenance columns**: `id`, `source_system`, `source_entity`, `source_id`,
  `source_updated_at`, `ingested_at`, `ingestion_run_id`, `record_hash` on all 7 canonical tables.
- **Existing fingerprints**: per-row `record_hash` only. There is **no** table-level or
  snapshot-level Layer 1 fingerprint — `layer1_fingerprint` is genuinely new work for VS-01.

**`support_tickets.created_at` is indexed**, which is the access path every VS-01 window signal
needs. No new index is required for S1–S10.

### 6.1 Live development database state — NOT a clean baseline

> ⚠️ This is finding **M0-F1** (§14). Recorded, not corrected.

| Table | Live DB rows | `data/demo` rows | Δ |
|---|---|---|---|
| organizations | **0** | 1 | **−1** |
| documents | **0** | 12 | **−12** |
| customers | **52** | 50 | **+2** |
| deals | **46** | 44 | **+2** |
| employees | 24 | 24 | 0 |
| projects | 22 | 22 | 0 |
| support_tickets | 80 | 80 | 0 |

Operational: 12 `ingestion_runs` (1 SUCCESS, 7 NOOP, 4 PARTIAL_SUCCESS), 1,792 `source_records`,
24 `ingestion_errors`.

Diagnosis, from `ingestion_runs`: the single SUCCESS run fetched **220** records = 50+44+24+22+80,
i.e. five of seven entity types. `organizations` and `documents` were never ingested into this
database. The four PARTIAL_SUCCESS runs each fetched 8 records — the malformed acceptance fixture
(steps K–L of `verify_layer1`) — inserting `CUST-901`, `CUST-902`, `DEAL-901`, `DEAL-904`
**under `source_system = 'csv_demo'`**, indistinguishable by scope from the real demo data.

---

## 7. API / contract baseline

FastAPI, OpenAPI 3.1.0, title *AI CEO — Layer 1*, version 0.1.0, 46 component schemas.
**22 operations. 21 GET + 1 POST. No `securitySchemes` — authentication is absent by design.**

| Route | Method | Status codes |
|---|---|---|
| `/api/v1/health` | GET | 200, 503 |
| `/api/v1/sources` | GET | 200, 500 |
| `/api/v1/sources/{source}/health` | GET | 200, 404, 422, 500 |
| `/api/v1/ingestion/runs` | **POST** | 201, 422, 500 |
| `/api/v1/ingestion/runs` | GET | 200, 422 |
| `/api/v1/ingestion/runs/{run_id}` | GET | 200, 404, 422 |
| `/api/v1/ingestion/runs/{run_id}/errors` | GET | 200, 404, 422 |
| `/api/v1/entities/{7 types}` | GET | 200, 422 |
| `/api/v1/entities/{7 types}/{entity_id}` | GET | 200, 404, 422 |
| `/api/v1/metrics/ingestion` | GET | 200 |

- **Error behaviour**: structured envelope from `app/api/errors.py`; `x-request-id` correlation
  header on every response (`app/api/request_id.py`).
- **Pagination**: `limit`/`offset` on all list endpoints, with `total`.
- **Approval endpoints**: **none exist.** VS-01 introduces the first.
- **Governance boundary**: the only non-GET operation in the entire system is
  `POST /api/v1/ingestion/runs`. Nothing can send, write outward or act externally.
- **Deterministic interface**: `list_entities` filters by `source_system` and orders by
  `(source_system, source_entity, source_id)` — a stable order VS-01's fingerprint can rely on.

**All 22 operations are Layer 1 contracts. VS-01 must not break any of them.** Its six new routes
sit under the unused `/api/v1/risk` prefix.

---

## 8. Test baseline

Environment: Python **3.11.5** (scratchpad venv), pytest **9.1.1**, ruff **0.16.7**, mypy **2.3.1**.
Docker services `ai-ceo-postgres`, `ai-ceo-api`, `ai-ceo-mock-source` all healthy.

Command: `python -m pytest -q -p no:cacheprovider -o addopts=""`

| Layer | Path | Collected |
|---|---|---|
| Unit | `tests/unit/` (44 files) | **3,381** |
| Connector contract | `tests/contract/` (3 files) | **185** |
| Integration (DB) | `tests/integration/` (19 files) | **493** |
| End-to-end | `tests/e2e/` (4 files) | **80** |
| **Total** | 75 tracked test files | **4,139** |

| Result | Value |
|---|---|
| Collected | 4,139 |
| **Passed** | **4,139** |
| Failed / errored / skipped | **0 / 0 / 0** |
| Warnings | 2 (third-party deprecations: starlette/httpx, anyio) |
| Wall time | 177.83 s |
| Exit status | 0 |

Layer 1 acceptance tests (`tests/e2e/test_i1_acceptance.py`) and G2 security/boundary tests
(`test_g2_import_safety.py`, `test_g2_outbound_safety.py`, `test_g2_secret_hygiene.py`,
`test_g2_security_boundary.py`, `test_g2_secret_canary.py`) are inside these totals and all pass.

**Coverage** (`--cov=app`): **4,460 statements, 0 uncovered, 100%** line coverage.
Branch coverage was not measured — a pre-existing limitation, unchanged.

Every one of these figures matches the documented Layer 1 baseline at `fff40f6` exactly.

---

## 9. Quality baseline

| Gate | Command | Result | vs. Layer 1 baseline | Classification |
|---|---|---|---|---|
| Ruff | `ruff check app/ tests/` | **69 findings** | 69 | existing baseline condition |
| Ruff (+scripts) | `ruff check app/ tests/ scripts/` | 69 findings | — | existing baseline condition |
| Mypy | `mypy app/` | **9 errors in 4 files** (87 files checked) | 9 | existing baseline condition |
| Secret scan | `python scripts/secret_scan.py` | **0 findings**, 226 files scanned, 3 binaries skipped, exit 0 | 0 over 224 files | existing baseline condition |
| Whitespace | `git diff --check` / `--cached --check` | clean | clean | — |
| Attribution | repo-wide grep (§10) | clean | clean | — |

Ruff breakdown: F401 ×25, I001 ×19, UP017 ×10, B904 ×7, UP015 ×4, B007 ×2, C416 ×1, B011 ×1.
Mypy: `normalization/coercion.py` ×3, `normalization/mappings.py` ×2, `connectors/rest.py` ×2,
`connectors/odoo.py` ×2.

The secret-scan file count rose 224 → 226 because the two new `CONTEXT/*.md` planning documents
are now tracked. Findings remain 0. **No finding was fixed during M0.**

---

## 10. Security / attribution baseline

### 10.1 Attribution — clean

Searched: tracked files, all reachable commit messages, author/committer metadata, notes, tags
and refs, for `Claude`, `Anthropic`, `Co-Authored-By`, `Claude-Session`,
`noreply@anthropic.com` and generated-by attribution.

| Surface | Result |
|---|---|
| Commit messages (56) | **0 matches** |
| Author / committer metadata | **0 matches** — single identity `YuvrajGaykhe <yuvrajgaykhe.17@gmail.com>` |
| Git notes / tags | none exist |
| Tracked files — explicit attribution patterns | **0 matches** |

### 10.2 Technical references — not attribution

Two categories of match exist and are **correctly not authorship attribution**:

| Location | Match | What it actually is |
|---|---|---|
| `tests/unit/test_d1_normalization.py:513`, `tests/unit/test_d2_boundary.py:64` | `"anthropic"` | An entry in `FORBIDDEN_MODULE_PREFIXES`. The D1/D2 boundary tests **forbid** importing the Anthropic SDK (alongside `openai`, `langchain`, `neo4j`, `sqlalchemy`, …). This is anti-LLM enforcement — the opposite of attribution. |
| `skills-lock.json` lines 10, 13, 40, 43 | `claude-handoff`, `git-guardrails-claude-code` | Directory names in a developer-tooling lockfile. Not authorship metadata, and not referenced by any application code. |

> Recorded for accuracy: `skills-lock.json` is a tracked **developer-tooling** artifact with no
> role in the application, its tests, its build or its deployment. It is not a correctness or
> attribution problem; whether it belongs in the repository at all is a separate housekeeping
> question, out of scope for M0.

### 10.3 Security boundary state

- No authentication anywhere — documented design decision, unchanged.
- Connectors GET-only; `app/core/security.py` re-validates every outbound request (same-origin,
  no-redirect, finite timeout ≤ 300 s).
- CSV reads re-checked at read time for extension, directory containment (symlinks included),
  regular-file status and size ≤ 50 MiB.
- `Settings` hides DB password and URL from `repr`; engines never echo SQL.
- Two named G2 exemptions exist, both for `scripts/verify_layer1.py` (its own-API `httpx.Client`,
  and the `pytest` subprocess), each pinned by a test that fails if the exemption becomes unnecessary.

---

## 11. Docker / deployment baseline

| Item | State |
|---|---|
| `Dockerfile` | `python:3.11-slim`; installs `libpq-dev`; `pip install .` (runtime deps only, no dev extras); copies `app/`, `config/`, **`data/demo/` only**, `alembic.ini`, `migrations/`; `EXPOSE 8000`; `uvicorn app.main:app` |
| `docker/Dockerfile.mock-source` | Mock-source image; bakes in the same demo CSVs |
| `docker/mock_source.py` | Serves `/odoo/...` and `/rest/...` from one container |
| `.dockerignore` | Excludes `.git`, `.github`, venvs, caches, `.env*`, `data/raw`, `data/quarantine`, **`CONTEXT`**, compose files |
| `docker-compose.yml` | 3 services: `postgres` (16-alpine, named volume `pgdata`), `api` (8000), `mock-source` (8080). All healthchecked; `restart: unless-stopped`; `api` depends on healthy postgres |
| `.env.example` | Committed with placeholder values only; real `.env` gitignored |
| **CI configuration** | **None. `.github/` does not exist.** All gates are run manually via `make`. |
| Current build state | All three containers **Up and healthy**; images already built (not rebuilt during M0) |

**Deployment assumptions**: single-host Docker Compose; PostgreSQL state persists in the `pgdata`
named volume across `docker compose down` (destroyed only by `-v`); the API image deliberately
**excludes `data/fixtures/`**, which is why `verify_layer1` steps K–L must run on the host; images
are not rebuilt automatically after a source change.

No Docker or deployment file was inspected destructively or modified.

---

## 12. Vertical-slice architecture baseline

Each design decision in the strategy and VS-01 v2 plan, checked against the repository.

### 12.1 Data / relationship substrate — ✅ supported

PostgreSQL carries all three customer FKs needed by `neighbourhood()`, each with a supporting
index (`ix_deals_customer_id`, `ix_projects_customer_id`, `ix_support_tickets_customer_id`).
`escalation_path()` is at most two source-key hops (`customers.owner_source_id` →
`employees.manager_source_id`), which SQL handles directly. **No query in VS-01's four public
queries requires variable-length traversal, so Neo4j is correctly deferred.** No graph dependency
is declared in `pyproject.toml`. Placing the relationship layer behind a substrate-agnostic
interface is compatible with the current code — nothing in `app/` presumes a graph store.

### 12.2 Documents — ✅ correct and untouched

`documents` has **no** customer FK, confirmed in the live schema. No customer FK was added during
M0. Derived links with `basis` / `matched_token` / offsets / `linker_version` /
`layer1_fingerprint` in a new `document_customer_links` table leave Layer 1 untouched.

Measured link evidence for CUST-007 (independently recomputed):

| Document | `CUST-007` token | Exact name "Meridian Textiles" | Type |
|---|---|---|---|
| DOC-005 | ✅ | ✅ | report |
| DOC-006 | ✅ | ✅ | contract |
| DOC-009 | ✅ | ✅ | meeting_notes |

**The substring trap is real and stronger than documented.** The dataset holds **four** customers
whose names end in "Textiles": `CUST-002 Northstar Textiles`, `CUST-007 Meridian Textiles`,
`CUST-039 Evergrid Textiles`, `CUST-041 Westbrook Textiles`. The plan and strategy name three.
Token-boundary matching is mandatory (see M0-F5).

### 12.3 Risk vs impact — ✅ preserved, and the data supports it more strongly than documented

The separation is correct and the repository supports it. The supporting *figures* in the context
document are imprecise (M0-F3). Recomputed:

| Measure | CUST-007 / DEAL-001 |
|---|---|
| Support pressure rank | **1st of 50** — the only customer meeting DOC-003's rule |
| Weighted exposure (amount × probability, active deals, per customer) | **22nd of 23** — 4,825.30 vs median 221,900.00 |
| Raw active-deal amount per customer | **23rd of 23** |
| Deal amount among all 44 deals | **43rd of 44** |
| Deal amount among the 13 USD deals | **12th of 13** |

A blended score would bury the only genuinely escalating account. Keeping risk ordinal, and money
off the sort key entirely (`band desc → S8 desc → S4 desc → source_id asc`), is correct.

### 12.4 Time-dependent rules — ✅ verified, and the `as_of` rule is load-bearing

- Dataset clock stops **2026-08-27**; `now()` (2026-09-19) yields an empty 14-day window. Confirmed.
- `ACCEPTANCE_AS_OF = 2026-09-18` reproduces every asserted signal value exactly.
- The `max(created_at)` = 2026-08-27 fallback **changes results**, confirming the plan's own
  warning that it is for ad-hoc use only:

| Signal | @ 2026-09-18 (pinned) | @ 2026-08-27 (fallback) |
|---|---|---|
| S7 `sla_breach_count` (CUST-007) | **5** | 3 |
| S8 `open_sla_breach_high_count` (CUST-007) | **3** | 2 |
| Leader on total SLA breaches | CUST-007 (5), CUST-009 (4) | **CUST-009 (4)**, CUST-007 (3) |

`support_tickets.created_at` is indexed, so sliding-window evaluation is efficient. Deterministic
UTC-date bucketing with a fixed weekday rule and no holiday calendar is a stated limitation and
is reproducible. **See M0-F4: the context document misattributes which date produces which ranking.**

### 12.5 Grounding — ✅ verified against document text

| Requirement | Verified |
|---|---|
| DOC-003 carries the rule, not an invented threshold | ✅ DOC-003 states *"resolution target 1 business day"* (high), *"resolution target 5 business days"* (medium), and *"three or more tickets within 14 days are escalated to their account owner"* |
| DOC-005 states the conclusion in prose (leakage risk is real) | ✅ DOC-005 names CUST-007, "5 tickets between 2026-08-18 and 2026-08-27", "4 remain open while deal DEAL-001 is in negotiation" |
| DOC-009 records the customer tying the deal to the tickets | ✅ verbatim: *"tied the Meridian Textiles - Seat Expansion decision (DEAL-001) to resolving them"* |
| DOC-010 is topical only and never names Meridian | ✅ contains neither `CUST-007` nor the customer name |
| **The leave-DOC-005-out test is justified and mandatory** | ✅ Every S1–S10 value is derivable from `support_tickets` alone; removing DOC-005 must change nothing |

### 12.6 Governance — ✅ compatible

- **Approval boundary**: no approval endpoint exists; VS-01 introduces the first. No collision.
- **Payload binding**: `record_hash` already implements the exact serialisation discipline
  (`sort_keys`, `separators=(",",":")`, normalised `Decimal`, UTC ISO-8601) that `payload_hash`
  reuses. Directly reusable.
- **Identity assumptions**: no authentication exists (confirmed: no `securitySchemes`). The
  approver identity is **asserted, not verified**, and must be documented in exactly those terms.
- **Deterministic facts**: all S1–S15 values recomputed and confirmed deterministic.
- **Human authorization boundary**: the only non-GET route in the system is
  `POST /api/v1/ingestion/runs`. No outbound client, mail library or source-write path exists
  outside the G2-guarded connector layer. **No executor exists, and none can be reached.**

### 12.7 Conflict handling — ✅ the conflict is real and in the data

Independently confirmed at `as_of = 2026-09-18`:

- **Sales**: DEAL-001 `negotiation`, `is_active = true`, probability **90.00**, USD **5,361.44**
  → satisfies `ACCELERATE_DEAL_CLOSE` (active, negotiation, ≥ 80).
- **Support**: policy escalation true (5 tickets in the 14-day window 2026-08-18→08-31),
  S8 = 3 open high-priority SLA breaches → satisfies `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` (S8 ≥ 1).
- Both actions target the **same object, DEAL-001**. The conflict is genuine, not manufactured.
- `ASSIGN_DEDICATED_SUPPORT_OWNER` (S8 ≥ 2 → 3 ✅), `REVIEW_INVOICE_DISPUTE` (open `billing`
  ticket → TKT-079 ✅), `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA` (S5 ✅) and
  `SCHEDULE_EXECUTIVE_SPONSOR_CALL` (S5 ∧ S11 > 0 ✅) also fire.
  **All six non-`NO_ACTION` entries trigger, exactly as A16 claims.**

VS-01 owning the mechanism is correct: VS-04 extends a working reconciler rather than inventing one.

### 12.8 Assessment identity — ✅ feasible, with one gap

`layer1_fingerprint` = SHA-256 over scoped canonical `record_hash` values and per-entity counts.
`record_hash` exists, is per-row, is stored on every canonical table, and `list_entities` provides
a deterministic scoped ordering. **The design is implementable today.** One definitional gap is
recorded as M0-F2.

---

## 13. VS-01 readiness

| # | Item | Status | Repository evidence |
|---|---|---|---|
| 1 | Data available | ✅ | 233 rows across 7 entities in `data/demo/`; `seed_demo.py --check` → up to date, exit 0 |
| 2 | Canonical relationships available | ⚠️ | 3 customer FKs verified in live schema with indexes; **`documents` has no customer FK** — derived links required (by design) |
| 3 | Deterministic risk rules possible | ✅ | All of S1–S15 recomputed from `support_tickets`/`deals`/`projects` alone; every asserted value in A10 reproduced |
| 4 | Document evidence strategy defined | ✅ | Strategy §7.2–7.5; DOC-003/005/006/009/010 text verified; four "Textiles" customers confirm the substring ban is necessary |
| 5 | Provenance strategy defined | ✅ | 8 provenance fields on every canonical row; `basis`/`matched_token`/offsets/`linker_version` specified in A11/A18 |
| 6 | Assessment identity defined | ⚠️ | `record_hash` + counts implementable today; **`source_id` is excluded from `record_hash`** — see M0-F2 |
| 7 | Conflict handling defined | ✅ | A15 policy schema; conflict confirmed present in data (§12.7) |
| 8 | Approval boundary defined | ⚠️ | A17/A18/A19 define payload-hash binding and append-only decisions; **identity is asserted, not verified** — no auth exists (documented, accepted) |
| 9 | API integration point identified | ✅ | `/api/v1/risk` prefix unused; F1/F2 envelope, `x-request-id` and limit/offset conventions reusable |
| 10 | Test strategy defined | ✅ | A25–A27; 4 existing test layers with established markers and a PostgreSQL harness in `tests/conftest.py` |
| 11 | Baseline measurements captured | ✅ | This report, §2/§4/§6/§8/§9/§15 |
| 12 | Layer 1 freeze boundary identified | ✅ | §3.3 (10 frozen contracts) and §3.4 (directory boundary); target packages verified absent |

**Score: 9 ✅ / 3 ⚠️ / 0 ❌.** All three ⚠️ are known, documented and designed-around, not surprises.

---

## 14. M0 findings

### M0-F1 — Development database does not represent the Layer 1 dataset · **HIGH · BLOCKS M1**

**Evidence.** Live `ai_ceo_layer1`: `organizations` 0 (expected 1), `documents` **0** (expected 12),
`customers` 52 (expected 50), `deals` 46 (expected 44). `ingestion_runs` shows one SUCCESS run of
**220** records — five of seven entity types — plus four PARTIAL_SUCCESS runs of the 8-row
malformed fixture that inserted `CUST-901`, `CUST-902`, `DEAL-901`, `DEAL-904`.

**Why it matters.** Two independent problems:

1. **Documents are absent.** VS-01's evidence layer, its derived links, its policy citations and
   its grounding guarantee are all built on the 12 documents. Computed against this database,
   VS-01 produces zero document citations — and A17's rule that an unresolvable citation makes a
   brief invalid means the generator would raise, or worse, silently emit an evidence-free brief.
2. **The malformed fixture shares the real scope.** The bad-fixture rows were ingested under
   `source_system = 'csv_demo'`, the same value VS-01's default `Scope` uses. They are not
   separable by scope. `layer1_fingerprint` correctly *detects* that this snapshot differs from a
   clean one — but it cannot tell anyone *which* is correct, and every developer who has run
   `make verify-layer1` has this polluted state.

**Recommended resolution.** Before M1, define and document the canonical VS-01 evaluation database
state, and make the fingerprint mismatch visible rather than silent. Two options, both cheap:
(a) rebuild the development database from a full 7-entity ingestion and record the resulting
`layer1_fingerprint` as the pinned acceptance value; or (b) give the malformed fixture its own
`source_system` (e.g. `csv_demo_bad`) so acceptance runs cannot contaminate the default scope.
Option (b) touches Layer 1 fixture configuration and is therefore an explicit architecture
decision, not an M1 implementation detail. **Blocks M1** — M1 pins `Scope` and acceptance values.

### M0-F2 — `layer1_fingerprint` cannot detect a `source_id` change · **MEDIUM · does not block M1**

**Evidence.** `app/normalization/contract.py` derives `PROVENANCE_FIELDS` from
`CanonicalBase.model_fields`, and `BUSINESS_FIELDS` excludes them. `source_id` is a provenance
field, so `record_hash` **excludes it** (`app/normalization/identifiers.py` docstring confirms:
"excludes all provenance fields (id, source_system, source_entity, source_id, …)").

**Why it matters.** A5 defines `layer1_fingerprint` as "SHA-256 over the scoped canonical
`record_hash` values and per-entity counts". If a source record's `source_id` changed while its
business content did not, both the hash multiset and the counts stay identical — the fingerprint
is unchanged — yet `canonical_id` changes, every FK re-resolves and the whole relationship graph
VS-01 reasons over is different. The stale-intelligence hole that `layer1_fingerprint` was
introduced to close would remain open along this one axis.

**Recommended resolution.** Widen the fingerprint input to include the scoped `source_id` values
(or canonical `id`s) alongside the `record_hash` values and counts, and pin it with a
sensitivity test that renames a `source_id` and asserts the fingerprint changes. This is a
one-line definitional change in M1, cheaper before implementation than after.

### M0-F3 — Strategy's exposure figures are imprecise and mix currencies · **LOW · does not block M1**

**Evidence.** `AI_CEO_PROJECT_CONTEXT.md` §17.2 states CUST-007 is *"roughly twelfth on weighted
exposure (DEAL-001 is USD 5,361 against a portfolio median of ~327,750)"*. Recomputed: "twelfth"
is DEAL-001's rank among the **13 USD deals by raw amount**, not a weighted-exposure rank; on
weighted exposure across the portfolio CUST-007 is **22nd of 23**. The median 327,750 is the
median of **all 44 deal amounts across INR/USD/EUR** — a mixed-currency aggregate, which the same
document's §17.2 forbids ("No cross-currency aggregate may be produced until VS-02 delivers the
rate set").

**Why it matters.** The *conclusion* — keep risk and money on separate axes — is correct and in
fact better supported than stated (22nd, not 12th). But the supporting sentence performs exactly
the cross-currency comparison the project has banned, which is precisely what an examiner probes.

**Recommended resolution.** Restate with currency-qualified, like-for-like figures. No design change.

### M0-F4 — Context §17.5 misattributes the `as_of` SLA ranking · **LOW · does not block M1**

**Evidence.** §17.5 reads: *"Default resolves to `max(created_at)` = 2026-08-27, but every value
was computed at 2026-09-18, where the SLA-breach ranking inverts (CUST-009 has 4, CUST-007 has 3)"*.
Recomputed with DOC-003 targets (high 1, medium 5 business days):

| `as_of` | Total SLA breaches |
|---|---|
| **2026-08-27** (the fallback) | **CUST-009 = 4, CUST-007 = 3** ← the quoted numbers |
| **2026-09-18** (pinned) | CUST-007 = 5, CUST-009 = 4 |

The parenthetical describes **2026-08-27**, not 2026-09-18. The dates are swapped.

**Why it matters.** The underlying decision (pin `as_of = 2026-09-18`; the fallback is ad-hoc
only) is correct and this finding *strengthens* it. But an M3/M9 test written from this sentence
would assert the wrong pair. Correct before M3 writes signal tests.

### M0-F5 — Substring trap involves four customers, not three · **LOW · does not block M1**

**Evidence.** Strategy §7.2 and plan A11 name "Meridian Textiles", "Westbrook Textiles" and
"Northstar Textiles". The dataset also contains **`CUST-039 Evergrid Textiles`**.

**Why it matters.** Harmless to the design (token-boundary matching handles four as easily as
three) but the M4 test fixture should enumerate all four, or it under-tests the exact rule it
exists to protect.

### M0-F6 — A23's ticketless-customer count double-counts · **LOW · does not block M1**

**Evidence.** A23 reads *"Ticketless customer → band `NONE`, not an error (15 such customers, plus
the 4 inactive ones)"*, implying 19. Measured: **15 ticketless customers in total**, of which the
4 inactive customers are a **subset** (all 4 inactive customers have zero tickets, zero deals and
zero projects). The correct split is 11 active-and-ticketless + 4 inactive = 15.

**Why it matters.** An M3 or M9 test written as `assert len(none_band) == 19` fails; written as
`== 15` it passes. Correct the sentence before M3.

### M0-F7 — `ID_TOKEN` links may derive signals, and DOC-005 is an `ID_TOKEN` link · **LOW · design tension, does not block M1**

**Evidence.** A11 grants `ID_TOKEN` links "May derive signals: **Yes**". DOC-005 — the document
whose prose states the conclusion — matches CUST-007 by both `ID_TOKEN` and `EXACT_NAME`.

**Why it matters.** Today the tension is latent: no S1–S15 signal derives from a document, so the
leave-DOC-005-out test passes trivially. But the permission and the leakage risk point at the same
document. The moment any future slice derives a signal from an `ID_TOKEN` link, DOC-005 becomes
eligible and the platform's most valuable test starts protecting nothing.

**Recommended resolution.** State explicitly that in VS-01 **no** signal is document-derived, and
keep the leave-DOC-005-out test asserting exact equality of all signal values, not just the band —
so the test fails loudly if that ever changes.

### M0-F8 — Documentation metadata is stale / imprecise · **LOW · does not block M1**

Recorded, **not corrected**, per M0 rule 18.

| Location | Says | Actual |
|---|---|---|
| `AI_CEO_PROJECT_CONTEXT.md` line 3 | "Last updated: **2026-09-16**" | Last modified by `6d7a1cd` on **2026-09-18**; §17 is dated 2026-09-18 |
| `AI_CEO_PROJECT_CONTEXT.md` §12, task A3 | "Alembic setup + **all 11 migrations**" | **2** revisions (`0001` no-op → `8bfd73b6af60`), creating **12** tables |
| `AI_CEO_PROJECT_CONTEXT.md` §17.2 | "**Only three canonical FKs exist**" | Four canonical entity→entity FKs; three are *to customers*. `employees.organization_id → organizations.id` also exists |
| `AI_CEO_POST_LAYER1_STRATEGY.md` §9.2 | approval binds to `brief_content_hash` | Superseded by VS-01 v2: approval binds to the **decision payload** hash. §9.2 still carries pre-v2 language |
| `AI_CEO_PROJECT_CONTEXT.md` §12, tasks I1/I2 | "Complete locally — **not pushed**" | Both are pushed; `origin/main` is `945e0bb`, a descendant of both. The release note two paragraphs later says so correctly |

**No context document was modified during M0.** Correcting these is a separate, approved change.

---

## 15. Frozen invariants

Locked at M0. A later audit compares against these to prove Layer 1 was untouched.

| # | Invariant | Value |
|---|---|---|
| I1 | Layer 1 release commit | `945e0bb5ebf5632474afa7aab44eb4d105452283` |
| I2 | M0 HEAD | `6d7a1cde11162e9fe01ae7363b81b534ff0a5749` |
| I3 | Layer 1 source fingerprint (`app/` + `config/` + `migrations/`) | `1bdb01788ff9fd249990563049d4e0504e2b73ace223070c63f86b68fcabaa96` |
| I4 | Dataset fingerprint (`data/demo/`) | `11737bb8fa46c212dc7f5315ba6382d080e2fc1a0a524d3276476b6054ed55f6` |
| I5 | Normalization config | `36aefb1b26054bacdddf99a77b916989ec810ebe35702befbfe84a8c07cd5191` |
| I6 | Quality-gate config | `343cedae26096856fd7b621fe48d8f823bddfd13c10c2177d1373812b5517688` |
| I7 | Migration state fingerprint (`migrations/`) | `5cca03224d38936ca3ebcd81b2b400766d6e05ae47ee042b0cb85552893da45d` |
| I8 | Whole tracked tree (229 files) | `b741640f339ffacedf30764476c63b1f6d2ec5ff69c7dbb551604121d977da28` |
| I9 | HEAD git tree object | `baa706435d26bba73add8dbf8c2b8898e0a9b977` |
| I10 | Alembic head | `8bfd73b6af60` |
| I11 | Canonical UUID5 namespace | `a1c30e00-b1a7-4e5f-9c3d-1a2b3c4d5e6f` |
| I12 | Test total / passed | 4139 / 4139 |
| I13 | `app/` coverage | 4460 statements, 0 uncovered, 100% |
| I14 | Ruff / mypy / secret scan | 69 / 9 / 0 |
| I15 | API operations | 22 (21 GET + 1 POST), no `securitySchemes` |
| I16 | Canonical dataset rows | 233 |

### 15.1 Fingerprint method

Content-addressed, path-ordered, reproducible without a database:

```bash
git ls-files <paths> | sort | while read -r f; do
  printf '%s  %s\n' "$(git hash-object "$f")" "$f"
done | shasum -a 256
```

I3 uses `app config migrations`; I4 uses `data/demo`; I7 uses `migrations`; I8 uses no path
argument. I5/I6 are plain `shasum -a 256` of the single file. I9 is `git rev-parse HEAD^{tree}`.

**Future comparison.** After VS-01, recomputing I3 with the *same* path set will include VS-01's
new `migrations/versions/<new>_vs01.py` and any new `config/intelligence/` files, so I3 will
change legitimately. To prove Layer 1 itself is unchanged, recompute over the **M0 file list**
(the 229 paths in I8's input), not over the then-current `git ls-files` output. I4, I5, I6, I10
and I11 must be **byte-identical after VS-01** — those are the true freeze proofs.

### 15.2 Not fingerprinted, and why

- **Database content.** The live database is in the polluted state described in §6.1, so a hash of
  it would enshrine a defect as a baseline. The `data/demo` fingerprint (I4) is the correct
  dataset invariant; the database is a derived artifact.
- **Docker images.** Not rebuilt during M0; image digests would record the build host, not the
  repository.

---

## 16. Exact commands executed

**Git (read-only)**
```
git rev-parse --abbrev-ref HEAD ; git rev-parse HEAD ; git rev-parse HEAD^{tree}
git status --porcelain=v1 -uall ; git status -sb
git tag -l ; git remote -v ; git branch -avv ; git notes list
git for-each-ref --format='%(refname) %(objectname:short)'
git ls-remote origin
git log --format='%H %P | %an <%ae> | %cn <%ce> | %aI | %cI | %s' -8
git log --format='%h %s' 945e0bb..HEAD
git rev-list --left-right --count origin/main...HEAD ; git rev-list --all --count
git log --all --format='%H%n%an%n%ae%n%cn%n%ce%n%B%n---COMMITEND---' | grep -inE 'claude|anthropic|co-authored-by|generated with|noreply@'
git log --all --format='A:%an <%ae>' | sort -u ; git log --all --format='C:%cn <%ce>' | sort -u
git grep -InE 'Co-Authored-By|Claude-Session|noreply@anthropic\.com|Generated with \[Claude|anthropic\.com' -- .
git grep -InoiE 'claude' -- . ; git grep -InoiE 'anthropic' -- .
git ls-files ; git ls-files app config migrations data scripts ; git ls-files 'app/**' | xargs wc -l
git diff --check ; git diff --cached --check
```

**Quality**
```
ruff check app/ tests/
ruff check app/ tests/ scripts/
ruff check app/ tests/ --output-format=concise
mypy app/
python scripts/secret_scan.py
```

**Tests**
```
python -m pytest --collect-only -q -p no:cacheprovider -o addopts=""
python -m pytest tests/{unit,contract,integration,e2e} --collect-only -q -p no:cacheprovider -o addopts=""
python -m pytest -q -p no:cacheprovider -o addopts=""
python -m pytest -q -p no:cacheprovider -o addopts="" --cov=app --cov-report=term
```

**Dataset (read-only)**
```
python scripts/seed_demo.py --check
```
plus four throwaway stdlib-only analysis scripts in the session scratchpad (row counts,
distributions, referential integrity, VS-01 signal recomputation, SLA-breach recomputation at both
`as_of` dates, exposure ranking). **None wrote to the repository.**

**Database (read-only SQL)**
```
docker exec ai-ceo-postgres psql -U ai_ceo -d ai_ceo_layer1 -c "\dt"
  SELECT * FROM alembic_version;
  information_schema FK / unique / check constraint queries
  SELECT tablename, indexname FROM pg_indexes WHERE schemaname='public';
  per-table SELECT count(*)  ·  SELECT ... FROM ingestion_runs ORDER BY started_at
```

**API (read-only)**
```
curl -s http://localhost:8000/openapi.json
```

**Fingerprints** — see §15.1.

**Environment**
```
open -a Docker        # started the daemon; see §18
docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
```

---

## 17. Exact results

| Check | Result | Baseline | Match |
|---|---|---|---|
| Branch / HEAD | `main` / `6d7a1cd` | — | — |
| `origin/main` local = GitHub | `945e0bb` = `945e0bb` | — | ✅ |
| Ahead / behind | 3 / 0 | 3 unpushed docs commits | ✅ |
| Working tree | clean | clean | ✅ |
| Commit chain `945e0bb`→`328a0f5`→`c4496c7`→`6d7a1cd` | verified | asserted | ✅ |
| Attribution in commit metadata | 0 matches | 0 | ✅ |
| Author/committer identity | single: `YuvrajGaykhe <yuvrajgaykhe.17@gmail.com>` | required | ✅ |
| Tests collected / passed | 4139 / **4139** | 4139 / 4139 | ✅ |
| Failed / errored / skipped | 0 / 0 / 0 | 0 | ✅ |
| `app/` coverage | 4460 stmts, 0 uncovered, **100%** | 100% | ✅ |
| Ruff | **69** | 69 | ✅ |
| Mypy | **9** in 4 files | 9 | ✅ |
| Secret scan | **0** findings / 226 files | 0 / 224 files | ✅ (file count +2: new CONTEXT docs) |
| `git diff --check` | clean | — | ✅ |
| Alembic head (file = live DB) | `8bfd73b6af60` = `8bfd73b6af60` | — | ✅ |
| Tables | 12 + `alembic_version` | 12 | ✅ |
| API operations | 22 (21 GET + 1 POST), no auth | 22 | ✅ |
| Dataset rows | **233** | 233 | ✅ |
| `seed_demo.py --check` | 14 files up to date, exit 0 | reproducible | ✅ |
| VS-01 signals S1–S15 @ `as_of` 2026-09-18 | **all reproduced exactly** | as asserted in A10 | ✅ |
| Escalation-rule satisfiers | **exactly 1** (CUST-007) | exactly 1 | ✅ |
| Live database vs dataset | **organizations 0/1, documents 0/12, +4 fixture rows** | clean expected | ❌ **M0-F1** |

---

## 18. Items NOT executed, and why

| Item | Status | Reason |
|---|---|---|
| `make verify-layer1` (Layer 1 acceptance scenario) | **NOT RUN** | It *writes* to the database through `run_ingestion()`, including the malformed fixture at steps K–L. Running it would have altered the very database state M0 exists to record (§6.1), and would have masked finding M0-F1 by ingesting the missing documents. The state was recorded instead. Its 135 I1 tests + 30 I2 tests **did** run as part of the 4139. |
| Mutation audit | **NOT RUN** | The ad-hoc textual harness lives in a prior session's scratchpad and is not in the repository. Re-running it changes no baseline the M0 brief requires; the per-phase mutation figures in the context document stand as recorded. |
| Docker image rebuild | **NOT RUN** | M0 forbids rebuilding or redesigning deployment. Existing images were already built and healthy. |
| Branch-coverage measurement | **NOT RUN** | Line coverage is the established baseline; adding a metric would create a false new baseline. Pre-existing limitation, unchanged. |
| Grilling / adversarial-review **skill** | **NOT INVOKED** | `skills-lock.json` references `grilling`, `grill-me` and `grill-with-docs`, but no `skills/` directory exists in the repository and none of them is an invocable skill in this session. The adversarial review was performed directly and is recorded in §12 and §14. |
| Any fix to a finding | **NOT DONE** | M0 is discovery only. All eight findings are recorded, none corrected. |
| Any context-document edit | **NOT DONE** | Rule 18: staleness is reported (M0-F8), not silently rewritten. |
| Push | **NOT DONE** | Rule 19. The 3 documentation commits remain local. |

### 18.1 One environment action, disclosed

The Docker daemon was **not running** at M0 start. It was started with `open -a Docker` so that
the 493 integration and 80 end-to-end tests — the existing read-only verification suite the M0
brief requires in §8 — could execute. This altered **no repository state**: the working tree was
verified clean before and after, and the three containers came up from their existing images and
the existing `pgdata` volume. Had it not been started, 573 of 4139 tests would have been recorded
as blocked. The database contents were **read but never written** (§16), and the polluted state in
§6.1 pre-existed this session.

---

## 19. Recommended next step

**Verdict: GO WITH CONDITIONS.** Layer 1 is frozen, green and reproducible; the VS-01 v2 plan's
data assumptions are verified correct; the namespace, schema and API surface VS-01 needs are all
clear.

### 19.1 Entry conditions for M1 — must be satisfied first

1. **Resolve M0-F1.** Define and document the canonical VS-01 evaluation database state, and
   decide between rebuilding from a full 7-entity ingestion or giving the malformed fixture its
   own `source_system`. This is an architecture decision, not an implementation detail, and it
   must precede M1 because M1 pins `Scope` and the acceptance fingerprint.
2. **Settle M0-F2** — decide whether `layer1_fingerprint` includes scoped `source_id` values.
   One line in M1's definition; expensive to change after five tables depend on it.
3. **Approve the documentation corrections** for M0-F3 through M0-F6 and M0-F8 — in particular
   M0-F4 and M0-F6, whose incorrect numbers would otherwise be copied into M3 and M9 tests.

### 19.2 Conditions that may be carried into M1

4. **M0-F5** — enumerate all four "Textiles" customers in the M4 link fixture.
5. **M0-F7** — state in M1 that no VS-01 signal is document-derived, and keep the
   leave-DOC-005-out test asserting exact equality of every signal value.

### 19.3 Standing constraints for all Layer 2 work

- Layer 1 stays frozen: invariants I4, I5, I6, I10 and I11 must be byte-identical after VS-01.
- No new canonical vocabulary value without an explicit recorded architecture decision (§5).
- No `now()` in any intelligence, analyst or decision module.
- No executor in VS-01–VS-05.
- Every asserted fact carries a resolvable citation.
- No new datastore without a slice whose question requires it.

**M1 is not started. No implementation work was performed.**
