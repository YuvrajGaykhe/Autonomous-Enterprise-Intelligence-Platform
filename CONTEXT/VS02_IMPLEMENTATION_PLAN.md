# VS-02 — Revenue & Pipeline Intelligence (FX): Implementation Plan (v2.1)
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**v1 2026-10-01, drafted from the VS-02 Takeover Audit · v2 2026-10-01, after the adversarial
consistency audit of v1: four blocking and twenty-nine non-blocking findings repaired (§0.3) ·
v2.1 2026-10-01, after the owner's decisions: the rate set is configuration (SD-2), the table
alternative is removed, and three clarifications are made (§0.10)**

**Status of this document: APPROVED BY THE OWNER on 2026-10-01 for commit as
`VS-02: finalize specification`. Specification only. The owner's decisions are recorded in §0.10.**
**Nothing in it is built. No code, test, migration, configuration, frontend or README file was changed
to produce it.**

| Milestone | Status | Evidence |
|---|---|---|
| **VS02-M0** — pre-flight baseline | COMPLETE (2026-10-01) | §0.11; measured at `b0fcaa2`; recorded by the commit `VS-02: record the M0 baseline` |
| **VS02-M1** — FX foundation | COMPLETE (2026-10-05) | §B6; T-VS02-1a and T-VS02-3a applied; gate of §B5 measured on 2026-10-05: 7311 tests, `app/` 100%; recorded by the commit `VS02-M1: add the FX foundation` |
| **VS02-M2** — pipeline facts and aggregation | NOT STARTED | — |
| **VS02-M3** — concentration, risk-band cross-tabulation, the view | NOT STARTED | — |
| **VS02-M4** — API | NOT STARTED | — |
| **VS02-M5** — acceptance, evaluation and hardening | NOT STARTED | — |

Part A is specification and is **not** a record of what is built. A milestone is complete only when
this table says so and names a commit. No milestone begins until the previous one is complete and
approved, and **VS02-M0 does not begin until this file is committed on its own.** M0 is then a
separate task and begins only on the owner's instruction. The rate set's date and source note (U-1)
are an owner input during M0 (§B6): M0 cannot close without both, and VS02-M1 cannot begin until M0
closes.

> Strategy context: `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md` §6.3, §10.2 (status **PROPOSED**)
> VS-01 specification and conventions: `CONTEXT/VS01_IMPLEMENTATION_PLAN.md`
> Project state: `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`
>
> **Layer 1 and VS-01 (M1–M9) are frozen.** This slice adds new packages, new configuration files
> and one new route. It adds no table and no migration (SD-2). It changes no canonical schema, no
> existing migration, no existing route contract, no D1/D2 semantics and no frontend file. The only
> edits to frozen files are the additive ones §B1 lists and the test evolutions §B2 lists, each of
> which needs the owner's authorisation. VS-01's acceptance command is not edited, so M9 is not
> reopened.

---

## Labels

Every normative statement carries exactly **one** label. A tag in a heading covers every item under
it that carries no tag of its own; an item's own tag replaces the heading's.

| Tag | Label | Meaning |
|---|---|---|
| **[R]** | **REQUIRED** | Binding without a further choice inside VS-02. The source is named. |
| **[SD-n]**, **[MD-n]**, **T-VS02-n** | **PROPOSED OWNER DECISION** | Authored by this specification where no authority exists. Every one has an id and is listed in §0.6 (six shaping decisions), §0.7 (methodology) or §B2.1 (edits to frozen tests). It binds nothing until the owner approves it. |
| **[U-n]** | **UNKNOWN/OPEN** | No authority exists and this specification proposes no value. §0.9 states what closes it. |

**Standing in v2.1.** On 2026-10-01 the owner decided SD-1…SD-6 and approved MD-1…MD-22 as specified
(§0.10). They bind as written. Their tags stay on the statements they govern, so that §0.8 can still
say what a later change would reopen. The owner also authorised exactly ten T-VS02 rows (§B2.1).
U-1 was open in part in v2.1; the owner supplied its date and source note at VS02-M0, and it is
closed (§0.9, §0.11).

**What makes a statement REQUIRED.** Two kinds of source:

1. *Frozen authority*: frozen code, a frozen test, the VS-01 plan, or a project-wide binding. These
   bind now.
2. *The brief*: strategy §10.2 and §6.3. Their own status is PROPOSED, so they bind nothing by
   themselves. This plan adopts their content, and it becomes binding when the owner approves this
   plan. One statement of the brief is deliberately **not** adopted as REQUIRED and was put to the
   owner instead, because executing it literally collides with frozen surfaces: the word "table" in
   §6.3. The owner decided it under SD-2: the rate set is configuration, not a table.

**Outcome and mechanism.** Where a REQUIRED outcome is realised by a proposed mechanism, they are
two statements with two tags. No statement carries two.

Facts are marked **OBSERVED** (measured on 2026-10-01 from the repository or `data/demo/`) or
**RECORDED** (taken from an earlier phase record and not re-measured).

---

## 0. Basis: what the takeover audit established

### 0.1 Baseline

