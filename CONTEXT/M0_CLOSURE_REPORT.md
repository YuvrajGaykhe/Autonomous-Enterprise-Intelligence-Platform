# M0 — Remediation and Entry Gate: Closure Report
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**Executed: 2026-09-19 | Recorded by: Yuvraj Gaykhe**
**Status: DECISION / REMEDIATION ONLY. No production code, test, migration, schema, config, dataset or Docker file was modified. M1 is not started.**

> Companion documents: `CONTEXT/M0_BASELINE_REPORT.md` (the baseline this closes),
> `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`, `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md`,
> `CONTEXT/VS01_IMPLEMENTATION_PLAN.md`.

---

## 1. M0-F1 investigation

### 1.1 The question

Why does the live development database hold 220 rows over five entity types, with
`organizations` 0/1 and `documents` 0/12, plus four rows from the malformed fixture under
`source_system='csv_demo'`?

### 1.2 Root cause — this is not a defect

**The development database is the residue of `make verify-layer1`, not of `make ingest-demo`.**

Two deliberate, specified behaviours of the Layer 1 acceptance command produce exactly the
observed state.

**(a) The acceptance scenario ingests five of seven entity types by design.**

`scripts/verify_layer1.py:92`:

```python
#: The entity types the scenario ingests (spec Section 20 step E).
SCENARIO_ENTITIES = ("customers", "employees", "deals", "projects", "support_tickets")
```

`scripts/verify_layer1.py:363` posts exactly that list, and line 393 *asserts* the run covered
it and nothing else. 50 + 24 + 44 + 22 + 80 = **220**. `organizations` and `documents` are
outside the Section 20 step E scope and are therefore never ingested by the acceptance command.

This is documented, expected behaviour. `README.md:1249` shows the clean-database output verbatim:

```
verify-layer1: E-F  ingestion  PASS  run f245b8f6 SUCCESS: fetched 220 = 220 inserted + ...
                                     220 raw records persisted over 5 entity types
```

**(b) The malformed fixture is ingested through the `csv_demo` connector by design.**

`scripts/verify_layer1.py:488`:

```python
connector = build_connector("csv_demo", data_directory=BAD_FIXTURE_DIR)
```

Only the *data directory* is overridden; the connector's `source_name` stays `csv_demo`, so the
surviving fixture rows persist with `source_system='csv_demo'`. This too is required by the
scenario: step L asserts the valid fixture rows remain queryable **through the public API**, and
the API has no way to address a different source.

### 1.3 Evidence — the arithmetic closes exactly

`ingestion_runs` in the live database:

| Status | Runs | `records_fetched` each |
|---|---|---|
| SUCCESS | 1 | 220 |
| NOOP | 7 | 220 |
| PARTIAL_SUCCESS | 4 | 8 |

`verify_layer1` performs **two** scenario ingestions per invocation (steps E–F, then steps I–J
for idempotency) and **one** fixture ingestion. 4 invocations → 8 scenario runs (the first
SUCCESS, the rest NOOP) + 4 fixture runs. **8 = 1 + 7 and 4 = 4. The ledger closes with no
unexplained run.**

The 4 surviving fixture rows, as recorded from the live database before the rebuild, are
`CUST-901` and `CUST-902` (`CUST-903` rejected for `status='suspended'`, outside the D1
vocabulary; the duplicate `CUST-901` row deduplicated) and `DEAL-901` and `DEAL-902`
(`DEAL-903` rejected for the malformed amount `"12,50,000.00"`, `DEAL-904` for the date
`31/12/2026`). `DEAL-902` survives with a NULL `customer_id`: its `CUST-999` reference is
unresolvable, which is a WARNING under the E1 unresolved-FK rule, not a rejection. That is
3 rejected and 4 persisted per fixture run, matching `records_rejected = 3`.

### 1.4 Answers to the six questions

| # | Question | Answer |
|---|---|---|
| 1 | What produced the current DB? | ≥ 4 invocations of `make verify-layer1`. No `make ingest-demo` run is present — the row profile excludes it. |
| 2 | Why are organizations/documents absent? | `SCENARIO_ENTITIES` deliberately omits them (spec Section 20 step E). Not a bug. |
| 3 | Why does the malformed fixture exist? | Steps K–L require it, ingested via the `csv_demo` connector with an overridden `data_directory`. |
| 4 | Is the fixture created by an existing workflow? | **Yes** — `make verify-layer1`, the documented Layer 1 acceptance command. |
| 5 | Can the DB be deterministically rebuilt? | **Yes — proven.** See §1.5. |
| 6 | Does rebuilding change a Layer 1 contract? | **No.** It uses only existing commands; ingestion is the only write path into PostgreSQL (`README.md:551`). |

### 1.5 Demonstration of the supported rebuild path — performed, on a throwaway database