| Item | Value | Standing |
|---|---|---|
| HEAD and `origin/main` | `523210a` ("F6: polish the demo"), 0 ahead, 0 behind | OBSERVED |
| Working tree | `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md` modified (the owner's uncommitted change); `.claude/` untracked | OBSERVED |
| Backend against VS-01 closure `17de05f` | `app/`, `config/`, `migrations/`, `data/`, `tests/`, the Docker files and `pyproject.toml` are identical. `scripts/secret_scan.py` differs by 2 lines (F1 owner ruling) | OBSERVED |
| Migration head | one head, `070e4968a497` | OBSERVED |
| Backend suite | 6771 tests (unit 5287, contract 185, integration 1214, e2e 85), 0 skipped; `app/` coverage 100% over 7456 statements; ruff 69; mypy 9; secret scan 0; 2 warnings, with an intermittent third the owner ruled passes | RECORDED (F6 gate) |
| Golden brief | sha256 `87d1398661b0c30037ddc33e9acfd36db321ac9d0a36e04eadc3be9039ea9dce` | RECORDED |
| API | 28 operations; six under `/api/v1/risk`; three writes | OBSERVED |
| Development database | at `070e4968a497`, holding 52 customers and 46 deals. It is not the pinned 233-row snapshot. Context only: VS-02 never reads it (§B4) | OBSERVED |
| Hosted site | deployed from `523210a` (Vercel, Neon). Context only | RECORDED |

### 0.2 The authority for VS-02

The repository holds no VS-02 specification. Everything it states is:

1. Strategy §10.2 (the brief): objective, executive question, new capability, data requirement, key
   constraints, four acceptance clauses and the out-of-scope list.
2. Strategy §6.3 (the brief): an `fx_rates` reference table `(currency, as_of_date, rate_to_base,
   rate_set_version)`, a declared base currency, every monetary aggregate reporting base currency and
   rate-set version, and the rate set labelled a stated assumption.
3. Strategy §11: FX normalization is **shared** infrastructure, introduced in VS-02.
4. VS-01 plan §A12 and `app/intelligence/money.py`: `MoneyValue` is the seam FX plugs into "without
   touching any VS-01 call site".
5. VS-01 plan §A9.1 and `app/relationships/model.py`: `deal_owned_by` is substrate for VS-02's
   per-owner aggregation.
6. VS-01 plan §A30: VS-02 is the first later consumer of `Scope`, the relationship model, the
   evidence/citation contract and `MoneyValue`. It is **not** listed as a consumer of the analyst
   contract, the conflict policy, the action catalogue or the decision record.
7. The project-wide bindings: one `source_system`; explicit `as_of` and no `now()`; deterministic
   through VS-03; no executor; no datastore introduced without a slice whose question requires it;
   Layer 1 vocabulary never widened; every asserted fact citable; risk and money never blended
   (strategy §2.4, §2.7, §4.1, §4.3, §9.1, §14; context §17.3).
8. Frontend specification §9.1 and §9.13: the Pipeline Room is locked, "Opens with VS-02", and
   unlocking it is "part of the future slice's own frontend phase".

Items 3–8 are frozen authority. Items 1–2 are the brief (Labels, above). Anything this document
states beyond those eight sources is a PROPOSED OWNER DECISION or UNKNOWN/OPEN, and says so.

### 0.3 What v2 changed, and why

v1 was audited adversarially on 2026-10-01. The audit found four blocking findings (B), twenty-nine
non-blocking (N) and eight informational (I). Every one is answered here. None was dismissed.

| # | Finding in v1 | Resolution in v2 | Where |
|---|---|---|---|
| **B-1** | The DOC-004 leave-out test required an unchanged `view_hash`, but the view embeds the scope, whose fingerprint covers documents | The test compares every view key except `scope`, and asserts that the scope and the hash **do** change. The overclaims "never an input: any document" and "cannot read a document" are corrected | §A5, §A18.4, §A25 test 3, §A26 criterion 4 |
| **B-2** | `tests/unit/test_m8_api_schemas.py:68` pins the exact `ErrorCode` list; no evolution covered it | **T-VS02-10**, explicitly authorised evolution. No existing code is reused | §B2 |
| **B-3** | Evolutions were scheduled at M4 though the tests fail at M1 and M2, against a zero-failure gate | A milestone-by-milestone schedule, a gate rule, and T-VS02-1 and T-VS02-3 split into dated steps | §B2.2, §B5 |
| **B-4** | The hashed, typed view left field names and shapes to the implementer | §A14 freezes every object, field, type, nullability, order and empty state. Limitation texts are normative here | §A13, §A14 |
| N-1 | "No new datastore" stated absolutely | Restated as the authority has it | §0.2(7), §A30 |
| N-2 | PROPOSED strategy text cited as REQUIRED | The Labels section defines the brief's standing and the one exception | Labels |
| N-3 | Dual labels; proposals without ids | One tag per statement; MD-18…MD-22 added; every proposal has an id | throughout, §0.7 |
| N-4 | Unpinned scope labelled REQUIRED; base-labelling test labelled proposed | The unpinned route scope is MD-10; test 5 is REQUIRED | §A6, §A25 |
| N-5 | Owner approval surface incomplete | MD-21 puts the path table, including every edit to a frozen file, to the owner. The final table is complete | §B1, Owner Decisions |
| N-6 | "Striking one item reopens only its section" | Replaced by a dependency matrix | §0.8 |
| N-7 | "Exactly one module accepts a session" against `service.py` | Two named modules, neither writes | §A19, §A22.2 |
| N-8 | Import lists omitted the logger and FX errors | Exhaustive first-party allow-lists per module group | §A22.4 |
| N-9 | "Loaded at start" against lazy loading | Lazy, cached, never at import or startup; `app/main.py` untouched; isolation test | §A7.3, §A25 test 26 |
| N-10 | Two files named a rate-set version | One source: the authored rate file. `pipeline_rules.yaml` no longer names one. Digest pins accumulate in a test | §A7.3, §A7.4, §A22.3 |
| N-11 | `source_note` outside the digest | One identity rule: the digest covers every authored field | §A7.4 |
| N-12 | Precedence of the two 409s undefined; second code under no decision | A fixed evaluation order. v2.1 leaves one new code, `FX_RATE_MISSING`, under MD-14 | §A17.1 |
| N-13 | Missing rate named one currency in one place and several in another | A pre-check collects every missing currency, ascending. Test 9 and its fixture agree | §A7.5, §A17, §A25 |
| N-14 | Tests asserting HTTP status sat before the route existed | Every named test states its level and the milestone at which it first passes | §A25, §B6 |
| N-15 | Dense months unbounded by `as_of` | A fixed twelve-month horizon; always fifteen period buckets | §A10.4 |
| N-16 | Concentration's customer partition, top-N and cumulative points unreconciled | `by_customer` is a sixth partition; N and the cumulative points are constants; fewer holders defined | §A11, §A12.6, §A14.7 |
| N-17 | "Valued equals VS-01's describable deal on any data" | Corrected: they differ for a negative amount. Test 17 says so | §A8.3, §A25 |
| N-18 | Unknown band; band order without `RiskBand` | Vocabulary and rank come from the frozen `RiskBand`; an unknown stored band fails closed | §A12.3 |
| N-19 | Note semantics incomplete | Every code's trigger, scope and shape fixed | §A13.2 |
| N-20 | Typed response against the hashed object | A stated chain: canonical object → canonical JSON → hash → served value, with a test | §A14.10 |
| N-21 | "No free text"; prose inside the hash | Wording corrected. Limitation text is rendered outside the hash, as VS-01 separates payload from narrative | §A13.1, §A14.10, §A21 |
| N-22 | Golden limitations text with no allowed path | No golden file. The texts are normative in §A13.1 and asserted as literals | §A13.1 |
| N-23 | M0: dev database, census method, no commit, warning ruling | An M0 procedure; the census works on a discarded copy; an M0 commit; the ruling carried forward | §B5, §B6 |
| N-24 | T-VS02-6 allowed re-quoting lint counts the gate fixes | T-VS02-6 withdrawn. ruff 69 and mypy 9 are fixed | §B2 |
| N-25 | Makefile details | One help line per new target. The rest of this finding concerned the table alternative, removed in v2.1 | §B1 |
| N-26 | Acceptance command needed a mutated corpus and rate set | It checks only what is observable on its clean database; mutations stay in named tests it runs. Ingest is in process | §A27 |
| N-27 | "Stored equals stated" undefined for `customer_id` | A per-field resolution rule | §A18.2 |
| N-28 | Mutation targets omitted the band read and the view | Targets extended | §A28 |
| N-29 | "Unknown parameter value" undefined | Unknown query parameters are ignored, as on every existing GET route | §A15 |
| I-1 | An edit to VS-01's acceptance command reopens M9 | Moot in v2.1: with no migration (SD-2) that command is not edited | header, §B1 |
| I-2 | Duplicated lists | Out of scope lives only in §A30. §A29 is the documentation superset of §A13.1 | §A3, §A29, §A30 |
| I-3 | D-12 misstated the edited files | Corrected | §0.4 |
| I-4 | SD-5's rejection path omitted VS-01's own write pin | Added | §0.6 |
| I-5 | Appendix 2 had no date or note | U-1 names all four authored fields | §0.9, Appendix 2 |
| I-6 | `pipeline_version` had no content pin | A methodology digest pinned per version | §A22.3 |
| I-7 | Owner question on the proposal presupposed its answer | Both answers have a path | Owner Decisions |
| I-8 | Whether Layer 1 admits the fixture rows was unverified | The fixture package allows both forms, and M2 measures which each needs | §A24 |

**Also changed while repairing, and by the second pass over v2:**

- The stage order. The D1 vocabulary is an unordered set, so v1's "vocabulary order" was
  unimplementable; it is ascending by code point (§A10.2).
- `rate_set_version` was removed from `versions`, because `fx` already carries it (§A14.3).
- v1's demonstration question in §A2 was removed; it carried a proposal with no id.
- The leave-out test now fixes how its two arms are built. Removing a document moves the
  fingerprint, so assessments made before the removal no longer join; each arm is assessed after its
  corpus is fixed (§A18.4).
- Deal-level notes are produced where deals are classified, in `facts.py`, so the tests that assert
  them can pass at M2 (§A22.2).
- The import allow-list excludes VS-01's signal engine and band table by name (§A22.4).
- `tests/unit/test_vs02_boundary.py` exists from M1 and grows with each milestone (§B6).
- T-VS02-2 gained a second part. The same frozen file holds a per-operation response-model map that
  raises on an operation it does not list; the second pass found it by reading (§B2.1).
- The acceptance criteria and the out-of-scope list were relabelled: only what an authority states
  is REQUIRED (§A26, §A30).

### 0.4 Record of v1's internal attack

Kept as history. Twenty-one defects were found in the first draft; the resolutions stand, with three
corrected by §0.3 and one, D-1, made moot by SD-2.

| # | Defect in the first draft | Resolution |
|---|---|---|
| D-1 | Rates seeded by the migration; the frozen harness truncates every table before each test | Moot in v2.1: the rate set is configuration, with no table and no migration (§A7.6) |
| D-2 | Conversion at aggregate level breaks additivity | Per-deal rounding (MD-3, MD-4) |
| D-3 | Default `Decimal` context can round silently | A fixed arithmetic context (§A9.1) |
| D-4 | VS-01's `DealSignal` drops incomplete deals silently | VS-02's own `DealFact`; unvalued deals reported (MD-2) |
| D-5 | The scope's ticket-derived `as_of` fallback | `as_of` required (MD-10) |
| D-6 | Joining bands through a query that mixes snapshots | An exact-identity read (MD-9) |
| D-7 | No assessment read as `NONE` | `UNASSESSED` and `UNLINKED` buckets |
| D-8 | Ordering by band × exposure | Lexicographic order only (§A12.4) |
| D-9 | Reading DOC-004 in production | Test-only comparison and a leave-out test, corrected by B-1 (§A18.4) |
| D-10 | Shares dividing by zero | `null` with a reason (§A11) |
| D-11 | A random `assessment_id` in the view | No database id in the view |
| D-12 | Editing `schemas.py` and VS-01's M7/M8 boundary tests | A new response-model module and VS-02's own boundary test. The frozen files that **are** edited are those of §B1 and §B2 |
| D-13 | A rates route, won totals, manager roll-up, drill-down, history, pagination, a brief | Removed (§A30) |
| D-14 | A rate required for every currency | Only for a currency of an open valued deal |
| D-15 | The name "risk-adjusted" | Retired (SD-3) |
| D-16 | The `as_of` month split ambiguously | `OVERDUE` is strictly before `as_of` |
| D-17 | A fiscal calendar assumed | Calendar months (MD-6) |
| D-18 | Two base figures for one bucket | One; a hand-check bound instead (§A9.4) |
| D-19 | Shares shown without their dependence on the rates | Named in the block and as a limitation |
| D-20 | Relying on the frozen GET sweeps for the new route | VS-02's own route tests (§A25 tests 24–26) |
| D-21 | The scope fingerprint moves when only a ticket changes | Accepted and stated (§A29) |

---

## 0.5 Contradictions resolved

| # | Contradiction | Resolution | Label |
|---|---|---|---|
| X1 | The brief (§6.3) names an `fx_rates` **table**; a new migration breaks `scripts/vs01_acceptance.py:146` (`EXPECTED_HEAD`) and `tests/integration/test_m8_migration.py:218`, both frozen | The rate set lives in versioned configuration. No migration is added, so neither pin is touched | [SD-2] |
| X2 | The brief says "risk-adjusted pipeline view"; strategy §4.3 says risk and impact are never blended, and plan §A25 test 5 pins it | A cross-tabulation: exposure summed per band. No amount is adjusted by a band | [SD-3] |
| X3 | Strategy §1.1 says every slice crosses the decision layer; the brief names no analyst, brief or decision; plan §A30 does not list VS-02 as a consumer of them | VS-02 produces a read model and proposes no action | [SD-4] |
| X4 | The brief is PROPOSED; context §17's heading says "PLANNED". The strategy header still shows VS-01 at M1–M3. Strategy §10 lets a slice begin only when its predecessors are accepted | This plan is the re-grilling. The strategy document is never touched. Whether VS-01 is accepted is the owner's statement | [U-3] |
| X5 | A pipeline "as of" a date, when deals carry no history | `as_of` does not rewind deals (§A6) | [R] |
| X6 | VS-01 silently skips an incomplete deal; plan §A23 forbids silent drops | Counted and reported | [MD-2] |
| X7 | The frontend plan hires slice agents "after F7"; spec §9.13 makes unlocking part of the slice's own frontend phase | No frontend work in this plan | [SD-6] |
| X8 | The development database is not the pinned snapshot | VS-02 never reads or writes it | [R] |
| X9 | "FX plugs into `MoneyValue`"; three frozen test files pin that cross-currency `+` raises | `MoneyValue` is unchanged; conversion is a separate explicit function | [R] |
| X10 | Per-owner aggregation needs `deal_owned_by`; M2 is frozen at three public queries | VS-02 reads the edge through the exported `edges_of_type`, from its own package | [R] |
| X11 | A migration-seeded table against the harness's per-test truncate | Does not arise: there is no table | [SD-2] |
| X12 | Strategy §2.7 lists an environment-variable step in `as_of` resolution; the frozen `resolve_scope` has none | The frozen implementation stands; VS-02 passes `as_of` explicitly | [R] |

---

## 0.6 The six shaping decisions

The audit proposed a default for each. The owner decided all six on 2026-10-01 (§0.10). Each entry
records the decision and keeps what a different answer would have changed, because §0.8 still
governs a later change.

### SD-1 — Base currency

- **Decision (2026-10-01).** Approved: the base currency is **INR**.
- **Audit default.** Base currency **INR**, with an authored rate set labelled a stated assumption.
- **Why INR.** 30 of 44 deals are INR, and DOC-004 reports its pipeline figure in INR. OBSERVED.
- **If approved.**
  - INR amounts convert at exactly 1, so the INR base figure equals DOC-004's figure.
  - The base currency is data in the rate set, not code. A different base later is a new rate-set
    version and no code change.
  - Two further rates must exist, USD and EUR, because open valued deals hold only INR, USD and EUR.
    OBSERVED.
- **If rejected.** Name the base currency. A rate is then needed for every one of INR, USD and EUR
  that is not the base. Every base figure in Appendix 2 changes; no section of Part A changes.
- **What SD-1 does not settle.** The rate values, their date and their source note: **U-1**.

### SD-2 — Where the rate set lives

- **Decision (2026-10-01).** Configuration. The rate set lives only in
  `config/intelligence/fx_rates.yaml`, loaded lazily on first use (§A7.3, §A7.6).
- **What follows.**
  - No table, model, repository, migration or registration command; no change to `demo-reset`; no
    hosted database step.
  - No frozen migration, table-set or head pin is touched, and VS-01's acceptance command is not
    edited.
  - It departs from the brief's word "table" (§0.5 X1). A later slice that must join rates in SQL
    (VS-06's projection) adds the table then, with its own specification.
- **History.** v2 specified two alternatives. One was the brief's `fx_rates` table, which v2 called
  "Variant T" and which was the takeover audit's default. The other was configuration, which v2
  called "Variant C". The owner chose configuration. v2.1 removed every provision that existed only
  for the table, and this plan now describes one path.

### SD-3 — The meaning of "risk-adjusted pipeline"

- **Decision (2026-10-01).** Approved. "Risk-adjusted" means a cross-tabulation of pipeline
  exposure by the persisted VS-01 risk band. It does not mean a new risk score, a blended
  risk-adjusted monetary value, a recalculation of VS-01 risk, or an import of VS-01's signal engine.
  VS-01 stays frozen.
- **Audit default.** A cross-tabulation of open exposure by VS-01 risk band. Never a blended number.
- **If approved.** §A12 as written. VS-01's ranking, bands and payload hashes are untouched.
- **If rejected.** Any numeric adjustment of an amount by a band contradicts strategy §4.3 and the
  frozen plan §A25 test 5. It would reopen VS-01 and needs its own specification first. This
  document cannot be amended to do it.

### SD-4 — The decision layer

- **Decision (2026-10-01).** Approved. VS-02 creates no CEO brief, no analyst decision, no action,
  no approval and no executor behaviour.
- **Audit default.** No brief and no approval in VS-02.
- **If approved.** No analyst, position, conflict, action, brief or decision is built. No executor
  exists.
- **If rejected.** VS-02 needs an action catalogue entry, an analyst contract, a brief template and
  a decision path, each of which plan §A30 assigns to VS-03 or VS-04. That is a different slice and
  needs a new specification.

### SD-5 — Computed on read

- **Decision (2026-10-01).** Approved. One GET route, recomputed per request; no persisted view, no
  result table, no idempotency key, no POST route and no execution or history mechanism.
- **Audit default.** Computed on read, GET-only routes, no result persistence.
- **If approved.**
  - One GET route. Every request recomputes the view inside one read-only snapshot.
  - No result table, no idempotency key, no history.
  - VS-02 writes nothing, inside the API or outside it.
- **If rejected.** Results need a table, an identity, a POST route and a migration. Three frozen
  pins then need evolution as well: the write-operation list in
  `tests/integration/test_h4_api_contract.py`, the `WRITES` set in `scripts/vs01_acceptance.py:184`,
  and the migration pins of X1.

### SD-6 — Frontend

- **Decision (2026-10-01).** Approved. `frontend/**` stays frozen for VS-02, and the Pipeline Room
  stays locked until its separate later phase.
- **Audit default.** A separate later phase, not part of this slice.
- **If approved.** `frontend/**` is frozen for all of VS-02. The Pipeline Room stays locked and
  still reads "Opens with VS-02" after the backend ships. The frontend's recorded OpenAPI fixture is
  not regenerated, so its tests are unaffected. OBSERVED:
  `frontend/tests/contract/fixtures.test.ts` generates types from the recorded `openapi.json`, not
  from the live API.
- **If rejected.** A frontend phase joins this plan and needs its own specification section: the
  agent, the panel, the NEW HIRE ceremony (not built today), four pinned tests to evolve, new
  recorded fixtures, and a decision on whether it waits for F7.

---

## 0.7 Methodology decisions

Each was put to the owner as a proposed decision. The owner approved all twenty-two as a block on
2026-10-01, exactly as specified (§0.10), which approves the sections named. §0.8 says what striking
one would reopen.

| ID | Decision proposed | Specified in |
|---|---|---|
| MD-1 | An **open** deal is one whose `is_active` is true, VS-01's own definition of an active deal | §A8.2 |
| MD-2 | A **valued** deal has a non-null stage, amount, currency and probability and a non-negative amount. An open deal that is not valued is counted, excluded from every monetary figure, and reported | §A8.3 |
| MD-3 | Unweighted and probability-weighted exposure are both reported. Weighted is rounded per deal to 0.01, half-even | §A9.2 |
| MD-4 | The arithmetic context, and conversion per deal rounded to 0.01 of the base currency, half-even. Every aggregate is a sum of per-deal values | §A9.1, §A9.3 |
| MD-5 | Closed deals are counted by stage and carry no amount | §A8.4, §A14.8 |
| MD-6 | A period is a calendar month, over a fixed twelve-month horizon from `as_of`'s month, with `OVERDUE`, `LATER` and `UNDATED` | §A10.4 |
| MD-7 | Owner buckets: a resolved employee, `UNASSIGNED` or `UNRESOLVED`; the last two never collapse | §A10.3 |
| MD-8 | Concentration in the base currency, by customer and by owner: top-5 shares, cumulative top-1/3/5 share and HHI, at four decimal places | §A11 |
| MD-9 | Bands are read from persisted assessments at the exact scope identity and current rule versions. Missing coverage is a bucket, not an error | §A12.2, §A16.2 |
| MD-10 | `as_of` is a required parameter with no fallback, and the route's scope is unpinned | §A6 |
| MD-11 | The rate set: one snapshot, its fields, one identity rule and digest, one authored file, lazy loading | §A7.2–§A7.4 |
| MD-12 | One route, `GET /api/v1/pipeline/view`; the typed view contract; unknown query parameters ignored | §A14, §A15 |
| MD-13 | Packages `app/fx/` and `app/pipeline/`, their modules, import allow-lists, session-holding modules, `DealFact`, and `pipeline_rules.yaml` | §A8.1, §A19, §A22 |
| MD-14 | Error semantics: one new code, `FX_RATE_MISSING`, its status and details, and the evaluation order | §A7.5, §A17 |
| MD-15 | `view_hash`, the hash chain to the served value, and limitation text kept outside the hash | §A14.10 |
| MD-16 | Milestones, the gate rule, the M0 procedure, the acceptance command and the commits | §A27, §B5–§B7 |
| MD-17 | DOC-004 is compared in tests and the acceptance command only. Production code never reads its text | §A18.4 |
| MD-18 | The limitation codes, their order and their exact texts | §A13.1 |
| MD-19 | The data-quality note codes, their triggers and their shape | §A13.2 |
| MD-20 | The one log event and its fields | §A20 |
| MD-21 | The allowed and frozen path table, including every additive edit to a frozen file | §B1 |
| MD-22 | The fixture package, the named tests labelled MD-22, and the mutation targets | §A24, §A25, §A28 |

## 0.8 Decision dependencies

Striking or changing a decision reopens every section, test and criterion in its row. A row's
dependants are not approved until the decision is.

| Decision | Depends on it |
|---|---|
| SD-1 | §A7.2 base currency; Appendix 2; the base figures M0 pins into §A26 |
| SD-2 | §A7.3 as the only source of the rate set; §A7.6; §A16.3; §A17.1 step 4; the absence of any table, migration or registration path from §B1 and §B2; §B4; `V2.1c` |
| SD-3 | §A12; `by_risk_band`, `by_customer[].band`, `risk_coincidence` in §A14; tests 10–12 and 27; criterion 8; MD-9 |
| SD-4 | §A30; nothing is built for it |
| SD-5 | §A15; §A16.1; §A19 item 6; MD-12; tests 20 and 24 |
| SD-6 | §A23; the frontend rows of §B1 |
| MD-1 | §A8.2; MD-2; `deal_counts`; `closed_deals`; test 17 |
| MD-2 | §A8.3; `open_unvalued`; the two notes; tests 15 and 17 |
| MD-3 | §A9.2; the `weighted` member of every amount; weighted concentration; Appendix 1 |
| MD-4 | §A9.1, §A9.3, §A9.4; tests 4 and 22; criterion 6 |
| MD-5 | §A8.4; `closed_deals`; `deal_counts.by_stage` |
| MD-6 | §A10.4; `PERIOD_HORIZON`; test 13; Appendix 1 |
| MD-7 | §A10.3; concentration by owner; test 14 |
| MD-8 | §A11; §A12.6 and `by_customer`; §A14.7; `SHARES_FOLLOW_RATES`; tests 18 and 19 |
| MD-9 | §A12.2; `band_rows`; tests 11 and 12; `V2.2` |
| MD-10 | §A6; the `as_of` parameter; X5; test 24 |
| MD-11 | §A7.2–§A7.4; the `fx` object; test 8; the digest pin |
| MD-12 | §A14; §A15; tests 24 and 25; T-VS02-2 |
| MD-13 | §A8.1; §A19 item 5; §A22; §B1; T-VS02-1 |
| MD-14 | §A7.5; §A15's status table; §A17; tests 9 and 24; T-VS02-10 |
| MD-15 | §A14.10; `view_hash` in §A15 and §A20; tests 3, 8, 20 and 25; criteria 4, 11 and 12 |
| MD-16 | §A27; §B5–§B7 |
| MD-17 | §A18.4; the no-document rows of §A21; tests 2 and 3; criterion 4 |
| MD-18 | §A13.1; `limitations`; `limitation_texts`; test 6 |
| MD-19 | §A13.2; `data_quality`; test 15 |
| MD-20 | §A20 |
| MD-21 | §B1 |
| MD-22 | §A24; the MD-22 rows of §A25; §A28 |

## 0.9 Unknown and open

| ID | What is unknown | What closes it | Standing on 2026-10-01 | Blocks |
|---|---|---|---|---|
| **U-1** | The rate set's authored content: the USD and EUR rates against the base, the date they are stated for, and the source note. No rate exists in code, configuration or data | The owner supplies all of it | **Rates closed:** USD `85` and EUR `100`, in INR per unit. They are illustrative, authored rates and come from no market source. **Date and source note closed at VS02-M0:** the owner supplied both, and they are recorded verbatim in §A7.3 (§0.11). Neither was invented or defaulted | nothing |
| **U-2** | The project proposal PDF could not be read (no PDF tooling). Any commitment it makes about revenue or pipeline beyond what the strategy quotes is unknown | The owner's direction | **Closed.** The owner directs that the PDF be treated as making no revenue or pipeline commitment beyond this specification. No requirement is taken from it | nothing |
| **U-3** | Whether VS-01 is "accepted" in strategy §10's sense. The only record was M9's closure and the push of `523210a` | The owner's statement | **Closed.** VS-01 is accepted as the predecessor baseline for VS-02 | nothing |
| **U-4** | The organization's fiscal calendar. None is defined in data or documents | Not needed while MD-6 stands | **Closed.** No fiscal-calendar requirement; MD-6's calendar months stand | nothing |
| **U-5** | The frontend phase: its agent, its panel, and whether it waits for F7 | A later frontend specification (SD-6) | No action now | nothing in this plan |
| **U-6** | When, and whether, the hosted site receives VS-02 | The owner's separate approval per outward action (§B4) | No hosted action is part of this specification | nothing in this plan |
| **U-7** | Whether any frozen test beyond §B2's list is tripped by a new package, route or error code | VS02-M0's pin census (§B6). An unlisted failure stops the milestone and is put to the owner before anything is changed | **Closed by VS02-M0.** The census, by reading and by a scratch run, found no frozen test tripped outside the ten authorised rows of §B2.1 (§0.11) | nothing |

## 0.10 The owner's decisions of 2026-10-01, and what v2.1 changed

**Decisions.**

| Item | Decision |
|---|---|
| SD-1 | Approved: the base currency is INR |
| U-1 | Rates supplied: USD `85` and EUR `100`, in INR per unit, as illustrative authored rates for this rate set. The date and the source note are not yet supplied and remain an owner input at VS02-M0 |
| SD-2 | Configuration: the rate set lives in `config/intelligence/fx_rates.yaml` (v2's "Variant C"). No table and no migration |
| SD-3 | Approved: a cross-tabulation by persisted VS-01 band. No new score, no blended amount, no recalculated risk, no import of VS-01's signal engine |
| SD-4 | Approved: no brief, analyst decision, action, approval or executor |
| SD-5 | Approved: one GET route, recomputed per request, nothing persisted, no POST route |
| SD-6 | Approved: `frontend/**` frozen; the Pipeline Room stays locked |
| MD-1…MD-22 | Approved as a block, exactly as specified |
| U-2 | The proposal PDF is treated as adding no commitment |
| U-3 | VS-01 is accepted as the predecessor baseline |
| U-4 | No fiscal-calendar requirement |
| U-5, U-6 | No action in this plan |
| U-7 | VS02-M0 keeps the authoritative pin census; a new contradiction stops the milestone |
| T-VS02-1a, 1b, 1c, 2, 3a, 3b, 3c, 4, 5 and 10 | Authorised, and only these ten. Not authorised: the withdrawn T-VS02-6, the removed T-VS02-7…9, and any row VS02-M0 may propose |
| The three clarifications of v2.1 | Approved: one `fx.rate_set_version` for the view and test 5's wording; the three test seams of §A22.5 and nothing more; the REQUIRED-versus-decision wording |
| This revision | Approved for commit, alone, as `VS-02: finalize specification` |

Not supplied here: the rate set's date and source note (U-1). They are an owner input during VS02-M0
(§B6).

**Changes.** v2.1 is a documentation revision. It changes no architecture, scope, behaviour,
acceptance criterion or security control except as these items state.

1. **One path for the rate set.** Every provision that existed only for the table alternative (v2's
   "Variant T") was removed: the table, its model, its write repository, the migration, the
   registration functions and command, the Make target, the `demo-reset` line, three error classes,
   the `RATE_SET_NOT_REGISTERED` code, v2's test 23, T-VS02-7, T-VS02-8 and T-VS02-9, the edits to
   `models/__init__.py` and to VS-01's acceptance command, and the hosted migrate-and-register step.
   No variant marker remains.
2. **Numbering kept.** Test 23 is marked withdrawn and its number is not reused. T-VS02-7…9 are not
   reused. §A7.6 and §A16.3 keep their numbers.
3. **Rate-set version (clarification 1).** §A7.1 item 2 states that one `fx.rate_set_version`
   governs every base aggregate of the view, and test 5 is reworded to match. The view contract of
   §A14 is unchanged.
4. **Test seams (clarification 2).** §A22.5 documents the three seams the named tests need, and
   states that every other internal signature is implementation-private.
5. **Labels (clarification 3).** §A7.1, §A9.4, §A12.4, §A18.3, §A21, §A29 and §B3 now say which part
   is REQUIRED and which is governed by a decision.
6. **U-1.** The approved rates are written into §A7.2, §A7.3 and Appendix 2. VS02-M0 gains the step
   that records the date and the source note (§B6).
7. **Consequential wording.** MD-14 and the M4 rows speak of one new error code, not two. With no
   table, an empty source system always answers `200` (§A17.1);
   `scripts/vs01_acceptance.py` and `migrations/` are stated as frozen (§B1); §B2.3 lists the
   migration and head pins among those expected to pass unchanged.

## 0.11 The VS02-M0 record (2026-10-01)

VS02-M0 (§B6) ran on 2026-10-01 at `b0fcaa2`, one commit ahead of `origin/main` (`523210a`). It
changed no production code, test, configuration, migration, data, frontend or README file, and it
started nothing of VS02-M1. This amendment is its only output (§B6 step 7). §0.10 stays as the
record of v2.1; where it says U-1's date and source note are not yet supplied, this record is the
later one.

**Owner input (U-1).** The owner supplied both open fields, and §A7.3 records them verbatim:
`as_of_date` is `2026-10-01`, and `source_note` is the owner's sentence as written there. Neither
was invented, defaulted or reworded. The rates are unchanged: base INR, USD `85`, EUR `100`,
illustrative and owner-authored. The rate set is fully pinned, and it lives in configuration only
(SD-2, v2's "Variant C"): no table, migration or registration path exists.

| Check | Result (OBSERVED 2026-10-01) |
|---|---|
| Baseline suite (§B5) | 6771 passed (unit 5287, contract 185, integration 1214, e2e 85), 0 failed, 0 skipped, 2 warnings, both the known ones; `app/` coverage 100% over 7456 statements |
| Lint, types, secrets, head | ruff 69; mypy 9; secret scan 0; one head, `070e4968a497`. All equal to the baseline of §0.1 |
| VS-01 | `make verify-vs01` exits 0; the golden file's hash and the three payload hashes are unchanged; the pinned fingerprint is matched |
| Pin census, by reading | all ten authorised rows of §B2.1 match the repository at the lines cited |
| Pin census, by scratch run | nine frozen tests fail over the stubbed copy, each under a row of §B2.1: T-VS02-1a to 1c one test, T-VS02-2 two, T-VS02-3a one, T-VS02-3b two, T-VS02-5 two, T-VS02-10 one. T-VS02-3c and T-VS02-4 add content and have no failing test behind them. **No other frozen test failed: no further row is proposed, and no new authorisation is needed (U-7).** The copy is deleted |
| Dataset | `data/demo/` reconciles with Part A and Appendix 1: 233 rows over 7 entity types; 44 deals, 30 open and all valued, 14 closed |
| Arithmetic | Appendix 1 and Appendix 2 are reproduced in full by a calculation independent of any VS-02 code; the base-currency figures are pinned (§A26, Appendix 2) |
| Substrate (§0.2 items 4 to 7) | present as assumed |
| Security and boundaries (§A21) | every control is satisfiable against the frozen substrate; no violation |
| Allowed and frozen paths (§B1) | every frozen path is byte-identical to `523210a`; none of the new paths exists |

**Gate.** VS02-M0 is closed. VS02-M1 is authorised by the gate and has not started; it begins only
on the owner's instruction.

---

# Part A — Specification

### A1. Objective [R]

Source: the brief, strategy §10.2. State the shape and concentration of open pipeline, and where
commercial exposure coincides with relationship risk.

### A2. Executive question [R]

Source: the brief, strategy §10.2. "What revenue exposure requires attention?"

### A3. In scope [R]

Source: the brief, strategy §10.2 and §6.3.

1. FX normalization: a rate set with a declared base currency, and a conversion service.
2. Open-pipeline aggregation per currency, per stage, per owner and per expected-close period.
3. Concentration measures.
4. Exposure cross-tabulated by VS-01 risk band.
5. An output that names its base currency on every base aggregate and its rate-set version, and
   states the absent `lost` stage as a limitation.

What is out of scope is listed once, in §A30.

### A4. Definitions

| Term | Definition | Label |
|---|---|---|
| **Scope** | VS-01's `Scope`: one `source_system`, one `as_of`, one `layer1_fingerprint` | [R] plan §A30 |
| **Base currency** | The single currency every cross-currency figure is expressed in, declared by the rate set | [R] brief §6.3 |
| **Rate set** | A versioned, immutable set of rates to the base currency with one stated date. A stated assumption, never a fact | [R] brief §6.3 |
| **Native amount** | A deal's `amount` in its own `currency` | [R] plan §A12 |
| **Base amount** | A native amount converted through the rate set | [R] brief §6.3 |
| **Open deal** | A deal with `is_active` true | [MD-1] |
| **Valued deal** | An open deal that can be given an amount (§A8.3) | [MD-2] |
| **Unweighted exposure** | The sum of amounts | [MD-3] |
| **Weighted exposure** | The sum of per-deal `amount × probability / 100`, each rounded | [MD-3] |
| **Partition** | A division of the open valued deals into buckets, each deal in exactly one | [R] brief §10.2: "totals reconcile" |
| **View** | The canonical object of §A14, computed for one scope | [MD-12] |

### A5. Inputs

| Input | Read through | Label |
|---|---|---|
| `deals` attributes | a new persistence-only read (§A16.2) | [MD-13] |
| deal → owner | `app.relationships.edges_of_type(EdgeType.DEAL_OWNED_BY, …)` | [R] strategy §11: every slice reads relationships only through the model; X10 |
| deal → customer | `app.relationships.edges_of_type(EdgeType.CUSTOMER_HAS_DEAL, …)` | [R] same |
| VS-01 bands | persisted `risk_assessments`, a new persistence-only read | [MD-9] |
| the rate set | §A7.6 | [SD-2] |
| `config/intelligence/pipeline_rules.yaml` | a new loader (§A22.3) | [MD-13] |
| `rules_version`, `linker_version` | VS-01's `default_risk_rules()`, read and never written | [R] frozen |
| the D1 stage vocabulary and currency codes | `app.normalization.config.default_config()` | [R] frozen |

**Never an input to any figure [R]** (strategy §7.5, §2.4, §2.7): the text of any document; any
ticket attribute; any clock; any environment variable; any other source system's rows.

**The one thing VS-02 reads from every entity [R]** (frozen `resolve_scope`): the scope's
`layer1_fingerprint` and `entity_counts` are computed over all seven entity types, from `source_id`
and `record_hash` only. They identify the snapshot. They feed no figure, and they are why the scope,
and therefore `view_hash`, moves when any Layer 1 row changes (§A29).

### A6. Scope and `as_of`

1. [R] (strategy §2.7, context §17.3) No module of VS-02 reads a clock. Every computation takes an
   explicit `as_of`.
2. [MD-10] `as_of` is a **required** request parameter. VS-02 calls the frozen
   `resolve_scope(session, source_system=…, as_of=…)` with a date, so the scope's `as_of_source` is
   always `EXPLICIT` and the ticket-derived fallback is never taken.
   - *If approved:* the pipeline's date never depends on support tickets, and
     `ScopeResolutionError` cannot occur on this route.
   - *If rejected:* a null `as_of` resolves to `max(support_tickets.created_at)`, a
     `422 SCOPE_UNRESOLVED` path is added, and the view's date is coupled to another entity.
3. [MD-10] The route's scope is **unpinned**, as VS-01's assessment route is: it computes over
   whatever snapshot the database holds and reports that snapshot's fingerprint. The acceptance
   command compares the reported fingerprint with VS-01's pinned value and fails on a mismatch.
4. [R] (OBSERVED: `deals` has no creation or stage-change date) `as_of` does three things and only
   three: it is part of the scope the view reports; it places deals in the period partition
   (§A10.4); it selects which assessments are joined (§A12.2). It does **not** select deals. The
   view states this as limitation `NO_DEAL_HISTORY`.
5. [R] (plan §A23 precedent) Any calendar date is accepted. A date before all data or in the future
   is not an error.
6. [MD-6] The size of the response does not depend on `as_of` (§A10.4).

### A7. The FX model

#### A7.1 Principles [R]

Sources: the brief, strategy §6.3; strategy §14 item 4; plan §A12.

1. No figure spanning two currencies is produced except through the rate set.
2. Every base-currency aggregate is reported with its base currency and its rate-set version.
   - [MD-12] *How.* One view uses exactly one rate set. A single `fx.rate_set_version` identifies the
     rate set used by the entire view and therefore governs every base-currency aggregate in it.
     `rate_set_version` is not repeated on any Bucket or Amount object; it appears only where §A14
     puts it, in `fx` and in each Concentration block. The base currency is named the same way:
     `fx.base_currency` governs the view, and the per-deal base values of an `OpenDeal` carry no
     currency field of their own. The reporting requirement is the brief's; this way of meeting it
     is MD-12's.
3. The rate set is labelled a stated assumption in the view.
4. `MoneyValue` is not modified. Adding two currencies still raises `CurrencyMismatchError` (X9).

#### A7.2 The rate set [MD-11]

A rate set is an immutable value with exactly these authored fields, and one derived:

| Field | Type | Rule |
|---|---|---|
| `rate_set_version` | string, 1–50 characters | Identifies the set. The first is `"1"` |
| `base_currency` | ISO 4217 code in the frozen D1 vocabulary | `INR` ([SD-1]) |
| `as_of_date` | calendar date | The date the assumption is stated for. One date for the whole set. [U-1]: `2026-10-01`, supplied by the owner at VS02-M0 |
| `source_note` | string, 1–500 characters, no line break | Where the assumption comes from, in the owner's words. [U-1]: supplied by the owner at VS02-M0, verbatim in §A7.3 |
| `rates` | mapping currency → positive `Decimal` | `rate_to_base`: units of base currency per **one** unit of the currency. At most 8 decimal places and at most 10 integer digits. Values ([U-1], approved): USD `85`, EUR `100`, INR `1` |
| `digest` | 64 lowercase hex characters | Derived (§A7.4) |

Rules:

1. The base currency is in `rates` with the rate exactly `1`.
2. Every currency code is in the frozen D1 vocabulary, the rule `MoneyValue` already applies.
3. One rate per currency. A rate set is a single snapshot, not a time series. A time series is a
   later slice's need and is not anticipated here (strategy §11: promote on second use).
4. `as_of_date` is **reported**, never matched against the scope's `as_of`. No interpolation, no
   nearest-date lookup, no staleness rule.
5. **Immutability.** A version's authored content never changes. Any change to any authored field
   requires a new `rate_set_version`.

#### A7.3 The authored file and its loading [MD-11]

`config/intelligence/fx_rates.yaml` is the one place a human authors a rate set, and the one place
the rate set lives (SD-2). It holds exactly one rate set: the current one. It is the only place a
rate-set version is named.

```yaml
version: 1                      # file format
rate_set_version: "1"
base_currency: INR              # SD-1
as_of_date: 2026-10-01          # U-1: the owner's, recorded at VS02-M0
# U-1: the owner's words, recorded at VS02-M0
source_note: "Owner-authored illustrative rates for VS-02 deterministic demo calculations and acceptance testing; not sourced from a live market feed."
rates:
  INR: "1"
  USD: "85"                     # U-1
  EUR: "100"                    # U-1
```

1. The loader follows `app/intelligence/config.py`'s discipline: `yaml.safe_load` only; unknown or
   missing keys are refused; a broken file is refused with the broken key named (plan §A23).
2. A rate must be a YAML **string** or integer. A YAML float is refused, because a binary float is
   not the number the author wrote.
3. **Loading is lazy.** The file is read on first use by a VS-02 code path and cached for the
   process, as `default_risk_rules()` is. It is never read at import time or at application startup.
   `app/main.py` is not edited. A refused file therefore fails the pipeline route alone
   (`500`, §A17) and leaves every Layer 1 and VS-01 route working. A failed load is not cached.

#### A7.4 Identity and digest [MD-11]

One rule: **the digest covers every authored field.**

`digest = sha256(canonical_json({"as_of_date": iso, "base_currency": code, "rate_set_version": v,
"rates": [[currency, decimal_text(rate)], …], "source_note": note}).encode("utf-8")).hexdigest()`,
with `rates` ascending by currency code. `canonical_json` and `decimal_text` are VS-01's, imported,
not copied.

**The pin.** `tests/unit/test_vs02_fx.py` holds a literal map `PINNED_RATE_SETS` from
`rate_set_version` to digest. The committed file's version must be a key, and its digest must equal
the pinned value. An entry is never edited or removed; a new version adds an entry. An edit without
a version bump therefore fails the build.

#### A7.5 Conversion

1. [R] (X9) `convert(value: MoneyValue, rate_set) -> MoneyValue` returns a **new** `MoneyValue` in
   the base currency. `MoneyValue` and its operators are untouched.
2. [MD-4] `amount_base = quantize(value.amount × rate, BASE_QUANTUM, ROUND_HALF_EVEN)` in the
   arithmetic context of §A9.1, with `BASE_QUANTUM = Decimal("0.01")`. A value already in the base
   currency is multiplied by `1` and quantized the same way.
3. [MD-14] `FxRateMissingError` carries `currencies`, a tuple of codes in ascending order.
   `convert` raises it with the one currency it was asked to convert and has no rate for. There is no
   default rate and no skipped deal.
4. [MD-14] A rate is required only for the currency of an open, valued deal. Before any figure is
   computed, the service checks every such currency and raises the same error once, carrying **all**
   missing currencies. The whole view then fails (§A17). No partial base figure is produced.
5. [R] (strategy §14 item 4) Base amounts are summed with `MoneyValue.total(base_currency, …)` and
   native amounts with `MoneyValue.total(currency, …)`. No VS-02 code adds two `MoneyValue` objects
   of different currencies, and no VS-02 module catches `CurrencyMismatchError`.

#### A7.6 Storage [SD-2]

The rate set is the loaded, validated content of the authored file (§A7.3), and nothing else. There
is no table, model, repository, migration or registration command, and no stored copy of the rates.
VS-02 reads the rate set from configuration and writes it nowhere.

### A8. Deal facts

#### A8.1 `DealFact` [MD-13]

VS-02 reads each deal in scope into its own frozen value type. It does not reuse `DealSignal`, which
cannot represent an incomplete deal (D-4).

Fields: `source_id`, `stage`, `is_active`, `amount`, `currency`, `probability`,
`expected_close_date`, `owner_source_id`, `customer_source_id`, and the two resolved references
`owner` and `customer`, each a source id or null, filled from the relationship edges of §A5.

#### A8.2 Open [MD-1]

A deal is **open** when `is_active` is true, and **closed** otherwise.

- *Derivation.* VS-01's `signals._active_deals` selects `Deal.is_active.is_(True)`.
- *OBSERVED.* On the committed dataset `is_active` and `stage != 'won'` select the same 30 deals.
- *Where they disagree.* The deal is classified by `is_active`, never reclassified, and a
  `STAGE_ACTIVITY_MISMATCH` note is emitted (§A13.2). The closed stages are named in configuration:
  `closed_stages: [won]`.
- *If rejected.* Open becomes `stage not in closed_stages`. Test 17 is dropped, and VS-02 and VS-01
  can then disagree about one customer's exposure.

#### A8.3 Valued [MD-2]

An open deal is **valued** when its stage, amount, currency and probability are all non-null and its
amount is not negative. Otherwise it is **unvalued**.

1. An unvalued deal contributes to no monetary figure and sits in no partition.
2. It is never dropped: it is counted in `deal_counts.open_unvalued`, listed in
   `unvalued_deal_ids` and in `open_deals`, and reported by an `INCOMPLETE_DEAL` or
   `NEGATIVE_AMOUNT` note.
3. *Relation to VS-01.* M1's frozen `DealSignal` requires the same four fields but accepts a
   negative amount. So every valued deal is one VS-01 describes, and the two sets differ exactly by
   the open deals with a negative amount.
4. OBSERVED: the committed dataset has no unvalued deal. Fixtures exercise the rule.

#### A8.4 Closed deals [MD-5]

Closed deals are counted per stage and listed in `closed_deals` with their stage and activity only.
They carry no amount in the view.

- *Why.* The objective is open pipeline. A won total beside an open total invites the win rate and
  stage conversion the brief puts out of scope, and `won` deals carry only an expected close date.
- *If rejected.* A closed-deal measure per currency is added to `deal_counts`, with a limitation
  that it is not revenue.

### A9. Measures and arithmetic

#### A9.1 The arithmetic context

1. [R] (plan §A24) All arithmetic is `Decimal`. No float appears in any VS-02 module; a boundary
   test refuses `float(` and float literals in `app/fx/` and `app/pipeline/`.
2. [MD-4] Every multiplication and division runs in an explicit local context:
   `ARITHMETIC_PRECISION = 50`, rounding `ROUND_HALF_EVEN`. The process default context is never
   relied on (D-3).
3. [R] (plan §A24) Rounding to a quantum is always an explicit `quantize`.

#### A9.2 Per-deal native values [MD-3]

For each valued deal:

| Value | Definition |
|---|---|
| `native_unweighted` | `amount`, as stored |
| `native_weighted` | `quantize(amount × probability / 100, WEIGHT_QUANTUM, ROUND_HALF_EVEN)`, with `WEIGHT_QUANTUM = Decimal("0.01")` |

Both are reported everywhere, each under its own name. They are never added to each other.

- *Why both.* DOC-004's figure is unweighted. Strategy §4.3 reasons in weighted exposure.
- *Standing of the weight.* `probability` is the source system's stated value. Weighted exposure is
  arithmetic over stated values, not a forecast.
- *If rejected.* Name the one measure to keep. The other is removed from every amount object.

#### A9.3 Per-deal base values [MD-4]

| Value | Definition |
|---|---|
| `base_unweighted` | `convert(native_unweighted)` |
| `base_weighted` | `convert(native_weighted)`, that is, of the already-rounded weighted amount |

#### A9.4 Aggregates and reconciliation

1. [R] (the brief: "totals reconcile to the per-currency breakdown") For every partition of §A10 and
   §A12, the buckets sum **exactly** to the open pipeline's total: the deal count, each native
   figure per currency, and each base figure, weighted and unweighted alike. There is no tolerance.
2. [R] (the brief) The base total equals the sum of the per-currency base figures, exactly.
3. [MD-4] Every aggregate is the sum of the per-deal values of §A9.2 and §A9.3 over the bucket's
   deals, and is computed no other way. This is what makes items 1 and 2 hold by construction.
4. [MD-4] One base figure per bucket. The view never also reports `native total × rate` (D-18).
5. [MD-4] **The hand check.** A reviewer multiplying a currency's native total by its rate obtains
   that currency's base figure within `0.005 × (the bucket's valued deals in that currency)` units
   of the base currency. The README states the bound, and the acceptance command reports the
   observed difference.

- *Standing of items 1 and 2.* The reconciliation requirement is the brief's. That it holds
  **exactly**, with no tolerance, depends on MD-4: it follows from items 3 and 4 and from per-deal
  conversion (§A9.3). MD-4 is approved, so the requirement is exact.
- *If MD-4 is rejected* in favour of converting bucket totals: items 1 and 2 hold only within a
  stated tolerance.

### A10. Partitions

Each subsection defines a partition of the open valued deals. Every bucket has the shape of §A14.4.
Which buckets are always present is stated per partition; a present bucket with no deal states
zeros.

#### A10.1 By currency

1. [R] (the brief; strategy §3) Exposure is reported per currency.
2. [MD-12] One bucket per currency held by an open valued deal, ascending by code. No bucket for a
   currency no deal holds. Each carries the rate applied.

#### A10.2 By stage

1. [R] (the brief) Per-stage aggregation.
2. [MD-12] One bucket per value of the D1 stage vocabulary, **always present**, ascending by code
   point. OBSERVED: the vocabulary is an unordered set, `{negotiation, qualification, won}`.
3. [MD-1] An open deal in a closed stage is counted under that stage and carries the mismatch note.

#### A10.3 By owner

1. [R] (the brief; plan §A9.1) Per-owner aggregation over the `deal_owned_by` edge, a
   `SOURCE_KEY_JOIN` over `deals.owner_source_id` within the scope's source system.
2. [MD-7] The buckets:

   | `kind` | Key | When |
   |---|---|---|
   | `EMPLOYEE` | the employee's `source_id` | the edge exists |
   | `UNASSIGNED` | `UNASSIGNED` | `owner_source_id` is null |
   | `UNRESOLVED` | `UNRESOLVED` | `owner_source_id` is not null and names no employee in the scope |

   Order: `EMPLOYEE` buckets ascending by key, then `UNASSIGNED`, then `UNRESOLVED`. The last two
   are always present.
3. [R] (plan §A23) `UNASSIGNED` and `UNRESOLVED` never collapse. A key naming an employee of another
   source system is `UNRESOLVED`.
4. [R] (plan §A9.2) Ownership is not composed. VS-02 groups deals by their owner. It derives no
   customer–employee association from deal ownership and does not walk to an owner's manager.

#### A10.4 By expected-close period

1. [R] (the brief) Expected-close exposure by period.
2. [MD-6] The buckets, always exactly fifteen, in this order:

   | `kind` | Key | Holds the deals whose `expected_close_date`… |
   |---|---|---|
   | `OVERDUE` | `OVERDUE` | is strictly before `as_of` |
   | `MONTH` | `YYYY-MM`, twelve of them | is on or after `as_of` and falls in that calendar month. The twelve months are `as_of`'s month and the eleven that follow: `PERIOD_HORIZON = 12` |
   | `LATER` | `LATER` | falls after the twelfth month |
   | `UNDATED` | `UNDATED` | is null |

3. [MD-6] A deal expected on `as_of` itself is in its month. A deal earlier in `as_of`'s own month
   is `OVERDUE`. Month keys are computed arithmetically on (year, month) and never by constructing a
   date, so an `as_of` late in year 9999 yields keys in year 10000, written with five digits; nothing
   fails.
4. [MD-6] No quarter, half or fiscal-year roll-up is produced. No fiscal calendar is defined
   anywhere ([U-4]); a consumer can sum months.

- *Why a fixed horizon.* It bounds the response for any `as_of` and any data: an `as_of` of 1900
  returns the same fifteen buckets.
- *If MD-6 is rejected.* Name the period, the calendar and the horizon. Nothing else in Part A
  changes.

### A11. Concentration

1. [R] (the brief: "concentration measures") The view measures how concentrated open exposure is.
2. [MD-8] **Where.** The base currency only. Each block names its base currency and rate-set
   version.
3. [MD-8] **Over what.** Two partitions, by customer (§A12.6) and by owner (§A10.3), each for
   unweighted and for weighted exposure: four blocks.
4. [MD-8] **Holders.** A holder is a bucket of the partition whose base amount, in the measure
   concerned, is greater than zero. The pseudo-buckets `UNLINKED`, `UNASSIGNED` and `UNRESOLVED` are
   holders when their amount is greater than zero, flagged `pseudo: true`, so shares describe the
   whole total.
5. [MD-8] **Measures**, for a total `T` and holder amounts `a_i`, with
   `SHARE_QUANTUM = Decimal("0.0001")`:

   | Measure | Definition |
   |---|---|
   | `share` | `quantize(a_i / T, SHARE_QUANTUM, ROUND_HALF_EVEN)`, a fraction from 0 to 1 |
   | `top` | the `CONCENTRATION_TOP_N = 5` largest holders, or all of them when there are fewer, ordered by amount descending, then key ascending |
   | `cumulative` | for each `n` in `CUMULATIVE_POINTS = (1, 3, 5)`: the summed amounts of the largest `min(n, holder count)` holders, divided by `T`, then quantized. It is not a sum of rounded shares |
   | `hhi` | `quantize(Σ (a_i / T)², SHARE_QUANTUM, ROUND_HALF_EVEN)` |

6. [MD-8] When `T` is zero there is no holder: `top` and `cumulative` are empty lists, `hhi` is
   `null`, and `reason` is `NO_OPEN_EXPOSURE` (D-10).
7. [MD-8] Rounded shares need not sum to 1. The README says so.
8. [R] (strategy §4.2, §4.3) A share is a ratio of stated amounts. It is not a probability and not a
   score, and it is never combined with a band.

- *If MD-8 is rejected.* Strike HHI, or name the measure. The brief says "measures" and names none.

### A12. Exposure by risk band

#### A12.1 The customer of a deal [R]

Source: strategy §11. The customer of a deal is the source of its `customer_has_deal` edge, a
`CANONICAL_FK`. A deal with no such edge has no customer.

#### A12.2 Which bands are joined [MD-9]

The band of a customer is the `band` of the persisted `risk_assessments` row whose identity is
exactly:

`(customer, as_of = scope.as_of, source_system = scope.source_system, layer1_fingerprint =
scope.layer1_fingerprint, rules_version, linker_version)`

with `rules_version` and `linker_version` read from VS-01's current configuration. VS-01's unique
constraint guarantees at most one such row per customer.

1. VS-02 reads. It never runs an assessment, never computes a band, and never writes a risk table.
2. An assessment of another date, snapshot or rule version is not joined.
3. The view states the two versions it joined under, in `versions`.

- *If rejected in favour of recomputing bands in process.* VS-02 would import M3's signal engine and
  band table, the cross-tabulation could disagree with the assessments a human approved, and §A22.4
  changes.

#### A12.3 The partition [SD-3]

Six buckets, always present, in this order: the four bands by descending rank, then the two
coverage buckets.

| Key | Holds the open valued deals whose customer… |
|---|---|
| `CRITICAL`, `ELEVATED`, `WATCH`, `NONE` | has an assessment in that band |
| `UNASSESSED` | exists and has no assessment at the identity of §A12.2 |
| `UNLINKED` | does not exist: the deal has no customer (§A12.1) |

1. The band vocabulary and its rank are the frozen `RiskBand` enum's (`app.intelligence`), not a
   list VS-02 declares.
2. A stored band that is not a `RiskBand` value raises `PipelineDataError` and fails the request
   (`500`). It cannot occur while VS-01's writer is frozen, and it is not mapped to any bucket.
3. `UNASSESSED` is never merged into `NONE` (D-7).
4. When `band_rows` returns no row for the identity, every linked deal is `UNASSESSED`, the totals
   are unchanged, and the scope-level note `NO_ASSESSMENT_FOR_SCOPE` is emitted. This is not an
   error.

#### A12.4 The no-blend invariant [R]

Sources: strategy §4.3; the frozen plan §A25 test 5.

1. No value in the view is computed from a band and an amount together. A band only selects the
   bucket in which a deal's amounts are summed.
2. No amount is multiplied, discounted, weighted, scored or thresholded by a band.
3. [SD-3] Where bands and amounts both order a list, the order is lexicographic: band rank
   descending, then base unweighted exposure descending, then customer `source_id` ascending.
   Strategy §4.3 permits commercial impact to order equally-banded customers.
4. [MD-13] `app/pipeline/measures.py`, which holds every arithmetic rule, receives no band and
   imports no band type. `aggregation.py` uses `RiskBand` for bucket keys and rank only.
5. [MD-16] VS-02 changes nothing VS-01 computes. Risk ranking, band assignment, executive-worthiness
   and the three pinned payload hashes are regression checks at every gate.

Items 1 and 2 are the no-blend requirement and are authoritative. Items 3 to 5 are how this plan
keeps it: the tie-break order, the `measures.py` rule and the regression mechanism are governed by
the decisions tagged on them, not by the authority.

#### A12.5 Coincidence [SD-3]

`risk_coincidence` is the list of customer ids whose band is `CRITICAL`, `ELEVATED` or `WATCH` and
who hold at least one open valued deal, in the order of §A12.4 item 3. It is a filter and an order
over buckets already in the view. It adds no figure. It is how the view answers the objective's
"where commercial exposure coincides with relationship risk".

#### A12.6 The customer partition [MD-8]

A sixth partition, `by_customer`: one `CUSTOMER` bucket per customer holding at least one open
valued deal, and one `UNLINKED` bucket, always present, holding the deals with no customer. Each
`CUSTOMER` bucket carries the customer's band, or `UNASSESSED`.

Order: `CUSTOMER` buckets by base unweighted exposure descending, then key ascending; `UNLINKED`
last.

### A13. Limitations and data-quality notes

#### A13.1 Limitations

1. [R] (the brief) The absence of a `lost` stage is surfaced in the output as an explicit
   limitation.
2. [MD-18] The view's `limitations` is the list of **codes** below, in this order.
   `NO_LOST_STAGE` is present when the D1 stage vocabulary, read from the frozen configuration,
   holds no `lost` value. Every other code is always present.
3. [MD-18] The response's `limitation_texts` renders each code as the text below. These texts are
   **normative**: the implementation uses them character for character, and tests assert them as
   literals. There is no golden file. The text is outside `view_hash` (§A14.10).

| # | Code | Text |
|---|---|---|
| 1 | `NO_LOST_STAGE` | `The deal-stage vocabulary is {stages}. It records no lost outcome, so no win rate and no stage-conversion figure can be stated, and none is.` |
| 2 | `NO_ACTUAL_CLOSE_DATE` | `A closed deal carries an expected close date only. No actual close date exists.` |
| 3 | `NO_DEAL_HISTORY` | `Deals carry no creation or stage-change date. The pipeline is that of the data snapshot; as_of does not rewind it.` |
| 4 | `FX_STATED_ASSUMPTION` | `Base-currency figures use rate set {rate_set_version}, stated for {rate_as_of_date}. The rates are an assumption, not a market quotation, and are not matched to as_of.` |
| 5 | `SHARES_FOLLOW_RATES` | `Concentration shares are computed in the base currency and change with the rate set.` |
| 6 | `SOURCE_STATED_PROBABILITY` | `Weighted exposure multiplies each amount by the probability the source system states. It is not a forecast.` |
| 7 | `SINGLE_SOURCE_SYSTEM` | `Only source system {source_system} is included. Nothing is aggregated across source systems.` |
| 8 | `PERIOD_HORIZON` | `Expected-close periods are the twelve calendar months from the month of as_of. Later dates are grouped as LATER.` |
| 9 | `BAND_IS_NOT_MONEY` | `A risk band groups exposure and is never applied to an amount.` |

Placeholders: `{stages}` is the vocabulary's values ascending by code point, joined by `", "`;
`{rate_set_version}`, `{rate_as_of_date}` and `{source_system}` are the view's own values.

#### A13.2 Data-quality notes

1. [R] (plan §A23) A row that cannot be used is never silently dropped.
2. [MD-19] `data_quality` is a list of notes, each of the shape of §A14.9, ordered by `code`
   ascending and then `id` ascending, a null `id` first.

| Code | Emitted for | `fields` | `key` |
|---|---|---|---|
| `INCOMPLETE_DEAL` | an open deal with a null stage, amount, currency or probability | the null ones among those four, ascending | null |
| `NEGATIVE_AMOUNT` | an open deal with those four non-null and a negative amount | `["amount"]` | null |
| `STAGE_ACTIVITY_MISMATCH` | any deal, open or closed, whose stage is non-null and whose `is_active` equals "the stage is a closed stage" | `["is_active", "stage"]` | null |
| `OWNER_KEY_MISSING` | an open valued deal with a null `owner_source_id` | `["owner_source_id"]` | null |
| `OWNER_KEY_UNRESOLVED` | an open valued deal whose `owner_source_id` names no employee in the scope | `["owner_source_id"]` | the key |
| `CUSTOMER_KEY_MISSING` | an open valued deal with no customer and a null `customer_source_id` | `["customer_source_id"]` | null |
| `CUSTOMER_KEY_UNRESOLVED` | an open valued deal with no customer and a non-null `customer_source_id` | `["customer_source_id"]` | the key |
| `EXPECTED_CLOSE_MISSING` | an open valued deal with a null `expected_close_date` | `["expected_close_date"]` | null |
| `NO_ASSESSMENT_FOR_SCOPE` | the scope, when `band_rows` returns no row | `[]` | null |

3. [MD-19] A deal with a null stage draws no mismatch note. Owner, customer and close-date notes are
   emitted for valued deals only, because only they sit in the partitions those notes explain. A
   deal may draw several notes.

### A14. The view contract [MD-12]

This section is the whole output. Nothing may be added, renamed or omitted.

#### A14.1 Value domain

1. JSON values only: object, list, string, integer, boolean, `null`. **No JSON float anywhere.**
2. `dec` — a string, VS-01's `decimal_text` of a `Decimal`: plain notation, no exponent, no trailing
   zeros, `"0"` for zero.
3. `date` — a string, `YYYY-MM-DD`.
4. `id` — a canonical `source_id` string.
5. **Every key of every object is always present.** `null` appears only where a type says
   "or null".
6. Every list has the total order stated for it. "Ascending" means by Unicode code point.
7. The reserved keys `UNASSIGNED`, `UNRESOLVED`, `UNLINKED`, `OVERDUE`, `LATER`, `UNDATED`, `ALL`
   and `UNASSESSED` name pseudo-buckets. A canonical `source_id` equal to one of them, where it
   would be a bucket key, raises `PipelineDataError` (`500`).
8. The view contains no database id, no timestamp and no ingestion provenance (D-11), so two
   independently built databases with the same content yield the same view.

#### A14.2 Top-level object

| Key | Type |
|---|---|
| `view_version` | integer, `1` |
| `scope` | object, §A14.3 |
| `versions` | object, §A14.3 |
| `fx` | object, §A14.3 |
| `deal_counts` | object, §A14.5 |
| `open_pipeline` | Bucket, key `ALL`, over every open valued deal |
| `by_currency` | list of CurrencyBucket |
| `by_stage` | list of Bucket |
| `by_owner` | list of OwnerBucket |
| `by_expected_close` | list of PeriodBucket |
| `by_risk_band` | list of BandBucket |
| `by_customer` | list of CustomerBucket |
| `risk_coincidence` | list of `id` |
| `concentration` | object, §A14.7 |
| `open_deals` | list of OpenDeal, ascending by `id` |
| `closed_deals` | list of ClosedDeal, ascending by `id` |
| `data_quality` | list of Note |
| `limitations` | list of string: the codes of §A13.1 |

#### A14.3 `scope`, `versions`, `fx`

**`scope`** is `Scope.to_payload()` verbatim:

| Key | Type |
|---|---|
| `source_system` | string |
| `as_of` | `date` |
| `layer1_fingerprint` | string, 64 hex |
| `as_of_source` | string, always `EXPLICIT` |
| `entity_counts` | object: each of the seven entity type names → integer |

**`versions`**

| Key | Type |
|---|---|
| `pipeline_version` | integer |
| `rules_version` | integer |
| `linker_version` | string |

**`fx`**

| Key | Type |
|---|---|
| `base_currency` | string |
| `rate_set_version` | string |
| `rate_as_of_date` | `date` |
| `rate_set_digest` | string, 64 hex |
| `standing` | string, always `STATED_ASSUMPTION` |
| `source_note` | string |
| `rates` | list of `{currency: string, rate_to_base: dec}`, every rate of the set, ascending by `currency` |
| `used_currencies` | list of string, the currencies of the open valued deals, ascending |

#### A14.4 Amounts and buckets

**Amount**

| Key | Type |
|---|---|
| `currency` | string |
| `unweighted` | `dec` |
| `weighted` | `dec` |

**Bucket**

| Key | Type |
|---|---|
| `key` | string |
| `deal_count` | integer |
| `deal_ids` | list of `id`, ascending |
| `native` | list of Amount, one per currency the bucket's deals hold, ascending by `currency`. Never summed |
| `base` | Amount in the base currency |

An empty bucket has `deal_count` `0`, `deal_ids` `[]`, `native` `[]`, and `base` with both members
`"0"`.

Each extension adds keys to Bucket and removes none:

| Type | Added keys |
|---|---|
| **CurrencyBucket** | `rate_to_base`: `dec`. `key` is the currency |
| **OwnerBucket** | `kind`: `EMPLOYEE`, `UNASSIGNED` or `UNRESOLVED`. `basis`: `SOURCE_KEY_JOIN` for `EMPLOYEE`, else `null`. `carrier_field`: `deals.owner_source_id` for `EMPLOYEE`, else `null`. `unresolved_keys`: list of string, the distinct unmatched keys ascending, for `UNRESOLVED`; `[]` otherwise |
| **PeriodBucket** | `kind`: `OVERDUE`, `MONTH`, `LATER` or `UNDATED` |
| **BandBucket** | `customer_count`: integer. `customer_ids`: list of `id`, ascending |
| **CustomerBucket** | `kind`: `CUSTOMER` or `UNLINKED`. `band`: one of the four band values or `UNASSESSED`; `null` for `UNLINKED`. `executive_worthy`: boolean, the assessment's stored verdict; `null` when there is no assessment or for `UNLINKED` |

`by_stage` uses the plain Bucket.

#### A14.5 `deal_counts`

| Key | Type |
|---|---|
| `total` | integer: every deal in scope |
| `open` | integer |
| `open_valued` | integer |
| `open_unvalued` | integer |
| `closed` | integer |
| `unvalued_deal_ids` | list of `id`, ascending |
| `by_stage` | list of `{stage: string, total: integer, open: integer, closed: integer}` |

`by_stage` has one row per D1 stage value, ascending, always present, and then a final row
`UNSTAGED` for deals with a null stage, always present. `open = open_valued + open_unvalued` and
`total = open + closed`, in every row and overall.

#### A14.6 `risk_coincidence`

A list of `id`: §A12.5. `[]` when no banded customer holds an open valued deal.

#### A14.7 `concentration`

```
concentration: {
  by_customer: { unweighted: Concentration, weighted: Concentration },
  by_owner:    { unweighted: Concentration, weighted: Concentration }
}
```

**Concentration**

| Key | Type |
|---|---|
| `currency` | string, the base currency |
| `rate_set_version` | string |
| `total` | `dec`: `T` |
| `holder_count` | integer |
| `top` | list of `{key: string, pseudo: boolean, amount: dec, share: dec}`, §A11 item 5 |
| `cumulative` | list of `{holders: integer, share: dec}`, one per point of `CUMULATIVE_POINTS`, in that order, `holders` being the point itself (1, 3, 5) whatever the holder count; `[]` when `T` is zero |
| `hhi` | `dec` or `null` |
| `reason` | `NO_OPEN_EXPOSURE` when `T` is zero; otherwise `null` |

#### A14.8 Deals

**OpenDeal**

| Key | Type |
|---|---|
| `id` | `id` |
| `state` | `OPEN_VALUED` or `OPEN_UNVALUED` |
| `stage` | string or null |
| `is_active` | boolean, always `true` |
| `amount` | `dec` or null |
| `currency` | string or null |
| `probability` | `dec` or null |
| `expected_close_date` | `date` or null |
| `owner_source_id` | string or null |
| `owner` | `id` or null: the resolved employee |
| `customer_source_id` | string or null |
| `customer` | `id` or null: the resolved customer |
| `native_weighted` | `dec`; null when unvalued |
| `base_unweighted` | `dec`; null when unvalued |
| `base_weighted` | `dec`; null when unvalued |

**ClosedDeal** ([MD-5])

| Key | Type |
|---|---|
| `id` | `id` |
| `stage` | string or null |
| `is_active` | boolean, always `false` |

#### A14.9 Notes

**Note**

| Key | Type |
|---|---|
| `code` | string, a code of §A13.2 |
| `entity` | `deals`, or `null` for the scope-level note |
| `id` | `id`, or `null` for the scope-level note |
| `fields` | list of string, canonical field names, ascending |
| `key` | string or null: the unresolved source key |

#### A14.10 The hash, and what is served [MD-15]

The chain is fixed:

1. **The canonical object.** The view of §A14.2, built as plain JSON values.
2. **Canonical JSON.** VS-01's `canonical_json`: keys sorted, separators `(",", ":")`,
   `ensure_ascii=False`, `allow_nan=False`.
3. **The hash.** `view_hash = sha256(canonical_json(view).encode("utf-8")).hexdigest()`.
4. **What is served.** The response's `view` member is the same JSON value. The typed response model
   must serialise it without dropping, adding, renaming or defaulting any key: no `exclude_none`, no
   alias, no computed field. Key order in the served body is not significant, because step 2 sorts.
5. **The proof.** For any response, `canonical_json` of the parsed `view` member hashes to the
   served `view_hash`. Test 25 asserts it, and asserts that the served value equals the canonical
   object the service built.

What the hash covers: the scope, the versions, the whole rate set including its note, every figure,
every deal fact, every note and the limitation codes.

What it does not cover: `limitation_texts` and `citations`, which are derived from the view and
rendered outside it, as VS-01 keeps its narrative outside `payload_hash`. A wording correction
therefore changes no hash.

- *Use.* It makes determinism testable, and lets a later slice bind a decision to a view.
- *If MD-15 is rejected.* Determinism is asserted by comparing response bodies; `view_hash` leaves
  the response and the event; tests 3, 8, 20 and 25 are rewritten.

#### A14.11 The empty view

For a source system with no deal: `deal_counts` all zero, with its stage rows present;
`open_pipeline` empty; `by_currency` `[]`; `by_stage` three empty buckets; `by_owner` the two
pseudo-buckets, empty; `by_expected_close` fifteen empty buckets; `by_risk_band` six empty buckets;
`by_customer` the `UNLINKED` bucket, empty; `risk_coincidence` `[]`; the four concentration blocks
in their zero form; `open_deals` and `closed_deals` `[]`; `data_quality` the scope note alone;
`fx`, `scope`, `versions` and `limitations` as always.

### A15. API

1. [R] (plan §A19 convention) Additive. F1's envelope, request id and validation conventions are
   reused unchanged.
2. [SD-5] One route, a GET. There is no other route and no write.

| Route | Method |
|---|---|
| `/api/v1/pipeline/view` | GET |

3. [MD-12] **Query parameters.**

| Name | Type | Rule |
|---|---|---|
| `as_of` | date, **required** | [MD-10] |
| `source_system` | string, default `csv_demo`, length 1–100 | as VS-01's request field |

   An unknown query parameter is ignored, as on every existing GET route. No value is echoed in an
   error (F1 convention).

4. [MD-12] **Response `200` — `PipelineViewResponse`.**

| Key | Type |
|---|---|
| `view_hash` | string, 64 hex |
| `view` | the view, §A14 |
| `limitation_texts` | list of `{code: string, text: string}`, in `view.limitations` order |
| `citations` | list of `{kind: "record", entity: "deals", id: string, field: string}`, §A18.2 |

   The response models live in `app/api/v1/pipeline_schemas.py` and import no first-party package.
   The route declares `200`, `409`, `422` and `500` in OpenAPI, the last three with F1's
   `ErrorResponse`.

5. [MD-14] **Status semantics.** Errors use the frozen envelope
   `{"error": {code, message, details, request_id}}`.

| Status | Code | `details` | When |
|---|---|---|---|
| 200 | — | — | the view can be built, including the empty view (§A14.11) |
| 422 | `INVALID_REQUEST` | F1's validation list | `as_of` missing or not a date; `source_system` empty or longer than 100 |
| 409 | `FX_RATE_MISSING` | `{"currencies": [string, ascending], "rate_set_version": string}` | §A7.5 item 4 |
| 500 | `INTERNAL_ERROR` | none | a configuration file refused at load; `PipelineDataError`; any other failure |

   Fixed message: `FX_RATE_MISSING` — `the rate set holds no rate for a currency of an open deal`.

6. [R] (frozen `tests/integration/test_h4_api_contract.py`) The API's write operations stay exactly
   three.

### A16. Persistence and read-time behaviour

#### A16.1 Results [SD-5]

Nothing VS-02 computes is stored. There is no result table and no result cache. The view is
recomputed per request.

#### A16.2 Reads [MD-13]

A new persistence-only module, `app/persistence/repositories/pipeline_queries.py`, following plan
§0.3.11 D-M4-B1:

| Function | Returns |
|---|---|
| `deal_rows(session, source_system)` | every row of `deals` with that `source_system` and `source_entity = 'deals'`, as plain rows of `(source_id, stage, is_active, amount, currency, probability, expected_close_date, owner_source_id, customer_source_id)`, ordered by `source_id` |
| `band_rows(session, *, source_system, as_of, layer1_fingerprint, rules_version, linker_version)` | `(customer_source_id, band, executive_worthy)` for the identity of §A12.2, inner-joined to `customers`, ordered by customer `source_id`. An assessment whose customer was set null has no customer to attach a deal to and is not returned |

It imports no `app.intelligence`, `app.fx` or `app.pipeline` module, names no domain type, decides
nothing, writes nothing and logs nothing. `risk_queries.py` is not edited.

#### A16.3 Writes [SD-2]

None. The rate set is configuration (§A7.6) and nothing is stored (§A16.1), so VS-02 has no write
repository and writes no row to any table.

### A17. Failure modes

#### A17.1 Evaluation order [MD-14]

A request is evaluated in this order, and the first failing step decides the response:

1. Request validation → `422`.
2. Configuration: `pipeline_rules.yaml` and `fx_rates.yaml`, loaded lazily → a refused file is
   `500`.
3. Scope resolution. With an explicit `as_of` it cannot fail.
4. The rate set: the content loaded at step 2. Nothing further can fail here.
5. Facts: deals, edges, bands. A reserved-key collision or an unknown band → `500`.
6. The missing-rate check of §A7.5 item 4 → `409 FX_RATE_MISSING`.
7. The view, its hash, the event → `200`.

Consequence: an empty source system answers `200` with the empty view (§A14.11), which still names
its base currency and its rate set, because step 2 has loaded them.

#### A17.2 Situations

| Situation | Behaviour | Label |
|---|---|---|
| Empty source system, or no deals | `200`, the empty view | [R] plan §A23 |
| No open valued deal | `200`; concentration in its zero form | [MD-8] |
| Open deal that cannot be valued | counted, excluded from money, noted | [MD-2] |
| Deal with no owner, or an unresolved owner key | the two owner pseudo-buckets | [MD-7] |
| Deal with no customer | `UNLINKED`, with the missing or unresolved note | [SD-3] |
| No assessment for the scope, or partial coverage | `UNASSESSED` | [MD-9] |
| Invalid `fx_rates.yaml` or `pipeline_rules.yaml` | refused at first use naming the broken key; `500`; no partial view; other routes unaffected | [R] plan §A23 |
| `as_of` before all data, or in the future | permitted | [R] plan §A23 |
| Concurrent ingestion during a request | the request sees one REPEATABLE READ snapshot | [R] frozen `read_snapshot` |

### A18. Evidence and citations

#### A18.1 The guarantee [R]

Sources: strategy §7.4; context §17.3 binding 6; plan §A17. Every stated fact resolves to a canonical
record and field, or is a derived fact carried with its source facts and its derivation. No citation
is fabricated.

#### A18.2 Record citations

1. [R] (plan §A17) Every deal value the view states is cited as VS-01's frozen
   `RecordCitation("deals", source_id, field)`, built through the frozen type so that only citable
   fields can be named.
2. [MD-12] The cited fields:

   | Deal | Fields cited |
   |---|---|
   | open | `is_active` always; each of `stage`, `amount`, `currency`, `probability`, `expected_close_date`, `owner_source_id`, `customer_source_id` whose stated value is non-null; `customer_id` when `customer` is non-null |
   | closed | `is_active` always; `stage` when non-null |

   The response's `citations` list is that set, in each citation's frozen payload form, ordered by
   `id` and then `field`.
3. [MD-12] **What "resolves" means**, per field:
   - the record exists in the scope;
   - for every field except `customer_id`: the stored value, rendered by §A14.1's rule for its type,
     equals the value the deal entry states;
   - for `customer_id`: the stored foreign key is non-null, and the customer it references has the
     `source_id` the entry states as `customer`.

#### A18.3 Derived and structural facts [R]

Source: plan §A17, as amended by plan §0.6.14: a derived fact is carried with its source facts and
its derivation. That grounding requirement is authoritative. The field names the table relies on
(`deal_ids`, `basis`, `carrier_field`, the `fx` keys) are the view contract's and are governed by
MD-12.

| Fact | How it is grounded |
|---|---|
| An aggregate | its `deal_ids`, and the fixed rules of §A9 |
| A base amount | the deal's native value and the rate in `fx.rates`, under `fx.rate_set_version` and `fx.rate_set_digest` |
| An owner | the cited `owner_source_id`, and the bucket's `basis` and `carrier_field` |
| A band | the customer id, with `scope` and `versions`. That is the assessment's identity; no database id is used (D-11) |
| A share or HHI | the holder amounts in the same block, and §A11's definitions |

`risk_assessments` is not a canonical entity, and the rate set is configuration, not a record. The
frozen `RecordCitation` admits neither, so neither is cited as a record. Both are cited
structurally, as VS-01 cites a policy rule by its id.

#### A18.4 DOC-004

1. [R] (the brief) "DOC-004's stated INR pipeline figure is reproduced from the records."
2. [MD-17] **No production code reads document text.** `app/fx/` and `app/pipeline/` import neither
   the `Document` model, any document repository nor `app.evidence`, and call no function that
   returns a document's title or body. A boundary test asserts it. The one frozen function they call
   that touches the `documents` table is `resolve_scope`, which reads `source_id` and `record_hash`
   for the fingerprint (§A5).
3. [MD-17] **Reproduction.** In a named test and in the acceptance command: the INR native
   unweighted total of the open pipeline, rendered with two decimal places and comma grouping as
   `INR 47,342,500.00`, equals the text of DOC-004's citable span `[170, 187)`. OBSERVED: that span
   reads `INR 47,342,500.00`; the sentence is `[124, 188)`.
4. [MD-17] **Leave-out.** Two arms are built in the test database: arm A over the full corpus, arm B
   over the corpus without DOC-004. **Each arm is assessed by VS-01's assessment run after its
   corpus is fixed**, at the same `as_of`, because removing a document moves the fingerprint and
   assessments made before the removal would no longer join (§A12.2). Then:
   - every top-level key of the view **except `scope`** is identical between the arms, compared as
     canonical JSON;
   - `scope.layer1_fingerprint` and `scope.entity_counts.documents` differ, and so does `view_hash`.

   The test asserts both halves, so the only difference is proved to be the snapshot identity. This
   is strategy §7.5's answer-leakage test applied to VS-02, in the form VS-01's DOC-005 test takes:
   it compares what is computed, not the snapshot's identity.

- *If MD-17 is rejected.* The view gains a document reconciliation block, the pipeline package gains
  a document read, and item 2's structural guarantee is lost.

### A19. Determinism, sessions and transactions

1. [R] (plan §A24) A view is a pure function of the source system, `as_of`, the Layer 1 snapshot,
   the persisted assessments at that identity, the rate set and `pipeline_rules.yaml`.
2. [R] (plan §A24; context §17.3) No clock, no randomness, no environment read, no dict-order or
   locale dependence, no float.
3. [R] (plan §A24) Every list in the view has an explicit, total order (§A14).
4. [R] (plan §A24) Two requests over one snapshot return the same `view` value and one `view_hash`,
   in separate processes.
5. [MD-13] **Sessions.** The caller owns the session. In `app/pipeline/` exactly two modules accept
   a `Session`: `facts.py`, which reads, and `service.py`, which passes the caller's session to
   `resolve_scope` and to `facts.py`. No module of `app/fx/` accepts one. Every other VS-02 module
   is pure and imports no SQLAlchemy name. No VS-02 module commits, rolls back, flushes, begins or
   closes.
6. [SD-5] **The route** reads through the frozen `read_snapshot`: one REPEATABLE READ, read-only
   transaction covering the fingerprint, the deals, the edges and the bands. The transaction cannot
   write.
7. [MD-11] Loaded configuration is cached per process and loaded lazily (§A7.3).

### A20. Observability

1. [R] (plan §A21; frozen G2 test) Application logging goes through `log_event`. No monetary value,
   no customer identifier and no document text appears in any log line.
2. [MD-20] One event, `vs02.pipeline_view_built`, INFO, emitted by `service.py` after the view is
   built and before it returns. Fields, in order: `source_system`, `as_of`, `layer1_fingerprint`,
   `pipeline_version`, `rate_set_version`, `open_deal_count`, `unvalued_deal_count`, `view_hash`.
3. [MD-20] A request that fails emits nothing. No counter is added. The event is not transactional.

### A21. Security and boundaries [R]

Sources: strategy §9.1; plan §A22; context §17.3. Each row is asserted by
`tests/unit/test_vs02_boundary.py`.

**What is REQUIRED here.** The concern in each row, which is the control objective. The control that
realises it is governed by the decision concerned: the import and module lists by MD-13; the
no-document and no-ticket row by MD-17; the read-only row by SD-5; what the view's prose is, in the
prompt-injection and reflected-input rows, by MD-15 and MD-18; and the tests that assert the rows by
MD-22.

| Concern | Control |
|---|---|
| No executor | Over the transitive import closure of `app/fx/` and `app/pipeline/`: no outbound HTTP, SMTP or socket module, and no `app.connectors`, `app.ingestion`, `app.core.security` or `app.api` |
| Read-only | No session write method in either package |
| No clock, no randomness | The M1 boundary rules, applied to both packages |
| No document text, no ticket attribute | Neither package imports the `Document` or `SupportTicket` model, a document or ticket repository, `app.evidence`, `app.analysts` or `app.decisions` |
| VS-01 isolation | No Layer 1 or VS-01 package imports `app.fx` or `app.pipeline` |
| Prompt injection | Structurally impossible: no model and no prompt. The view holds no free-text business field of any record or document: no name, title, note or body. What it takes from records is identifiers, source keys, vocabulary values, numbers and dates, served as JSON strings and never interpreted. Its only prose is the rate set's authored `source_note`; limitation texts are fixed templates rendered outside the view |
| Reflected input | `{source_system}` in a limitation text is the request's own value, length-bounded, served as a JSON string and never interpreted |
| Disclosure | The route publishes amounts that `GET /api/v1/entities/deals` already publishes, and bands that `GET /api/v1/risk/assessments` already publishes. The hosted site has no authentication, VS-01's standing limitation |
| Secret hygiene | The canary check of the frozen G2 suite is repeated for the new route by test 24 |

### A22. Packages and dependency direction [MD-13]

#### A22.1 `app/fx/` — shared (strategy §11)

| Module | Holds |
|---|---|
| `rates.py` | the rate-set value type, the lazy loader for `fx_rates.yaml`, the digest |
| `convert.py` | `convert`, the arithmetic context, `ARITHMETIC_PRECISION`, `BASE_QUANTUM` |
| `errors.py` | `FxError`, `FxConfigError`, `FxRateMissingError` |

#### A22.2 `app/pipeline/` — slice-local

| Module | Holds |
|---|---|
| `config.py` | the lazy loader for `pipeline_rules.yaml`, and the methodology digest |
| `errors.py` | `PipelineError`, `PipelineConfigError`, `PipelineDataError` |
| `facts.py` | `DealFact`; the function that takes a session and reads deals, edges and bands; the classification of each deal (open, valued, owner state, customer state) and the deal-level notes of §A13.2 |
| `measures.py` | per-deal values and their constants; pure; receives no band |
| `aggregation.py` | the six partitions, concentration and coincidence; pure |
| `view.py` | the canonical object, `view_hash`, citations, the scope-level note, limitation codes and texts; pure |
| `service.py` | `pipeline_view(session, *, as_of, source_system)`: the evaluation order of §A17.1, and the event. It returns the view, its hash, the limitation texts and the citations |

#### A22.3 `config/intelligence/pipeline_rules.yaml`

```yaml
version: 1            # file format
pipeline_version: 1   # bumped whenever anything that can change a figure changes
closed_stages: [won]  # each must be a D1 stage value
```

1. Unknown keys are refused. The file names no rate-set version (§A7.3).
2. Every other parameter is a named constant in code: `ARITHMETIC_PRECISION`, the rounding mode,
   `WEIGHT_QUANTUM`, `BASE_QUANTUM`, `SHARE_QUANTUM`, `PERIOD_HORIZON`, `CONCENTRATION_TOP_N` and
   `CUMULATIVE_POINTS`.
3. **The methodology digest.** `sha256(canonical_json(...))` over `closed_stages` ascending and every
   constant of item 2, each as a string. `tests/unit/test_vs02_config.py` pins a literal map from
   `pipeline_version` to that digest, with the same never-edit rule as §A7.4. Changing a constant or
   `closed_stages` without bumping `pipeline_version` fails the build.

#### A22.4 Import allow-lists

Exhaustive for first-party imports: a first-party import not listed fails the boundary test. Standard
library and the third-party packages VS-01's boundary tests already exempt (`sqlalchemy`,
`pydantic`, `yaml`) are outside these lists.

| Module group | May import |
|---|---|
| `app/api/v1/pipeline.py` | `app.api.dependencies`, `app.api.errors`, `app.api.v1.pipeline_schemas`, `app.pipeline`, `app.fx.errors` |
| `app/api/v1/pipeline_schemas.py` | nothing first-party |
| `app/pipeline/*` | `app.pipeline` (siblings), `app.fx`, `app.relationships`, `app.intelligence` **except** `app.intelligence.signals`, `app.intelligence.bands` and `app.intelligence.windows` (VS-02 never computes a signal or a band, §A12.2), `app.normalization.config`, `app.persistence.repositories.pipeline_queries`, `app.core.logging` |
| `app/fx/*` | `app.fx` (siblings), `app.intelligence`, `app.normalization.config` |
| the new persistence module, `pipeline_queries.py` | `app.persistence.models`, `app.core.database` |

And the reverse: `app.fx` does not import `app.pipeline`; nothing under `app/persistence/` imports
either package; no Layer 1 or VS-01 package imports either package. The route catches
`FxRateMissingError`, importing it from `app.fx.errors` directly; it is not re-exported to disguise
the import (plan §0.7.12's rule).

#### A22.5 Test seams

[MD-13] The named tests of §A25 need three seams, and only these three are fixed here.

1. **Rate-set loading and substitution.** `app/fx/rates.py` follows the pair that
   `app/intelligence/config.py` already has in `load_risk_rules(path)` and `default_risk_rules()`:
   a loader that takes a path and returns a validated rate set, and a cached default over
   `config/intelligence/fx_rates.yaml`. `app/pipeline/config.py` does the same for
   `pipeline_rules.yaml`.
   - The pure modules (`measures.py`, `aggregation.py`, `view.py`) receive the rate set as an
     argument and never load it. Only `service.py` obtains the default.
   - A test that needs another rate set, or a refused file, authors a file of its own and loads it
     through the path loader. To reach the service or the route, it substitutes what the default
     returns for the length of the test. This is how test 8's changed rate, test 9's second missing
     currency and test 26's refused files are built.
   - No request parameter, environment variable or production code path selects a rate set, and
     `pipeline_view`'s signature (§A22.2) does not change.
2. **Stage vocabulary.** The pure builders that produce `by_stage`, `deal_counts.by_stage` and the
   `NO_LOST_STAGE` limitation receive the stage vocabulary as an argument. `service.py` supplies the
   frozen D1 vocabulary from `app.normalization.config.default_config()`. No pure module reads it
   for itself. Test 6's `lost` arm passes a different vocabulary to the builder.
3. **An aggregation-level entry point at M2.** From VS02-M2, `aggregation.py` exposes a callable
   that takes the classified deal facts, the rate set, the stage vocabulary and `as_of`, and returns
   the partitions of §A10. Tests 1 and 13–17 call it at M2, before `view.py` exists. M3 extends the
   same module with §A11 and §A12, and `view.py` consumes it.

Every other internal signature is implementation-private: names, parameter order, return types and
helpers are the implementer's, unless a section of this plan freezes one by name, as it does for
`convert`, `pipeline_view`, `deal_rows`, `band_rows` and `DealFact`'s fields.

### A23. Frontend [SD-6]

None. `frontend/**` is frozen for every milestone of this plan. The four frontend tests that pin
"Opens with VS-02" stay true.

### A24. Fixtures [MD-22]

No change to `data/demo/` or `data/fixtures/`. A new package `tests/fixtures/vs02/`, in the form of
`tests/fixtures/vs01/`: a manifest, and for each entry either a **delta** (CSV rows ingested through
Layer 1) or a **loader** (SQLAlchemy Core over the caller's session, never committing). Its guard
refuses any database whose name ends in neither `_test` nor `_vs02`.

Whether Layer 1 admits a row decides its form. VS02-M2 measures it per entry and records the form in
the manifest: a row D1 and D2 accept is a delta, a row they reject is a loader. Neither form touches
`data/`.

The entries, each exercising something the committed dataset does not (OBSERVED: it holds no
unvalued, unowned, unlinked, overdue or undated deal):

1. an open deal with a null amount, and one with a null probability;
2. an open deal with a negative amount;
3. an open deal whose `owner_source_id` is null, and one naming no employee;
4. an open deal with a null `customer_source_id`, and one with an unresolved one;
5. an open deal with a null `expected_close_date`;
6. a deal that is active with stage `won`, and one inactive with stage `negotiation`;
7. a deal and an employee in a second source system (M2's `other_demo` precedent);
8. an open valued deal in `GBP`, a D1 currency the rate set does not hold;
9. the corpus without DOC-004;
10. a customer whose `source_id` is the reserved key `UNLINKED`, holding one open valued deal.

### A25. Evaluation

[R] (plan §A25) The layers: unit, contract, integration, end-to-end, acceptance.

**Named tests.** Each states its level, the milestone at whose gate it first passes, and its label.
A test labelled [R] proves a REQUIRED statement; the rest are [MD-22].

| # | Test | Level | First passes | Label |
|---|---|---|---|---|
| 1 | **Per-currency reproduction.** The open pipeline's native figures equal Appendix 1's | aggregation over the ingested dataset | M2 | [R] |
| 2 | **DOC-004 reproduction.** §A18.4 item 3 | view | M3 | [R] |
| 3 | **DOC-004 leave-out.** §A18.4 item 4, both halves | view | M3 | [MD-22] |
| 4 | **Reconciliation.** For all six partitions, for count, native and base, weighted and unweighted: the buckets sum exactly to the total, and every open valued deal is in exactly one bucket | view | M3 | [R] |
| 5 | **Base labelling.** Every base aggregate identifies the base currency through the view's `fx.base_currency`: each `base` Amount and each Concentration block names a `currency` equal to it. The view names the rate-set version and digest once, in `fx`. Per-deal `OpenDeal` base values carry no currency field of their own and are governed by `fx.base_currency`. Asserted by walking the whole view | view | M3 | [R] |
| 6 | **Lost-stage limitation.** `NO_LOST_STAGE` is present with its exact text; with a stage vocabulary containing `lost` passed to the builder, it is absent. No key of §A14 names a win rate, a conversion or a forecast | view | M3 | [R] |
| 7 | **Mixed currency.** `MoneyValue` still raises across currencies; no VS-02 path sums two currencies | unit | M2 | [R] |
| 8 | **FX liveness.** A changed USD rate changes every base figure that includes a USD deal and no native figure; the digest and `view_hash` change | view | M3 | [MD-22] |
| 9 | **Missing rate.** With fixture 8, the service raises once, naming `GBP`; with two such currencies it names both, ascending. No view is returned | service | M3 | [MD-22] |
| 10 | **No blend.** Permuting the band labels of the assessments moves deals between buckets and changes no amount, no total and no concentration figure | view | M3 | [R] |
| 11 | **Coverage.** With no assessment: every linked deal is `UNASSESSED`, totals unchanged, the scope note present. With one customer assessed: that customer is banded and the rest are `UNASSESSED` | view | M3 | [MD-22] |
| 12 | **Stale assessments ignored.** An assessment at another `as_of`, fingerprint or rules version is not joined | view | M3 | [MD-22] |
| 13 | **Periods and the horizon.** Always fifteen buckets. At `2026-09-18`: Appendix 1. At `2027-01-15`: 11 overdue, 19 in the window. At `2025-01-01` and at `1900-01-01`: all 30 in `LATER`. A deal expected on `as_of` is in its month; a null date is `UNDATED` | aggregation | M2 | [MD-22] |
| 14 | **Owners.** `UNASSIGNED` and `UNRESOLVED` stay distinct, with their notes; another source system's employee is never joined | aggregation | M2 | [MD-22] |
| 15 | **Unvalued deals.** Fixtures 1 and 2 are counted, excluded from money, listed and noted; `open_valued + open_unvalued = open` | aggregation | M2 | [R] |
| 16 | **Scope isolation.** A second source system's deals appear in no figure | aggregation | M2 | [R] |
| 17 | **VS-01 equivalence.** For every customer with no negative-amount open deal, VS-02's native unweighted open exposure per currency equals VS-01's `exposure_by_currency`. On the committed dataset that is every customer. With fixture 2, the difference is exactly that deal | aggregation | M2 | [MD-22] |
| 18 | **Concentration.** Shares, cumulative shares and HHI equal hand-computed values; fewer than five holders; a zero total gives the zero form | view | M3 | [MD-22] |
| 19 | **Multi-currency customer.** CUST-042's bucket shows INR and USD natively and one base amount | view | M3 | [MD-22] |
| 20 | **Determinism and read-only.** Two processes return one `view_hash`; building a view changes no row count in any table | service | M3 | [R] |
| 21 | **Citations.** Every citation resolves under §A18.2 item 3 | view | M3 | [R] |
| 22 | **Arithmetic bound.** The largest amount `Numeric(15, 2)` holds, at probability `99.99` and a rate with 10 integer digits and 8 decimal places, weights and converts to the exact expected value | unit | M2 | [MD-22] |
| 23 | **Withdrawn in v2.1.** It tested rate-set registration, which SD-2 removed. The number is not reused | — | — | — |
| 24 | **Status semantics.** Over HTTP: `200` and the empty view; `422` for a missing or malformed `as_of`; an unknown query parameter ignored; `409 FX_RATE_MISSING` with its details; `500` for a refused configuration and for fixture 10; the envelope and request id; the read-only transaction; the secret canary | HTTP | M4 | [MD-22] |
| 25 | **Served representation.** §A14.10 item 5; every key of §A14 present, on the committed dataset, the empty view and the fixtures | HTTP | M4 | [MD-22] |
| 26 | **Configuration isolation.** With a refused `fx_rates.yaml` or `pipeline_rules.yaml`, the pipeline route answers `500` and every Layer 1 and VS-01 route answers as before | HTTP | M4 | [MD-22] |
| 27 | **Unknown band.** A stored band outside `RiskBand` raises `PipelineDataError` and yields no view | view | M3 | [MD-22] |

**Boundary tests [MD-22].** `tests/unit/test_vs02_boundary.py` asserts every row of §A21 and every
line of §A22.4, each with a negative control in M8's style: a forbidden edit to a copy of the real
source must be caught. The file exists from M1 and gains each milestone's rows as its modules arrive.

### A26. Acceptance criteria (binary) [MD-16]

The form is VS-01's (plan §A27). Four criteria restate the brief's own acceptance clauses and are
[R]: 4 (DOC-004 reproduced), 5 (base currency and rate-set version named), 6 (totals reconcile) and
7 (the absent `lost` stage surfaced). The rest are this plan's.

1. `make verify-vs02` exits 0 against a database built by the clean full-dataset path (233 rows, 7
   entity types), with the pinned fingerprint matched.
2. The open pipeline holds 30 deals, all valued, and its native figures equal Appendix 1.
3. All six partitions of Appendix 1 are reproduced, and each sums exactly to the total.
4. DOC-004's figure is reproduced. With DOC-004 removed, every view key except `scope` is identical.
5. Every base aggregate names its base currency; the view names the rate-set version, digest, date
   and standing.
6. The base total equals the sum of the per-currency base figures exactly, and each currency's hand
   check is within the bound of §A9.4.
7. `NO_LOST_STAGE` is in the view, with its text in the response.
8. The band cross-tabulation equals Appendix 1's and sums exactly to the total, and test 10 passes.
9. Before any assessment is run, every customer is `UNASSESSED` and the totals are identical.
10. A missing rate returns `409 FX_RATE_MISSING` and no figure.
11. Two runs give one `view_hash`, and a request writes nothing.
12. The served `view` hashes to the served `view_hash`.
13. Every citation resolves.
14. Named tests 1–22 and 24–27 pass.
15. VS-01 is unharmed: `make verify-vs01` exits 0, and the golden file's hash and the three payload
    hashes are unchanged.
16. Regression: the full suite passes with 0 failed and 0 skipped; `app/` coverage is 100%; ruff 69;
    mypy 9; secret scan 0; one migration head.

Base-currency **numbers** are criteria: VS02-M0 pinned them on 2026-10-01. The rates are approved
(U-1), and M0 computed the base figures from them and recorded them, by the approved amendment of
§B6: the open pipeline is INR 73,442,577.10 unweighted and INR 32,375,999.45 weighted, and Appendix
2 holds every pinned figure. They join criteria 3, 6 and 8.

### A27. The acceptance command [MD-16]

`scripts/vs02_acceptance.py` and `make verify-vs02`, in the form of `scripts/vs01_acceptance.py`.

1. It recreates its own database, `<configured database>_vs02`, and never opens the development
   database or the Docker stack.
2. It migrates, and ingests `data/demo/` **in process** with `run_ingestion` and no entity filter,
   as VS-01's command does.
3. It serves the working-tree application on a loopback socket and drives it over HTTP.
4. Its only non-GET request is `POST /api/v1/risk/assessments`, pinned by a unit test.
5. It checks only what is observable on its clean database. It never mutates the corpus or the rate
   set. Every property that needs a mutation — leave-out, missing rate, no-blend, coverage, stale
   assessments — is proved by a named test, which `V2.13` runs.
6. It reads the pinned fingerprint and the acceptance date through `app.intelligence`, as VS-01's
   command does. It imports nothing from `app.decisions`, `app.evidence` or `app.analysts`.
7. It prints one line per check — an id, a name, `PASS`, `FAIL` or `SKIPPED`, and one line of
   observed evidence — and a summary. Exit 0 only when no check failed.
8. Options: `--with-tests`, which enables `V2.14` and `V2.15`; without it they are `SKIPPED`.

Checks, in order:

| Id | Name | Observes |
|---|---|---|
| `V2.1` | `clean_dataset` | head; 233 rows over 7 entity types; `SUCCESS` then `NOOP` |
| `V2.1b` | `pinned_fingerprint` | the view's `scope.layer1_fingerprint` equals VS-01's pinned value |
| `V2.1c` | `rate_set` | the authored set loads and its digest equals the pin |
| `V2.2` | `unassessed_view` | criterion 9, before any assessment |
| — | | `POST /api/v1/risk/assessments` at the acceptance date |
| `V2.3` | `native_totals` | criterion 2 |
| `V2.4` | `partitions` | criterion 3 |
| `V2.5` | `doc004_reproduction` | DOC-004's `title` and `body_text`, read through `GET /api/v1/entities/documents` and joined as VS-01's citable text (the title, one line feed, the body); its span `[170, 187)` against the INR total |
| `V2.6` | `base_labelling` | criterion 5 |
| `V2.7` | `reconciliation` | criterion 6, with the observed hand-check differences |
| `V2.8` | `lost_stage_limitation` | criterion 7 |
| `V2.9` | `risk_band_crosstab` | criterion 8's figures |
| `V2.10` | `determinism` | two requests, one hash; every table's row count unchanged |
| `V2.11` | `served_hash` | criterion 12 |
| `V2.12` | `citations` | every citation against `GET /api/v1/entities/deals` and `/customers`, by §A18.2 item 3 |
| `V2.13` | `named_tests` | pytest over the named tests of §A25 |
| `V2.14` | `vs01_unharmed` | `scripts/vs01_acceptance.py` as a subprocess, exit 0. `--with-tests` only |
| `V2.15` | `regression` | criterion 16. `--with-tests` only |

### A28. Mutation audit [MD-22]

The project's ad-hoc textual harness, under M9's binary rule (plan §0.8.12, R-M9-5): every mutant is
killed, or proved equivalent in writing. The mutant list is fixed and hashed before the first run.

| Target | Files, each in full |
|---|---|
| FX | `app/fx/rates.py`, `app/fx/convert.py`, `config/intelligence/fx_rates.yaml` |
| Per-deal measures | `app/pipeline/measures.py` |
| Partitions, concentration, coincidence | `app/pipeline/aggregation.py`, `config/intelligence/pipeline_rules.yaml` |
| Fact classification | `app/pipeline/facts.py` |
| The reads, including the band identity filter | `app/persistence/repositories/pipeline_queries.py` |
| The view, its hash, notes and citations | `app/pipeline/view.py` |

Not targeted: `service.py`, the route and the response models, which the milestone tests and tests
24–26 cover. Recorded as a limitation (§A29).

### A29. Known limitations [R]

Source: strategy §14 item 7: limitations are documented. That duty is what is REQUIRED. Each entry
below is conditional on the decision that generates it (among them MD-2, MD-6, MD-8, MD-9, MD-11,
MD-20, MD-22 and SD-5) and stands only while that decision stands. This is the documentation list;
the nine codes of §A13.1 are the subset the view itself states. The README carries this list.

No lost stage, so no win rate or conversion; no actual close date; no deal history, so `as_of` does
not rewind the pipeline; the rates are an assumption and are not matched to `as_of`; concentration
shares move with the rate set; probabilities are the source's stated values; a single source system;
periods are calendar months over a twelve-month horizon, with no fiscal calendar; the scope's
fingerprint covers all seven entity types, so any Layer 1 change gives the view a new scope and a new
`view_hash` although no figure moves; the band cross-tabulation shows `UNASSESSED` until VS-01's
assessment has been run for the same date and snapshot; a band joined under a rules version is not
revalidated; a negative-amount deal is described by VS-01 and not valued by VS-02; the view is not
persisted, so there is no history of past views; the log event is not transactional; the mutation
audit does not cover the service or the route; the dataset is synthetic, 233 rows; the route is
unauthenticated.

### A30. Out of scope

This is the single list.

1. [R] **By authority** (the brief, strategy §10.2; strategy §14; plan §A31; context §17.3):
   forecasting; win rate; stage conversion; quota; territory analysis; any model or prompt; any
   executor; any write to a source system; `now()` in any module; widening the D1 vocabulary;
   cross-source aggregation; authentication; changes to `data/`; any change to a Layer 1 or VS-01
   module's behaviour; a new storage engine or service of any kind.
2. **By this plan's decisions**, each excluded only once its decision is approved:
   - [SD-2] an `fx_rates` table, a migration, a registration command, or any stored copy of the
     rate set;
   - [SD-4] a brief, a position, an action or an approval;
   - [SD-5] result persistence or history; any write route;
   - [SD-6] any frontend work;
   - [MD-5] closed-deal amounts;
   - [MD-6] quarter, half or fiscal-year roll-ups;
   - [MD-7] an owner-to-manager roll-up;
   - [MD-11] a time series of rates;
   - [MD-12] a rates route; a per-customer or per-deal drill-down route; pagination;
   - [MD-21] any new dependency.

---

# Part B — Governance

### B1. Allowed and frozen paths [MD-21]

Anchors are `523210a`. The rule that such a table exists is VS-01's (plan §0.7.15, §0.8.13); this
table's content is MD-21, and approving it authorises each additive edit to a frozen file it names.

| Path | VS-02 may | Scope |
|---|---|---|
| `app/fx/{__init__,rates,convert,errors}.py` | create | §A22.1 |
| `app/pipeline/{__init__,config,errors,facts,measures,aggregation,view,service}.py` | create | §A22.2 |
| `app/persistence/repositories/pipeline_queries.py` | create | §A16.2 |
| `app/api/v1/pipeline.py`, `app/api/v1/pipeline_schemas.py` | create | §A15 |
| `config/intelligence/fx_rates.yaml`, `config/intelligence/pipeline_rules.yaml` | create | §A7.3, §A22.3 |
| `scripts/vs02_acceptance.py` | create | §A27 |
| `tests/unit/test_vs02_*.py`, `tests/unit/vs02_support.py`, `tests/integration/test_vs02_*.py`, `tests/e2e/test_vs02_scenario.py`, `tests/fixtures/vs02/` | create | §A24, §A25 |
| `app/api/v1/router.py` (frozen) | edit, additively | one import and one `include_router` |
| `app/api/errors.py` (frozen) | edit, additively | `FX_RATE_MISSING` appended after M8's members |
| `Makefile` (frozen) | edit | one new target, `verify-vs02`: its `.PHONY` entry, one `help` line and its recipe. No other line changes |
| `README.md` | edit | §B3 only |
| The frozen tests of §B2 | edit | exactly as §B2 states |
| `CONTEXT/VS02_IMPLEMENTATION_PLAN.md` | edit | this document |
| `CONTEXT/AI_CEO_PROJECT_CONTEXT.md` | append | one phase record, in the closure commit |
| Every other file under `app/`, including all of `app/intelligence/`, `app/relationships/`, `app/evidence/`, `app/analysts/`, `app/decisions/`, `app/main.py`, `app/api/v1/{risk,schemas}.py` and every existing model and repository | **frozen** | — |
| The three existing files of `config/intelligence/`; `config/mappings/`; `config/validation/`; `config/connectors/` | **frozen** | — |
| Every existing migration; `migrations/env.py`; `alembic.ini` | **frozen** | no migration is added (SD-2) |
| `scripts/vs01_acceptance.py` | **frozen** | VS-01's acceptance command is not edited (SD-2) |
| `data/`; `tests/golden/`; `tests/conftest.py`; `tests/fixtures/vs01/`; every test not named in §B2 | **frozen** | — |
| `frontend/**`; `vercel.json` | **frozen** | SD-6 |
| `Dockerfile`, `docker-compose.yml`, `docker/`, `.dockerignore`, `.env.example`, `.gitignore`, `pyproject.toml` | **frozen** | no new dependency |
| `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md` | **never touched and never staged** | the owner's uncommitted change |
| Every other `CONTEXT/` file | **frozen** | — |

### B2. Test evolution

#### B2.1 The evolutions

The governing rule is VS-01's (plan §0.4.4) [R]: **extend, move, re-scope or replace only the
obsolete assertion, and never weaken the surrounding test.** Each row is an edit to a frozen test
and needs the owner's authorisation; none is applied without it. Line numbers are OBSERVED at
`523210a`.

**Authorised on 2026-10-01, exactly these ten:** T-VS02-1a, T-VS02-1b, T-VS02-1c, T-VS02-2,
T-VS02-3a, T-VS02-3b, T-VS02-3c, T-VS02-4, T-VS02-5 and T-VS02-10. No other row is authorised: not
the withdrawn T-VS02-6, not the removed T-VS02-7…9, and not any row VS02-M0 may propose. Each
authorised row is applied only in the milestone §B2.2 names.

| # | Test / file | Assertion affected | Evolution |
|---|---|---|---|
| T-VS02-1a | `tests/unit/test_m1_boundary.py:56` | `LAYER2_PACKAGES`, the importers of `app.intelligence` | add `"app/fx/"` |
| T-VS02-1b | same | same | add `"app/pipeline/"` |
| T-VS02-1c | same | same | add `"scripts/vs02_acceptance.py"`, one file, never `scripts/` |
| T-VS02-2 | `tests/unit/test_f1_openapi.py:54–66` and `:94–110` | (a) the exact operation set; (b) the `expected` map of `test_success_responses_reference_named_models`, which looks up every published operation and raises on one it does not hold | (a) add `("get", "/api/v1/pipeline/view")` to the union; (b) add `("get", "/api/v1/pipeline/view"): ("200", "PipelineViewResponse")` to the map |
| T-VS02-3a | `README.md`, checked by `tests/unit/test_i2_readme.py:250` | the per-layer test counts | re-quote the counts. README content only |
| T-VS02-3b | `README.md`, checked by `test_i2_readme.py:195, :228` | every route and every `ErrorCode` documented | document the route and the new code. README content only |
| T-VS02-3c | `README.md` | — | the VS-02 section (§B3) |
| T-VS02-4 | `tests/unit/test_i2_readme.py:167` | the `(heading, script)` parameters | add the VS-02 section with `vs02_acceptance` |
| T-VS02-5 | `tests/unit/test_g2_security_boundary.py:35, :46` | `SUBPROCESS_MODULES`, `HTTP_CLIENT_MODULES` | add `scripts/vs02_acceptance.py`, named as one file, with its reason, as T-M9-2 and T-M9-3 did |
| T-VS02-6 | — | — | **withdrawn in v2.** ruff 69 and mypy 9 are fixed (§B5); a moved count is a failure to fix, not a number to re-quote |
| T-VS02-10 | `tests/unit/test_m8_api_schemas.py:68` | `[code.value for code in ErrorCode] == [*LAYER_1_ERROR_CODES, *M8_ERROR_CODES]` | the right-hand side becomes `[*LAYER_1_ERROR_CODES, *M8_ERROR_CODES, *VS02_ERROR_CODES]`, with `VS02_ERROR_CODES = ("FX_RATE_MISSING",)`. The test's name and its second assertion are kept |

T-VS02-7, T-VS02-8 and T-VS02-9 were removed in v2.1. They evolved the migration-head, table-set and
VS-01 acceptance pins, which a configuration rate set does not touch (SD-2). The numbers are not
reused.

#### B2.2 The schedule [MD-16]

Each evolution is applied in the milestone whose change first contradicts the frozen assertion, in
that milestone's single commit. The last column is the state the gate must show.

| Milestone | Change that trips a frozen assertion | Evolution applied | Gate |
|---|---|---|---|
| M0 | none; the repository is unchanged | none | baseline |
| M1 | `app/fx/` imports `app.intelligence` | T-VS02-1a | green |
| M1 | new tests change the counts | T-VS02-3a | green |
| M2 | `app/pipeline/` imports `app.intelligence` | T-VS02-1b | green |
| M2 | counts | T-VS02-3a | green |
| M3 | counts | T-VS02-3a | green |
| M4 | the route is published | T-VS02-2, T-VS02-3b | green |
| M4 | `ErrorCode` gains its member | T-VS02-10 | green |
| M4 | counts | T-VS02-3a | green |
| M5 | `scripts/vs02_acceptance.py` exists, runs a subprocess, builds an HTTP client and imports `app.intelligence` | T-VS02-5, T-VS02-1c | green |
| M5 | the README's VS-02 section and its options table | T-VS02-3c, T-VS02-4 | green |
| M5 | counts | T-VS02-3a | green |

Not evolutions, because the frozen tests already state the rule a new file must meet: a new Make
target needs its `.PHONY` entry, a recipe and a `make <target>` help line
(`tests/unit/test_i1_verify_units.py:1170`); a recipe that runs Python uses `.venv/bin/`.

#### B2.3 Expected to pass unchanged [U-7]

Read and expected not to change; VS02-M0's census confirms it:
`tests/integration/test_h4_api_contract.py` (the new route is a GET with no path parameter and no
pagination); `tests/integration/test_g2_secret_canary.py`; `tests/unit/test_m2_boundary.py`
(`app/relationships/` is not edited); `tests/unit/test_m6_boundary.py`, `test_m7_boundary.py` and
`test_m8_boundary.py` (nothing is added to or imports `app/decisions/`);
`tests/unit/test_e1_boundary.py`, `test_f1_boundary.py` and the G2 scans, which cover the new
repository and route as written; `tests/unit/test_b1_models.py` and the table-count helpers that
iterate `Base.metadata` (no model is added); `tests/integration/test_m8_migration.py`,
`tests/integration/test_h3_migrations.py` and `tests/unit/test_vs01_acceptance.py` (no migration or
table is added, and the head does not move).

Confirmed by VS02-M0 on 2026-10-01: the scratch run's nine failing frozen tests all fall under rows
of §B2.1, and no other frozen test failed (§0.11).

**Anything not in §B2.1 is not authorised.** A further contradiction is reported, and
implementation stops until the owner rules.

### B3. README [R]

Source: the frozen `tests/unit/test_i2_readme.py`, which fails unless the README documents every
published route and error code and quotes the real counts. That requirement is authoritative. The
content of item 1's section and the mechanics of each README edit are governed by the test
evolutions T-VS02-3a, 3b, 3c and 4 and by MD-16's schedule.

1. One new section, `## VS-02 Revenue and Pipeline Intelligence`, after the VS-01 section: what it
   needs, the acceptance command and its options table, the checks, the reconciliation hand check
   and its bound, that rounded shares need not sum to 1, and the limitations of §A29. (T-VS02-3c, M5)
2. The new route and its error code in the API section. (T-VS02-3b, M4)
3. The per-layer test counts, re-quoted in every milestone's commit. (T-VS02-3a)
4. It never claims a forecast, a win rate, a market rate or a production system.

No other README line changes.

### B4. Migration and hosting

| | VS-02 | Label |
|---|---|---|
| Migration | none. The head stays `070e4968a497` | [SD-2] |
| Local development | nothing to run | [SD-2] |
| Test, acceptance and frontend databases | unchanged | [SD-2] |
| Hosted database | unchanged: no migration and no data step | [SD-2] |
| Hosted actions, if the owner ever approves a deployment | deploy the code only | [SD-2] |
| Docker image | no Dockerfile change: `app/` and `config/` are already copied | [R] frozen `test_docker_packaging.py` |

[R] (git-release discipline; frontend specification §14) Every deployment, every hosted migration
and every push is a separate outward action and needs its own explicit approval. None is part of any
milestone's gate ([U-6]).

[R] (X8) The development database is never read, written or migrated by VS-02. Rebuilding it is the
owner's decision.

### B5. Baseline, regression and the gate [MD-16]

The form is VS-01's (plan §0.8.14).

**The environment.** The repository's `.venv`; the suite's own `<database>_test` harness; lint caches
outside the repository (M8's trap). Never the development database or the Docker stack.

**The baseline** is the re-measurable rows of §0.1: HEAD and the working tree; the frozen-path diff
against `523210a`, which is empty; one head; the suite's counts per layer with 0 failed and 0
skipped; `app/` coverage; ruff 69; mypy 9; secret scan 0; the golden file's hash; VS-01's three
payload hashes; the strategy document's diff hash; and `make verify-vs01` exiting 0. The development
database and the hosted site are not part of it.

**Warnings.** The suite reports 2 warnings, or 3 when the intermittent pydantic warning of the frozen
M8 concurrency test appears. The owner's ruling of 2026-10-01 (F6) that the third passes is carried
forward. Any other warning stops the phase.

**The gate rule.**
1. At every milestone gate the full suite shows 0 failed and 0 skipped. No test is knowingly left
   failing at a gate.
2. Each evolution of §B2.1 is applied in the milestone §B2.2 names, in that milestone's commit.
3. While a milestone is in progress, the only failures expected are that milestone's scheduled
   assertions, until its evolution is applied. Any other failure stops the work and is reported.
4. Every gate also reports coverage, ruff, mypy, the secret scan over tracked and new files, the head
   check, the frozen-path diff, the golden and payload hashes, `make verify-vs01`, and `git status`,
   which may show only VS-02's allowed paths and the strategy document.

**The pass condition.** Every measurement equals the baseline except: the test counts VS-02's tests
add; the statement count, which grows with coverage kept at 100%; the README quotations that follow
them; and the secret scan's file count. The migration head does not move. ruff stays 69 and mypy
stays 9: new code adds no finding. Any other difference stops the phase.

### B6. Milestones [MD-16]

One commit per milestone, verified before the next begins. Dependency order:
`M0 → M1 → M2 → M3 → M4 → M5`; every edge is hard.

**VS02-M0 — Pre-flight baseline.** The repository's production code and tests are not changed.

1. Re-measure the baseline of §B5.
2. **Pin census, by reading.** Search the frozen tests for exact-set and exact-list assertions over:
   `ErrorCode`, the OpenAPI operations, table sets, migration heads, importer allow-lists, module
   inventories, Makefile targets and README parametrisations.
3. **Pin census, by a scratch run.** Copy the working tree to a directory outside the repository. In
   the copy only, add empty stubs for each new path of §B1 that a frozen scan could see: the two
   packages importing `app.intelligence`, the route with its error code, and the acceptance script.
   Run the frozen suite in the copy against the harness database. Record every failing frozen test.
   Delete the copy. The repository is unchanged.
4. Every failure not already in §B2.1 is reported with a proposed T-VS02 row. The milestone stops,
   and nothing is changed until the owner authorises the row.
5. **Owner input (U-1).** Record the rate set's `as_of_date` and `source_note`, as the owner supplies
   them. Neither is invented, defaulted or taken from a source the owner did not name. M0 does not
   close without both.
6. Compute the base-currency expectations from the approved rates, by a scratch calculation
   independent of any VS-02 code. No base figure depends on the date or the note.
7. **Output:** an amendment to this plan only — the status row, any §B2.1 additions, the rate set's
   date and note in §A7.3, the pinned base figures in §A26 and Appendix 2 — committed alone on the
   owner's approval.

Closed on 2026-10-01: §0.11 is its record.

**VS02-M1 — FX foundation.**
- *Change.* `app/fx/`; `fx_rates.yaml`.
- *Tests.* Loader refusals, including a float rate and an unknown key; lazy loading; the digest and
  its pin; conversion; a missing rate; `MoneyValue` unchanged; `test_vs02_boundary.py` created with
  the rows that concern `app/fx/`.
- *Evolutions.* §B2.2's M1 rows.
- *Non-goals.* Any deal read, any route.

**VS02-M2 — Pipeline facts and aggregation.**
- *Change.* `pipeline_queries.deal_rows`; `app/pipeline/{config,errors,facts,measures}`; the four
  partitions of §A10 in `aggregation.py`; `pipeline_rules.yaml` and the methodology digest pin; the
  fixture package.
- *Tests.* Named tests 1, 7, 13–17 and 22; the boundary rows that concern `app/pipeline/`.
- *Evolutions.* §B2.2's M2 rows.
- *Non-goals.* Bands, the customer partition, concentration, the view, the route.

**VS02-M3 — Concentration, the band cross-tabulation and the view.**
- *Change.* `pipeline_queries.band_rows` and the band read in `facts.py`; §A11 and §A12 in
  `aggregation.py`; `view.py`; `service.py`.
- *Tests.* Named tests 2–6, 8–12, 18–21 and 27; the limitation texts as literals; the boundary rows
  for the new modules.
- *Evolutions.* §B2.2's M3 row.
- *Non-goals.* The route.

**VS02-M4 — API.**
- *Change.* `pipeline.py`, `pipeline_schemas.py`, the `ErrorCode` member, the router registration,
  the README's API entries.
- *Tests.* Named tests 24–26; the response schema; the boundary rows for the route and the response
  models, completing `test_vs02_boundary.py`.
- *Evolutions.* §B2.2's M4 rows.
- *Non-goals.* The acceptance command.

**VS02-M5 — Acceptance, evaluation and hardening.**
- *Change.* `scripts/vs02_acceptance.py`, `make verify-vs02`, the end-to-end scenario, the mutation
  audit and the tests it finds missing, the README section.
- *Acceptance.* All sixteen criteria of §A26.
- *Evolutions.* §B2.2's M5 rows.
- *Non-goals.* The frontend; any deployment; VS-03.

### B7. Commits [R]

Source: git-release discipline. Nothing is staged, committed, pushed, amended or rebased without the
owner's explicit approval for that action. Files are staged by explicit path. The author and
committer are the owner's identity. No commit carries an attribution trailer. The strategy document
is never staged.

The commits, in order [MD-16]:
1. `VS-02: finalize specification` — this file only, after the owner's review.
2. `VS-02: record the M0 baseline` — this file only: M0's amendment.
3. `VS02-M1: …` through `VS02-M5: …` — one per milestone, each with its evolutions and its README
   changes.
4. `docs: close VS-02 implementation plan` — this file's status table and closure notes, and the
   phase record appended to `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`.

---

## Appendix 1 — Dataset expectations, native (OBSERVED)

Measured from `data/demo/deals.csv` on 2026-10-01 with the rules of §A8–§A12, at `as_of`
2026-09-18. These figures do not depend on any rate.

**Counts.** 44 deals. Per stage, total / open / closed: negotiation 14 / 14 / 0; qualification
16 / 16 / 0; won 14 / 0 / 14; `UNSTAGED` 0. Open 30, all valued; closed 14.

**Open pipeline, by currency**

| Currency | Deals | Unweighted | Weighted |
|---|---|---|---|
| EUR | 1 | 96,633.33 | 38,653.33 |
| INR | 21 | 47,342,500.00 | 20,707,975.00 |
| USD | 8 | 193,373.46 | 91,796.37 |

The unrounded weighted sums are EUR 38,653.3320 and USD 91,796.3680; per-deal rounding gives the
figures above.

**By stage** (three buckets; `won` holds no open deal)

| Stage | Deals | INR unweighted / weighted | USD unweighted / weighted | EUR unweighted / weighted |
|---|---|---|---|---|
| negotiation | 14 | 23,340,000.00 / 15,675,500.00 | 92,319.26 / 70,995.17 | — |
| qualification | 16 | 24,002,500.00 / 5,032,475.00 | 101,054.20 / 20,801.20 | 96,633.33 / 38,653.33 |
| won | 0 | — | — | — |

**By owner** (`UNASSIGNED` and `UNRESOLVED` are present and empty)

| Owner | Deals | INR unweighted / weighted | USD unweighted / weighted | EUR unweighted / weighted |
|---|---|---|---|---|
| EMP-007 | 10 | 13,159,000.00 / 3,404,000.00 | 23,156.61 / 8,974.69 | — |
| EMP-008 | 7 | 8,942,500.00 / 4,999,500.00 | 56,921.68 / 39,692.16 | — |
| EMP-009 | 1 | 1,109,500.00 / 221,900.00 | — | — |
| EMP-010 | 12 | 24,131,500.00 / 12,082,575.00 | 113,295.17 / 43,129.52 | 96,633.33 / 38,653.33 |

**By expected close** (fifteen buckets; `OVERDUE`, `LATER` and `UNDATED` are empty, as are 2027-05 to
2027-08)

| Month | Deals | INR unweighted | USD unweighted | EUR unweighted |
|---|---|---|---|---|
| 2026-09 | 1 | 4,200,000.00 | — | — |
| 2026-10 | 3 | 2,105,500.00 | — | — |
| 2026-11 | 3 | 670,000.00 | 11,451.80 | — |
| 2026-12 | 3 | 249,000.00 | 56,921.68 | — |
| 2027-01 | 4 | 585,000.00 | 24,487.95 | — |
| 2027-02 | 2 | 770,500.00 | — | — |
| 2027-03 | 7 | 8,270,000.00 | 100,512.03 | — |
| 2027-04 | 7 | 30,492,500.00 | — | 96,633.33 |
| 2027-05 to 2027-08 | 0 each | — | — | — |

**By risk band**, after VS-01's assessment at 2026-09-18 (CUST-007 `CRITICAL`; CUST-025 and CUST-036
`WATCH`; no customer `ELEVATED`)

| Band | Customers | Deals | Native unweighted |
|---|---|---|---|
| CRITICAL | 1 (CUST-007) | 1 (DEAL-001) | USD 5,361.44 |
| ELEVATED | 0 | 0 | — |
| WATCH | 1 (CUST-036) | 1 (DEAL-037) | INR 499,000.00 |
| NONE | 21 | 28 | INR 46,843,500.00; USD 188,012.02; EUR 96,633.33 |
| UNASSESSED | 0 | 0 | — |
| UNLINKED | 0 | 0 | — |

CUST-025 is `WATCH` and holds no deal, so it is in no bucket. `risk_coincidence` is
`[CUST-007, CUST-036]`.

**By customer.** 23 `CUSTOMER` buckets, and `UNLINKED`, empty. Three customers hold open deals in two
currencies: CUST-029, CUST-042 and CUST-050. The order of the buckets depends on the rate set.

**DOC-004.** Citable span `[170, 187)` reads `INR 47,342,500.00`.

## Appendix 2 — Base-currency figures at the approved rates (pinned at VS02-M0)

**The rates are the owner's decision of 2026-10-01 (U-1): base INR; `USD = 85`, `EUR = 100`,
`INR = 1`. They are illustrative, authored rates: a stated assumption that comes from no market
source and no document. The set's date, `2026-10-01`, and its source note are the owner's, supplied
at VS02-M0 (U-1, §A7.3); no figure here depends on either.**

The figures below were this plan's calculation. VS02-M0 recomputed them independently on
2026-10-01, found every one equal, and pinned them (§0.11, §A26, §B6). They are acceptance figures.

| Figure | Unweighted | Weighted |
|---|---|---|
| Open pipeline, base | INR 73,442,577.10 | INR 32,375,999.45 |
| — from EUR | INR 9,663,333.00 | INR 3,865,333.00 |
| — from INR | INR 47,342,500.00 | INR 20,707,975.00 |
| — from USD | INR 16,436,744.10 | INR 7,802,691.45 |
| negotiation | INR 31,187,137.10 | INR 21,710,089.45 |
| qualification | INR 42,255,440.00 | INR 10,665,910.00 |
| CRITICAL | INR 455,722.40 | INR 410,150.50 |
| WATCH | INR 499,000.00 | INR 149,700.00 |
| NONE | INR 72,487,854.70 | INR 31,816,148.95 |

Concentration by customer, unweighted, 23 holders: CUST-042 0.2556, CUST-015 0.1742, CUST-037
0.1316, CUST-010 0.0911, CUST-049 0.0794; cumulative at 1, 3 and 5 holders 0.2556, 0.5614 and
0.7319; HHI 0.135. Weighted: CUST-015 leads at 0.2767; HHI 0.1369. By owner, unweighted, 4 holders:
EMP-010 0.5913, EMP-007 0.206, EMP-008 0.1876, EMP-009 0.0151; the cumulative share at 5 holders is
1; HHI 0.4275. Shares are shown as the view serialises them, without trailing zeros.

Under these rates the per-currency hand check differs from the per-deal sum by 0.00 for both USD and
EUR.

The ordering changes with the rates: in INR alone CUST-015 holds the largest open amount, and under
this set CUST-042 does. That is limitation `SHARES_FOLLOW_RATES`, shown concretely.

---

## Owner Decisions

### Decided on 2026-10-01

Recorded in §0.10: SD-1 to SD-6; MD-1 to MD-22; the rates of U-1; the owner's directions on U-2 to
U-7; the authorisation of ten test evolutions (§B2.1); the three clarifications of v2.1; and the
approval to commit this file alone as `VS-02: finalize specification`. Nothing in that list needs a
further ruling.

### Supplied at VS02-M0

| # | Input | Supplied | Reference |
|---|---|---|---|
| 1 | **U-1** The rate set's date and its source note | by the owner on 2026-10-01, in the owner's words, and recorded verbatim. Neither was invented | §0.9, §0.11, §A7.2, §A7.3, §B6 |

### Still required

Nothing. VS02-M0 is closed (§0.11): its census found no frozen-test contradiction outside the ten
authorised rows (U-7). VS02-M1 is authorised by the gate, is a separate task and begins only on the
owner's instruction. U-5 and U-6 block nothing in this plan.