Executed against a **disposable probe database** (`ai_ceo_m0_probe`), never against the
development database, and dropped afterwards:

```bash
docker exec ai-ceo-postgres psql -U ai_ceo -d postgres \
  -c "DROP DATABASE IF EXISTS ai_ceo_m0_probe;" -c "CREATE DATABASE ai_ceo_m0_probe OWNER ai_ceo;"
export DATABASE_URL="postgresql://ai_ceo:changeme@localhost:5432/ai_ceo_m0_probe"
alembic upgrade head
python scripts/ingest_demo.py          # no --entities filter
```

Result:

```
status: SUCCESS   records_fetched: 233   inserted: 233   rejected: 0   entity types: 7
  organizations 1 · employees 24 · customers 50 · deals 44 · projects 22 · support_tickets 80 · documents 12
```

Re-run: `NOOP`, 233 unchanged, 0 inserted, 0 updated. `source_system` breakdown: `csv_demo` only,
**no fixture rows**.

`scripts/ingest_demo.py` needs no flags because `IngestionRequest.entities` defaults to `None`,
documented at `app/ingestion/orchestrator.py:102` as *"entities=None selects every entity the
source provides."*

**The whole procedure was then repeated from a fresh DROP/CREATE. All three candidate
fingerprints came back byte-identical (§2.4). The 233-row state is deterministically
reproducible.**

### 1.6 The correct lifecycle

```
clean database            docker compose down -v   (or DROP/CREATE a named database)
      ↓
schema                    alembic upgrade head          ← make migrate
      ↓
Layer 1 ingestion         python scripts/ingest_demo.py ← make ingest-demo, NO --entities filter
      ↓
233 canonical rows        7 entity types, 0 rejected, SUCCESS; re-run is NOOP
      ↓
deterministic verification  pin layer1_fingerprint; re-run must reproduce it
      ↓
VS-01
```

This is already what the VS-01 plan's own demo prescribes — **§A28: `make docker-up && make
migrate && make ingest-demo`** — *not* `make verify-layer1`. The plan was right; the practice
diverged.

> **`make verify-layer1` must not be used to prepare a VS-01 evaluation database.** It ingests 5
> of 7 entity types and then deliberately injects malformed-fixture rows into the `csv_demo`
> scope. It remains the correct and unchanged **Layer 1** acceptance command.

### 1.7 Options considered

| | Option A — rebuild the dev DB from the full dataset | Option B — isolate fixtures under a separate `source_system` / DB |
|---|---|---|
| Mechanism | `make migrate` + `make ingest-demo` on a clean database | Change `verify_layer1.py` to build the fixture connector under e.g. `csv_demo_bad`, or point it at its own database |
| Layer 1 freeze | ✅ untouched — existing commands only, proven on the probe | ❌ **modifies `scripts/verify_layer1.py`**, a released Layer 1 artifact |
| Deterministic reproducibility | ✅ proven — two independent rebuilds, identical fingerprints | ✅ but unproven, and changes the acceptance report's numbers |
| Provenance | ✅ unchanged | ⚠️ changes the `source_system` of fixture rows — a provenance semantics change |
| Test isolation | ⚠️ **not durable** — the next `make verify-layer1` re-contaminates | ✅ durable |
| VS-01 evidence availability | ✅ all 12 documents present | ✅ (orthogonal) |
| Existing Layer 1 tests | ✅ untouched | ❌ breaks `tests/e2e/test_i1_acceptance.py` and I1's fixture-source-id assertions; needs `config/connectors/` to gain a source |
| Connector contracts | ✅ untouched | ⚠️ a fourth `source_system` must enter `normalization.yaml` — **a D1 vocabulary change, which the project forbids** |
| Cost now | zero code | Layer 1 change → requires explicit approval, out of M0 scope |

**Decisive objection to B.** `config/mappings/normalization.yaml` declares the canonical
`source_systems` vocabulary as exactly `csv_demo`, `odoo_mock`, `rest_mock`, with one mapping
file per entry. Adding `csv_demo_bad` widens the D1 vocabulary — precisely the move binding #1 of
the project strategy prohibits ("Layer 1 stays frozen. Its D1 vocabulary is never widened to
satisfy an analytical need").

**Decisive objection to A alone.** A rebuild is a *state*, not a *guarantee*. Nothing stops the
next `make verify-layer1` from re-contaminating the same database, silently, five minutes later.

### 1.8 Chosen resolution — A + D (rebuild, plus a fingerprint guard)

**A. Adopt the §1.6 lifecycle as the documented VS-01 evaluation-state procedure**, and record
that `make verify-layer1` residue is not a valid VS-01 evaluation state. Zero code change, zero
Layer 1 impact, proven reproducible.

**D. Make contamination loud instead of durable.** Pin the expected `layer1_fingerprint` for
`ACCEPTANCE_AS_OF` in `config/intelligence/risk_rules.yaml` at M1, and have `make verify-vs01`
fail with a named message when the computed fingerprint does not match. A contaminated database
(220 rows, or 233 + 4 fixture rows) yields a different fingerprint and is **rejected at the door**
rather than silently producing a citation-free brief.

This pairing is entirely Layer 2. It needs no Layer 1 change, no new `source_system`, no D1
vocabulary widening, and no modification to `verify_layer1.py`.

**Option B is recorded as a future improvement requiring an approved Layer 1 change**, not
adopted now. It is the only durable fix at the source, but it costs a D1 vocabulary entry and an
I1 test rewrite — a decision for after VS-01, if ever.

> **Implementation note (NOT performed).** The development database was deliberately left in its
> contaminated state so this report's evidence remains reproducible. Rebuilding it is an M1 entry
> action for the operator, using the §1.6 commands.

---

## 2. M0-F2 analysis — `layer1_fingerprint`

### 2.1 The five concepts, distinguished

| Concept | Scope | Owner | Changes when |
|---|---|---|---|
| `record_hash` | **Business content of one row.** Excludes all provenance (`id`, `source_system`, `source_entity`, `source_id`, `source_updated_at`, `ingested_at`, `ingestion_run_id`) and the E1-resolved FKs | **Layer 1 — FROZEN** | a business field value changes |
| `canonical_id` | `uuid5(namespace, f"{source_system}:{source_entity}:{source_id}")` | **Layer 1 — FROZEN** | the source identity triple changes |
| `source_id` | The stable source identifier. **Provenance, therefore excluded from `record_hash`** | Layer 1 | the source renumbers a record |
| Provenance | The 8 universal columns; `ingested_at` / `ingestion_run_id` change on **every** ingestion | Layer 1 | any run touches the row |
| `layer1_fingerprint` | A **Layer 2 composition** identifying the Layer 1 snapshot an assessment was computed from | **Layer 2 — NEW** | (this is the design question) |

Verified: `app/normalization/contract.py` derives `PROVENANCE_FIELDS` from
`CanonicalBase.model_fields` and `BUSINESS_FIELDS` excludes them; `source_id` is on
`CanonicalBase`, so it is excluded from `record_hash` by construction.

### 2.2 Answers

**1. Purpose.** To make an assessment's identity depend on the Layer 1 snapshot it was computed
from, so a re-run after new ingestion cannot return stale intelligence through the uniqueness
constraint on `risk_assessments` (plan §A18, §0 defect 4).

**2. What should it represent?** Not "complete Layer 1 state" and not raw provenance —
`ingested_at` and `ingestion_run_id` change on every run, so including them would make every
re-ingestion produce a new fingerprint even when nothing changed, destroying idempotency. It must
represent **the semantic content *and the identity* of the scoped canonical rows**: everything
VS-01's answer depends on, and nothing that does not.

**3. Can `source_id` changes affect VS-01 correctness?** **Yes, decisively.** `source_id` is the
join key for every `SOURCE_KEY_JOIN` edge (owner, assignee, manager, document owner), it is the
input to `canonical_id`, it is what E1 resolves the three customer FKs against, and it is quoted
verbatim in `ID_TOKEN` document links and in brief citations. A `source_id` change re-keys rows,
re-resolves FKs and invalidates citations — while leaving every `record_hash` untouched.

**4. Can two different Layer 1 states share a fingerprint?** **Yes — demonstrated.** See §2.3.

**5. What does the plan assume?** §A5: *"SHA-256 over the scoped canonical `record_hash` values
and counts"*. M1 repeats it: *"computes the fingerprint over the scoped canonical `record_hash`
values and counts"*. Neither states an ordering, and neither mentions `source_id`.

### 2.3 Demonstration — the collision is real, and worse than M0 stated

Three candidate compositions were computed over the clean 233-row probe database, then recomputed
after simulating a `source_id` rename **in memory** (nothing was written):

| | Composition |
|---|---|
| **v1a** | `{entity: {count, sorted(record_hash values)}}` — the literal reading of §A5 |
| **v1b** | `{entity: {count, record_hash values sequenced by source_id}}` — the same words, plus an *unstated* ordering assumption |
| **v2** | `{entity: {count, (source_id, record_hash) pairs sorted by source_id}}` — identity-bound |

Baseline over the clean 233-row state:

```
v1a = 19ebfeeb6b4299df940cb15806383a8a83d84fe300f9e878205f118a89232739
v1b = e8491c8c7a85fb61b7b58688ac8dac0b5b08e65e76d5d12df20ae7a2712692b3
v2  = 1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00
```

| Scenario (business content byte-identical) | v1a | v1b | v2 |
|---|---|---|---|
| `CUST-007` → `CUST-999` (reorders the sequence) | **BLIND** | detected | detected |
| `CUST-007` → `CUST-007Z` (**preserves ordinal position**) | **BLIND** | **BLIND** | detected |

**The specified composition (v1a) is blind to every `source_id` rename.** The composition a
developer would plausibly write instead (v1b) is blind only to order-preserving renames — which
is worse in practice, because it would pass a casual sensitivity test while the hole stays open.

**The plan's own sensitivity tests do not catch this.** §A25 test 13 ("ingesting one extra ticket
changes the fingerprint") and M1's ("fingerprint changes when a record changes") both pass under
**all three** compositions, because both scenarios change a count or a hash. They create false
confidence.

### 2.4 Stability

| Property | Result |
|---|---|
| Deterministic across a full rebuild | ✅ DROP → CREATE → `alembic upgrade head` → `ingest_demo.py`, twice: all three fingerprints byte-identical |
| Independent of run ids, timestamps, UUIDs | ✅ by construction — `record_hash` and `source_id` carry no temporal provenance |
| Independent of database row order | ⚠️ **only with an explicit `ORDER BY`.** Recomputing over shuffled rows without re-sorting changed the value. PostgreSQL does not guarantee row order without one. |

### 2.5 Fingerprint decision — smallest defensible design

**Adopt v2. Change nothing in Layer 1.**

`layer1_fingerprint` is a **Layer 2 composition** computed by *reading* two frozen Layer 1
columns. Including `source_id` requires **no change to `record_hash`, no change to any Layer 1
module, no migration and no D1 vocabulary change.**

Definition to record in §A5 and M1:

> `layer1_fingerprint` = SHA-256 over the JSON serialisation of
> `{entity_type: {"count": n, "records": [[source_id, record_hash], ...]}}`
> for the seven canonical entity types within the scope, where each `records` list is **ordered
> by `source_id`** and the serialisation uses the same discipline as `record_hash`
> (`sort_keys=True`, `separators=(",", ":")`, UTF-8).
>
> It deliberately **excludes** `ingested_at`, `ingestion_run_id` and `source_updated_at`: those
> change on every ingestion, and including them would make an unchanged re-ingestion produce a
> new fingerprint, defeating the idempotency the fingerprint exists to protect.

Required accompanying test, replacing the one that cannot fail:

> **Fingerprint identity sensitivity.** Re-ingest one record under a changed `source_id` whose
> sort position is unchanged (e.g. `CUST-007` → `CUST-007Z`), with byte-identical business
> content. The fingerprint **must** change. Keep the existing count-sensitivity test as well.

**Layer 1 impact: none.** This is the smallest change that closes the hole.

---

## 3. F3–F8 verification, and one new finding

Each finding re-verified from the repository and the data. "Affects implementation?" means a
milestone test or acceptance criterion would encode the wrong value.

### F3 — exposure ranking and mixed-currency median · **CONFIRMED · documentation only**

**Where.** `AI_CEO_POST_LAYER1_STRATEGY.md:218-220` (§4.3); condensed into
`AI_CEO_PROJECT_CONTEXT.md:548-550` (§17.2).

**Text.** *"On weighted commercial exposure it is roughly twelfth: DEAL-001 is USD 5,361 against a
portfolio median of ~327,750, while CUST-031 carries ~1.77M of exposure with a single open
ticket."*

**Recomputed:**

| Claim | Verdict |
|---|---|
| "4 open tickets, 4 high priority, 4 in the last 30 days" | ✅ correct (4 / 4 / 4) |
| "the next-worst customer has 2 open" | ✅ correct (CUST-025 = 2) |
| "CUST-031 carries ~1.77M with a single open ticket" | ✅ correct (Vertex Foods, 1,766,000, 1 open) |
| **"roughly twelfth on weighted exposure"** | ❌ **CUST-007 is 22nd of 23** on mixed-currency weighted exposure. "Twelfth" is DEAL-001's rank among the **13 USD deals by raw amount** — a different measure. |
| **"against a portfolio median of ~327,750"** | ❌ compares a **USD** figure to the median of **all 44 deals across INR/USD/EUR**. `AI_CEO_POST_LAYER1_STRATEGY.md:141` labels that median "mixed currency"; §4.3 then uses it as if comparable. |
| "a blended score would surface Vertex Foods" | ⚠️ Vertex Foods is **4th**; the top is CUST-015 Unity Pharma at ~8.96M |

**Correction.** Replace the mixed-currency comparison with a currency-qualified one:

> On commercial exposure CUST-007 is near the bottom of the portfolio: 22nd of the 23 customers
> holding active deals on weighted exposure. Restricted to a single currency so the comparison is
> honest, DEAL-001 is 12th of the 13 USD deals by amount, and CUST-007's USD weighted exposure
> (4,825.30) is exactly the median of the 7 USD customers. A cross-currency portfolio ranking is
> not computable until VS-02 delivers the FX rate set. Meanwhile CUST-015 (Unity Pharma) carries
> ~8.96M of weighted exposure with no escalation at all — a blended score would surface it and
> bury Meridian.

**Affects implementation?** **No.** No milestone test cites these figures. §A15's ordering rule
("Money is never a sort key") and §A25 test 5 (amount invariance) are unaffected. The correction
**strengthens** the argument — 22nd is a stronger separation than 12th.

### F4 — `as_of` SLA-breach ranking misattributed · **CONFIRMED · context document only**

**Recomputed** (DOC-003 targets: high 1, medium 5 business days), total SLA breaches:

| `as_of` | Ranking |
|---|---|
| **2026-08-27** (the `max(created_at)` fallback) | **CUST-009 = 4, CUST-007 = 3** |
| **2026-09-18** (`ACCEPTANCE_AS_OF`) | CUST-007 = 5, CUST-009 = 4 |

**The VS-01 plan is CORRECT.** `VS01_IMPLEMENTATION_PLAN.md:24`: *"**At 2026-08-27** the
SLA-breach ranking differs (CUST-009 has 4, CUST-007 has 3)"* — accurate.

**Only the context document is wrong.** `AI_CEO_PROJECT_CONTEXT.md:592`: *"every value was
computed at 2026-09-18, **where** the SLA-breach ranking inverts (CUST-009 has 4, CUST-007 has
3)"* — the relative clause attaches the numbers to the wrong date. The error was introduced when
§17.5 condensed the plan's defect table.

**Correction.** `AI_CEO_PROJECT_CONTEXT.md:592` — replace *"computed at 2026-09-18, where the
SLA-breach ranking inverts"* with *"computed at 2026-09-18; **at the 2026-08-27 default** the
SLA-breach ranking differs"*.

**Affects implementation?** **No** — the plan, which drives M3 and M9, already states it
correctly. Correcting the context document prevents a future reader from re-deriving the error.

### F5 — four "Textiles" customers, not three · **CONFIRMED · affects an M4 test**

**Measured:** `CUST-002 Northstar Textiles`, `CUST-007 Meridian Textiles`,
**`CUST-039 Evergrid Textiles`**, `CUST-041 Westbrook Textiles`.

**Where.** `AI_CEO_POST_LAYER1_STRATEGY.md:440`; `VS01_IMPLEMENTATION_PLAN.md:187`;
and **`VS01_IMPLEMENTATION_PLAN.md:363`** — §A25 test 7: *"Westbrook and Northstar Textiles
acquire no Meridian link."*

**Correction.** Add Evergrid Textiles (CUST-039) in all three places; test 7 becomes
*"Westbrook, Northstar and Evergrid Textiles acquire no Meridian link."*

**Affects implementation?** **Yes** — §A25 test 7 is a named acceptance test. Written from the
current text it exercises 2 of the 3 available negative cases, under-testing the exact rule it
exists to protect. The design (token-boundary matching) is unchanged and already handles four.

### F6 — ticketless customers double-counted · **CONFIRMED · affects an M3/M9 test**

**Measured:** 15 ticketless customers of 50. All 4 inactive customers (CUST-002, 013, 027, 034)
have **zero tickets, zero deals and zero projects**, so they are a **subset** of the 15. The
split is 11 active-and-ticketless + 4 inactive = **15**.

**Where.** `VS01_IMPLEMENTATION_PLAN.md:325` (§A23) *"(15 such customers, plus the 4 inactive
ones)"* — implies 19. `VS01_IMPLEMENTATION_PLAN.md:366` (§A25 test 10) *"The 4 inactive and 15
ticketless customers yield `NONE`"* — same ambiguity.

**The strategy document is CORRECT**: `AI_CEO_POST_LAYER1_STRATEGY.md:143` reads *"Customers with
no tickets | 15 of 50"*.

**Correction.** §A23 → *"(15 such customers — 11 active plus all 4 inactive ones)"*.
§A25 test 10 → *"The 15 ticketless customers, which include all 4 inactive ones, yield `NONE`,
not worthy."*

**Affects implementation?** **Yes** — test 10 is a named acceptance test. `assert len(...) == 19`
would fail; worse, a developer might "fix" it by loosening the assertion.

### F7 — `ID_TOKEN` links may derive signals, and DOC-005 is one · **CONFIRMED · latent, documentation only**

**Verified.** §A11 (`VS01_IMPLEMENTATION_PLAN.md:182`) grants `ID_TOKEN` links *"May derive
signals: Yes"*, and DOC-005 matches CUST-007 by both `ID_TOKEN` and `EXACT_NAME`. DOC-005's body
states the conclusion in prose: *"raised 5 tickets between 2026-08-18 and 2026-08-27; 4 remain
open while deal DEAL-001 is in negotiation."*

**Latent, not active.** Every signal S1–S15 derives from `support_tickets`, `deals` or
`projects`. S14 (`contract_documents`) is marked "evidence only". **No signal is
document-derived**, so the leave-DOC-005-out test currently passes on substance.

**Already largely mitigated.** §A25 test 4 already requires *"band, every signal, the escalation
state and the resolution are byte-identical"* — exact equality of every signal, not just the
band. That is the correct strength.

**Correction (clarifying only).** Add to §A11: *"In VS-01 no signal is derived from any document
link; the `ID_TOKEN` permission is reserved for later slices. DOC-005 is an `ID_TOKEN` match and
states the conclusion in prose, so §A25 test 4 must keep asserting exact equality of every signal
value — it is what stops a future slice from quietly making the conclusion document-derived."*

**Affects implementation?** **No** behaviour change. It converts an unwritten assumption into a
stated invariant.

### F8 — stale documentation metadata · **CONFIRMED · documentation only**

| # | Location | Says | Actual | Correction |
|---|---|---|---|---|
| a | `AI_CEO_PROJECT_CONTEXT.md:3` | "Last updated: 2026-09-16" | Last modified by `6d7a1cd` on 2026-09-18; §17 is dated 2026-09-18 | → "2026-09-19" on the next edit |
| b | `AI_CEO_PROJECT_CONTEXT.md:296` | A3 — "all 11 migrations" | **2** revisions (`0001` no-op → `8bfd73b6af60`), creating **12** tables | → "Alembic setup + baseline migration" |
| c | `AI_CEO_PROJECT_CONTEXT.md:538` | "Only three canonical FKs exist" | Four canonical entity→entity FKs; three are *to customers* | → "Only three canonical FKs to `customers` exist … the only other canonical FK is `employees.organization_id`" |
| d | `AI_CEO_POST_LAYER1_STRATEGY.md:556` | approval stores `brief_content_hash` | Superseded by v2: approval binds to the **decision payload** hash (§A17) | → `payload_hash`, with a note that prose is a non-binding view |
| e | `AI_CEO_PROJECT_CONTEXT.md:318-319` | I1/I2 "Complete locally — not pushed" | Both pushed; `origin/main` = `945e0bb` descends from both | → "Complete — pushed" |
| f | **`VS01_IMPLEMENTATION_PLAN.md:439-441`** | M0 should "record the baselines (… `make verify-layer1`) and resolve the stray `README.md` working-tree edit" | **Both are wrong now.** `make verify-layer1` is precisely what contaminates the evaluation DB (§1.6); and no stray README edit exists — README last changed in `fff40f6`, working tree clean | → replace with the §1.6 lifecycle and drop the README clause |

Item **f** is new in this pass and is the most consequential of the eight: the plan's own M0
instruction would have reproduced M0-F1.

### M0-F9 (NEW) — `escalation_path(CUST-007)` omits an assignee · **CONFIRMED · affects an M2 test**

**Where.** `VS01_IMPLEMENTATION_PLAN.md` M2 tests: *"`escalation_path(CUST-007)` returns EMP-007
→ EMP-002 plus **EMP-018/020/021** → EMP-004"*.

**§A9 defines** `escalation_path(customer)` as *"account owner → manager, plus **each open
ticket's assignee** → manager"*.

**Measured — CUST-007 has 4 open tickets with 4 distinct assignees:**

| Ticket | Priority | Assignee | Manager |
|---|---|---|---|
| TKT-075 | high | EMP-018 Rahul Agarwal | EMP-004 |
| TKT-076 | high | EMP-021 Rohan Rao | EMP-004 |
| **TKT-079** | **medium** | **EMP-017 Tomas Sinha** | EMP-004 |
| TKT-080 | high | EMP-020 Aditya Mathur | EMP-004 |

Account owner EMP-007 Vikram Pillai → manager EMP-002 Isha Khan ✅ correct.

**EMP-017 is missing from the plan's list.** The three listed (EMP-018/020/021) are exactly the
assignees of the three open **high-priority** tickets — the plan applied an
open-high-priority filter where §A9 says *each open ticket*.

**Correction.** M2 test → *"`escalation_path(CUST-007)` returns EMP-007 → EMP-002 plus
EMP-017/018/020/021 → EMP-004."* Either that, or amend §A9 to say "each open **high-priority**
ticket's assignee" — but the four-assignee reading is the one that matches §A9 as written, and
TKT-079 is the open `billing` ticket that drives `REVIEW_INVOICE_DISPUTE`, so its assignee
belongs in the escalation path.

**Affects implementation?** **Yes** — it is a named M2 acceptance test. It would assert 3 where
the specification yields 4.

---

## 4. Exact documentation corrections required

None have been applied. All are documentation-only; none changes VS-01's architecture.

| # | File | Line(s) | Change | Affects a test? |
|---|---|---|---|---|
| 1 | `AI_CEO_POST_LAYER1_STRATEGY.md` | 218–220 | F3: currency-qualified exposure wording | no |
| 2 | `AI_CEO_PROJECT_CONTEXT.md` | 548–550 | F3: same, condensed | no |
| 3 | `AI_CEO_PROJECT_CONTEXT.md` | 592 | F4: attach the numbers to 2026-08-27 | no |
| 4 | `AI_CEO_POST_LAYER1_STRATEGY.md` | 440 | F5: add Evergrid Textiles | no |
| 5 | `VS01_IMPLEMENTATION_PLAN.md` | 187 | F5: add Evergrid Textiles | no |
| 6 | `VS01_IMPLEMENTATION_PLAN.md` | 363 | F5: §A25 test 7 → three negative cases | **yes** |
| 7 | `VS01_IMPLEMENTATION_PLAN.md` | 325 | F6: §A23 → "15 … 11 active plus all 4 inactive" | no |
| 8 | `VS01_IMPLEMENTATION_PLAN.md` | 366 | F6: §A25 test 10 → 15, inclusive | **yes** |
| 9 | `VS01_IMPLEMENTATION_PLAN.md` | 182 + §A11 | F7: state that no VS-01 signal is document-derived | no |
| 10 | `AI_CEO_PROJECT_CONTEXT.md` | 3, 296, 318–319, 538 | F8 a/b/c/e | no |
| 11 | `AI_CEO_POST_LAYER1_STRATEGY.md` | 556 | F8 d: `payload_hash` | no |
| 12 | `VS01_IMPLEMENTATION_PLAN.md` | 439–441 | F8 f: replace the M0 instruction with the §1.6 lifecycle | no |
| 13 | `VS01_IMPLEMENTATION_PLAN.md` | M2 tests | F9: EMP-017/018/020/021 | **yes** |
| 14 | `VS01_IMPLEMENTATION_PLAN.md` | §A5, M1 | F2: identity-bound fingerprint definition + ordering + exclusions | **yes** |
| 15 | `VS01_IMPLEMENTATION_PLAN.md` | §A25 test 13, M1 tests | F2: add the identity-sensitivity test | **yes** |
| 16 | `VS01_IMPLEMENTATION_PLAN.md` | §A27, §A28 | F1: clean-database precondition + pinned fingerprint gate | **yes** |

**Six corrections (6, 8, 13, 14, 15, 16) change a named test or acceptance criterion.** These are
the ones that would otherwise be encoded wrong in code.

---

## 5. Grilling results

Performed manually. The project's `grilling` / `grill-me` / `grill-with-docs` skills are listed in
`skills-lock.json` but **no `skills/` directory exists in the repository and none is an invocable
skill in this session**, so the adversarial pass was conducted directly.

### F1

| Challenge | Answer |
|---|---|
| Could the DB solution accidentally modify Layer 1? | **No.** `alembic upgrade head` + `scripts/ingest_demo.py` are existing released commands; README states ingestion is the only write path into PostgreSQL. Demonstrated on a throwaway database, then dropped. No repository file, schema, migration or config was touched. |
| Could test fixtures contaminate demo data? | **Yes — and they already have. This is the real risk, and it is inherent.** `verify_layer1.py:488` ingests the fixture through the `csv_demo` connector by design, so *any* future `make verify-layer1` re-contaminates. A one-off rebuild is therefore **necessary but not sufficient** — which is exactly why the chosen resolution pairs it with the fingerprint gate (D), so contamination fails loudly instead of silently. |
| Could a future developer reproduce the 233-row state? | **Yes — proven twice.** Two independent DROP→CREATE→migrate→ingest cycles produced byte-identical fingerprints under all three compositions. |
| Could the chosen resolution hide the problem instead of fixing it? | It does not fix the *source* — `verify_layer1` still contaminates. It makes the consequence **undeployable**: VS-01 refuses to assess against an unexpected fingerprint. Option B is the source fix and is recorded as requiring an approved Layer 1 change. |

### F2

| Challenge | Answer |
|---|---|
| Could the proposed fingerprint create false confidence? | **The *specified* one already does.** §A25 test 13 and M1's fingerprint test both pass under all three compositions, so neither can ever detect the defect. v2 plus the new identity-sensitivity test closes it. |
| Could provenance changes escape detection? | **Deliberately, yes — and correctly.** v2 covers *identity* provenance (`source_id`). It excludes *temporal* provenance (`ingested_at`, `ingestion_run_id`, `source_updated_at`), which changes on every ingestion; including it would make an unchanged re-ingestion mint a new assessment, destroying the idempotency the fingerprint exists to protect. This trade-off must be stated in §A5, not left implicit. |
| Could the fingerprint become unstable across machines? | **Only if the ordering is left implicit.** Shuffling row order without re-sorting changed the value; PostgreSQL guarantees no order without `ORDER BY`. The definition therefore mandates ordering by `source_id` and the `record_hash` serialisation discipline. With those pinned it was byte-identical across two independent rebuilds. |
| Does v2 require a Layer 1 change? | **No.** It is a Layer 2 composition over two frozen, already-persisted columns. `record_hash` is untouched. |

### F3–F9

| Challenge | Answer |
|---|---|
| Could an incorrect number become an acceptance criterion? | **Yes, and three already are**: F5 → §A25 test 7; F6 → §A25 test 10; F9 → M2's `escalation_path` test. F3 and F4 are narrative only. |
| Could a later implementation encode the wrong number into tests? | **Yes** — and F9 is the clearest case: a developer implementing §A9 correctly (four assignees) would see the M2 test fail and might "fix" the *implementation* to match the wrong test, silently narrowing `escalation_path` to high-priority tickets only. |
| Could the corrections alter the intended VS-01 narrative? | **No.** F3 strengthens it (22nd of 23 separates risk from money more sharply than "twelfth"). F4 reinforces pinning `as_of`. F5/F6/F9 widen test coverage. F7 makes an existing invariant explicit. F1/F2 harden identity. **The conflict, the escalation, CUST-007, DEAL-001 and every S1–S15 value are unchanged.** |
| Is the M0 baseline itself trustworthy? | Re-verified independently this session: the 233/220 split, the fixture rows, the FK set, the vocabulary, and every §4.3 sub-claim. Two M0 statements were **refined**: M0-F1 is not a defect but the specified behaviour of `verify_layer1`; M0-F2 is worse than stated (v1a is blind to *all* renames, not just some). One new finding (F9) and one new F8 row (f) were added. |

---

## 6. Remaining risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | `make verify-layer1` re-contaminates any database it is run against. The chosen resolution detects this but does not prevent it. | Medium | Fingerprint gate (§1.8 D) fails loudly; Option B recorded as the source fix, pending approval |
| R2 | The pinned `layer1_fingerprint` cannot be fixed until M1 chooses the composition and a clean database exists — so it is a chicken-and-egg at M1 start | Low | M1 computes it on a freshly rebuilt DB and writes it into `config/intelligence/risk_rules.yaml` as its first act |
| R3 | v2 is blind to `source_updated_at` and to a canonical FK re-resolving without any content or count change | Low | Accepted and stated. FK resolution is a pure function of the scoped `source_id` set, which v2 covers; `source_updated_at` is not read by any VS-01 signal |
| R4 | Business-day arithmetic has no holiday calendar | Low | Pre-existing, documented in §A24; deterministic and reproducible |
| R5 | Approver identity is asserted, not verified | Accepted | No authentication exists by design; documented as a hard prerequisite before any executor |
| R6 | Corrections 1–16 are not yet applied, so a reader of the current documents can still derive the wrong numbers | Medium | Listed exactly in §4; must be applied before the affected milestone |

---

## 7. M1 entry conditions

| # | Condition | Status |
|---|---|---|
| E1 | Development database rebuilt via §1.6 (`make migrate` + `make ingest-demo`, **no** `--entities`, **not** `make verify-layer1`), showing 233 rows over 7 entity types | **operator action — not performed** (state preserved as evidence) |
| E2 | `layer1_fingerprint` composition decided: **v2, identity-bound** (§2.5) | decided here; **needs sign-off** |
| E3 | Documentation corrections 6, 8, 13, 14, 15, 16 applied (the test-bearing ones) | **not applied** |
| E4 | Documentation corrections 1–5, 7, 9–12 applied | **not applied** |
| E5 | Layer 1 invariants re-verified unchanged (I4, I5, I10, I11 of the baseline report) | ✅ verified this session |
| E6 | Layer 1 suite green | ✅ 4139/4139 at M0 |

---

## 8. Explicitly NOT changed

- **No file under** `app/`, `tests/`, `migrations/`, `config/`, `data/`, `docker/`.
- **No** `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `Makefile`, `alembic.ini`, `README.md`.
- **No** dependency added; no `LLM`, no Neo4j, no vector store, no API, no VS-01 module.
- **No** Layer 1 contract, schema, migration, vocabulary or `record_hash` semantics.
- **No** change to `scripts/verify_layer1.py` — Option B was rejected for now, not implemented.
- **No** row inserted, updated or deleted in the development database; it remains in its
  contaminated state (52 customers, 0 documents, 12 runs) so this report's evidence stays
  reproducible.
- **No** context, strategy or VS-01 plan document edited — every correction is *specified* in §4
  and *applied* nowhere.
- **No** commit, push, amend, rebase, reset or ref change.
- The throwaway probe database `ai_ceo_m0_probe` was created and **dropped**; only
  `ai_ceo_layer1` and `ai_ceo_layer1_test` remain.
