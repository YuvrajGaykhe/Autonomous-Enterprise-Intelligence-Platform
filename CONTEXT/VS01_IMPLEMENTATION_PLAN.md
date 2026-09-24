# VS-01 — Customer Risk & Executive Escalation: Implementation Plan (v2)
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**v1 2026-09-18 · v2 2026-09-18 after adversarial review · v2.1 2026-09-20, M2/M4 boundary ·
v2.2 2026-09-20, `deal_owned_by` scope decision · v2.3 2026-09-21, M3 closure ·
v2.4 2026-09-21, M4 decision resolution (§0.3) ·
v2.5 2026-09-21, M4 boundary clarification (§0.3.11) ·
v2.6 2026-09-22, M5 re-specification — six blockers closed (§0.4) ·
v2.7 2026-09-22, M5 second-pass review — three §0.4 defects closed (§0.4.9) ·
v2.8 2026-09-24, M5 recorded complete; M6 specification — eight gaps closed (§0.5) ·
v2.9 2026-09-24, M6 closure**

**Status as of 2026-09-24 — per milestone, not per document:**

| Milestone | Status | Evidence |
|---|---|---|
| **M0** — pre-flight baseline | **COMPLETE** | `CONTEXT/M0_BASELINE_REPORT.md`, `CONTEXT/M0_CLOSURE_REPORT.md`; commit `73f4007` |
| **M1** — foundations and contracts | **COMPLETE** | `app/intelligence/`, `config/intelligence/risk_rules.yaml`; commit `29776e0`; fingerprint pinned `1d891b0b…` |
| **M2** — relationship model | **COMPLETE** | `app/relationships/` — 7 edge types, 3 queries, no persistence; `tests/unit/test_m2_boundary.py` and `tests/integration/test_m2_relationships.py`; commit `bc0525d`; B1–B10 all asserted |
| **M3** — signal engine and risk band | **COMPLETE** | `app/intelligence/{windows,signals,bands}.py` and the populated band table in `config/intelligence/risk_rules.yaml`; `tests/unit/test_m3_{windows,bands,boundary}.py` and `tests/integration/test_m3_signals.py`; commit `34486eb`; closure §0.2 |
| **M4** — evidence and citations | **COMPLETE** | `app/evidence/`, `app/persistence/models/document_customer_link.py`, `app/persistence/repositories/document_links.py`, migration `c4a1e97d5b02` chained after `8bfd73b6af60` (one head); `tests/unit/test_m4_{linker,signals,boundary}.py` and `tests/integration/test_m4_{evidence,migration}.py`; commit `65eb462`, specification `42f9eeb`, correction `0b017e2`. D-1…D-6 (§0.3), the four gate blockers (§0.3.10) and the three boundary contradictions (§0.3.11) all closed; T1–T5 (§0.3.9) performed. `with_contract_documents` is defined, exported and proved, and **called by nothing in M4** |
| **M5** — analysts and positions | **COMPLETE** | `app/analysts/` — `context.py` (the one factory, and the only module permitted a `Session`), `base.py`, `support_risk.py`, `commercial.py`; `tests/unit/test_m5_{analysts,context,boundary}.py`, `tests/unit/m5_support.py` and `tests/integration/test_m5_contexts.py`; specification `6a8d413` (§0.4, nine decisions D-M5-B1…B9), implementation `d48c970`, and `6158f81`, which closed §0.4.8 criterion 15's first clause (a two-currency context, CUST-042) that `d48c970` had left unasserted — **all sixteen criteria are now asserted**. Measured at `6158f81`: **5163** tests (unit 4166, contract 185, integration 732, e2e 80), `app/` coverage **100%** (5937 statements), ruff 69, mypy 9, secret scan 0, **one** migration head `c4a1e97d5b02` and **no** new migration. Only T-M5-1 and T-M5-2 were needed; T-M5-3/T-M5-4 authorised a re-quote that no count required. `app/intelligence/`, `app/relationships/`, `app/evidence/` and `app/persistence/` byte-identical to `65eb462` |
| **M6** — conflict detection and reconciliation | **COMPLETE** | `app/decisions/` — `policy.py`, `conflicts.py`, `reconciler.py` and the initialiser, exactly; `config/intelligence/{action_catalogue,conflict_policy}.yaml`; `tests/unit/test_m6_{policy,conflicts,reconciler,boundary}.py`, `tests/unit/m6_support.py` and `tests/integration/test_m6_reconciliation.py`; specification `1d1ee59` (§0.5, eleven decisions D-M6-B1…B11), implementation `fd3a7e0`. All twenty-one §0.5.14 criteria asserted; only T-M6-1…T-M6-3 were needed. Measured at `fd3a7e0`: **5533** tests (unit 4518, contract 185, integration 750, e2e 80), 0 skipped, `app/` coverage **100%** (6347 statements), ruff 69, mypy 9, secret scan 0 over 292 files, **one** migration head `c4a1e97d5b02` and **no** new migration. `app/intelligence/`, `app/relationships/`, `app/evidence/`, `app/persistence/` byte-identical to `65eb462`, `app/analysts/` to `d48c970`. Closure notes: Part B M6 |
| **M7–M9** | **PLANNED** | Nothing implemented; no package, table, route or test exists for any of them. §0.4.3 records one **forward** decision M7 must honour: the assessment run owns the production call to `derive_and_persist()`. §0.5.1 records another: M7 **persists** M6's worthiness and ordering and computes neither |

Sections A1–A31 are specification and are **not** a record of what is built. A milestone is
complete only when Part B says so above and a commit is named. Do not begin a milestone until the
previous one is complete and approved.

> Strategy context: `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md`
> Layer 1 state: `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`
>
> **Layer 1 is frozen.** This slice adds new packages, new tables and new routes. It changes no
> canonical schema, no existing migration, no route contract, no D1/D2 semantics and no E1
> status semantics.

---

## 0. What v2 changed, and why

v1 was attacked deliberately. Sixteen defects were found; the material ones are recorded here so
the reasoning is not lost.

| # | Defect in v1 | Severity | Resolution in v2 |
|---|---|---|---|
| 1 | **VS-01 did not prove the AI CEO concept.** Two analysts that never disagree produce a *report*, not a *reconciliation*. Conflict was deferred to VS-04 | **Critical** | Conflict reconciliation is pulled into VS-01 (§A15). The data already contains a genuine one: Sales sees a 90%-probability deal in negotiation; Support sees an active policy escalation with 3 breaching high-priority tickets; DOC-009 records the customer tying the deal to their resolution |
| 2 | **`open_high_priority_count` stated as 4. It is 3.** TKT-073 is high priority but resolved | **Factual error** | Corrected throughout (§A10). Two separate signals: `open_high_priority_count` = 3, `high_priority_total` = 4 |
| 3 | **`as_of` default contradicted the acceptance values.** Default resolves to `max(created_at)` = 2026-08-27, but every asserted value was computed at 2026-09-18. At 2026-08-27 the SLA-breach ranking differs (CUST-009 has 4, CUST-007 has 3) | **Critical** | The acceptance scenario pins `ACCEPTANCE_AS_OF = 2026-09-18` in config. The `max(created_at)` fallback is a convenience for ad-hoc use and is never what the golden file or acceptance run uses |
| 4 | **Assessment uniqueness omitted the Layer 1 snapshot.** Re-running after a new ingestion would hit the unique constraint and silently return stale intelligence | **Critical** | `layer1_fingerprint` is part of the assessment row and of its uniqueness (§A18, §A24) |
| 5 | **Content hash covered the rendered brief.** A whitespace change in a template would invalidate every prior approval | **High** | Approval binds to the **decision payload** (findings, positions, resolution, action, citations), excluding all timestamps and `template_version`. Rendered prose is a view (§A17, §A24) |
| 6 | **Analysts were to receive a SQLAlchemy `Session`.** Scope enforcement would then be advisory — any module holding a session can read any table | **Critical** | Analysts receive **pre-built, typed context objects and never a session** (§A14). Scope becomes a property of construction, not a convention |
| 7 | **Executive-worthiness depended on a derived text link** (`contract_document_present`) | **High** | Worthiness is gated only on `CANONICAL_FK`-backed commercial linkage (active deal or active project). Contract documents are evidence, never a gate (§A15) |
| 8 | **Timezone rule unspecified.** `created_at` is UTC-aware; `as_of` is a date. Naive comparison shifts 14-day window boundaries by one day | **High** | All bucketing uses `created_at.astimezone(UTC).date()`; every window is a closed interval of UTC dates (§A24) |
| 9 | **Derived links had no recomputation trigger.** Documents change; `computed_at` alone leaves links stale | **Medium** | Links are derived inside the assessment run and stamped with `linker_version` + `layer1_fingerprint` (§A18) |
| 10 | **"No outbound import" boundary test was overstated.** The API package already imports HTTP machinery, and the acceptance script needs a client — exactly the situation I1 solved with named exemptions | **Medium** | The test walks the **transitive** import graph of the intelligence/analyst/decision packages and uses the I1 named-exemption mechanism, with each exemption justified and removable (§A22) |
| 11 | Briefs were to be generated for all 50 customers | Low | Assessments for all 50; briefs only for band ≥ `WATCH`. Citation resolution is tested on both |
| 12 | Risk of a speculative generic graph API | Medium | The relationship model exposes exactly the queries of §A9 — **three** after the v2.1 correction below. **No generic `traverse()` in VS-01** |
| 13 | `POST /risk/assessments` re-run semantics undefined | Low | Re-run with an identical fingerprint returns `200` with the existing assessment; a new fingerprint creates a new one (`201`) |
| 14 | Money had no type | Medium | `MoneyValue(amount, currency)` — never summed across currencies. This is the seam VS-02's FX plugs into (§A12) |
| 15 | Acceptance needed a modified corpus for the DOC-005 test, on a stack whose image excludes fixtures | Medium | The leave-one-out test runs in-process against a dedicated test database, not through the deployed stack (§A25) |
| 16 | Multi-currency edge cases untested (one EUR deal exists; some customers hold two currencies) | Low | Named fixtures (§A26) |

---

## 0.1 What v2.1 and v2.2 changed, and why — the M2/M4 boundary, then M2's scope

Found while grilling M2 before implementation, on 2026-09-20, in three passes — the boundary
contradiction first, then a deeper audit that made the boundary testable and fixed the counting
convention, then a structural pass that removed `document_owned_by` — followed by the scope
decision on `deal_owned_by` (row 24), which closes the last open question. Documentation only; no
code was written, and M2 has not started.

| # | Defect or open question in v2 | Severity | Resolution |
|---|---|---|---|
| 17 | **M2 was specified to build two incompatible things.** Its *Change* bullet said `queries.py` implements "the four queries of §A9", and §A9's third query is `documents_for(customer)` → *derived links with basis, matched token and offsets*. Its *Non-goals* line said "Derived document links (M4)". M2 could not both implement all four §A9 queries and exclude derived document links | **High** | `documents_for()` is **not** a relationship query. It is an M4 evidence interface exported from `app/evidence/`, and §A9 now lists **three** public relationship queries. Seven independent signals in v2 already pointed this way: M4 builds the linker, the link table and the first additive migration; M4's named tests *are* the document-link tests; M4's *Before* reads "Documents are unreachable from a customer", which is false if M2 linked them; M2's test list contains no document assertion; M1's `DerivedLink` requires a `linker_version` that does not exist until M4; and the dependency order says M4 may start once **M1** is done, not M2 |
| 18 | **Source-key joins counted five in §A9 and six in the strategy** (§2.2, §5.1), and the two documents were counting different things without saying so | Low | **§A9.1** now defines eight distinct quantities against the frozen code and requires every number to be quoted qualified. Both documents use it. The answer is not "five" or "six" but: **3 resolved canonical FKs**, **6 unresolved source-key joins**, **4 of those modelled by VS-01** and **3 returned by a query**. Rows 6 and 7 were 5 and 3 when this row was written; row 6 fell to 4 in defect 22 |
| 19 | **The M2/M4 boundary was stated but not testable.** Prose alone cannot fail a build, and defect 17 shows prose alone did not even stay self-consistent | Medium | **§A9.2** states the boundary as rules, and M2 gains **invariants B1–B9** — B10 was added later by row 24 — led by *M2 emits zero document→customer edges*, asserted over every customer rather than CUST-007 alone. §A11 gains M4's mirror invariant, so the boundary is falsifiable from both sides |
| 20 | **`employees.organization_id` was counted as a canonical FK** in strategy §2.1's "exactly three", while being a fourth column that is never populated | Low | Strategy §2.1 and §A9.1 now separate **resolved** FKs (3) from **declared-but-unresolvable** ones (1, always NULL — measured 0/24). It is a column, not an edge |
| 21 | **A customer–document association was reachable without any derived link.** `document_owned_by` composed with `customer_owned_by` yields Document → Employee → Customer using only edges M2 may emit. B1 cannot see it, because the composition never forms a single Document–Customer edge | **High** | Named as the *ownership-composition hazard* in §A9.2 with measured evidence — EMP-007 owns Deltaforge's MSA *and* is Meridian's account owner — and forbidden by new invariant **B9**. Shared ownership is not evidence of a relationship |
| 22 | **Defect 21 was closed by a test where it could be closed by construction.** Keeping `document_owned_by` while forbidding its composition left the dangerous first hop in the model, defended only by an invariant someone could later weaken | **High** | **`document_owned_by` is removed from M2's edge inventory** (§A9): it has no VS-01 consumer, and exposing it is unacceptable evidence semantics. M2 now emits no `Document` edge at all, so the composition has no first hop. §A9.1 row 6 falls 5 → 4; rows 1–5 are unchanged, because Layer 1 still holds the relationship. B9 is retained as defence in depth with a negative control, and M4 becomes the sole mechanism for any Document → Customer association |
| 23 | **The document header claimed nothing was implemented**, while M0 and M1 were complete and committed | Medium | Replaced with a per-milestone status table naming the commit for each completed milestone. A9–A31 are restated as specification, not a build record |
| 24 | **`deal_owned_by` was modelled with no VS-01 consumer and left as an open scope question.** An open question in a specification is decided by whoever implements it first — here, most likely by inventing a consumer to satisfy the 100% coverage gate, which would have put a meaningless deal-owner field into a query or an analyst context | **Scope** | **Decided in v2.2: it stays in M2, as substrate.** M2's edge model is the reusable relationship layer, not a projection of VS-01's three queries, and VS-02's per-owner aggregation and VS-03's people map already name deal ownership. **No VS-01 consumer is claimed, and none may be invented.** §A9.1 now states what decides membership of row 6, and why `project_owned_by` and `document_owned_by` still fail it; new invariant **B10** proves the edge directly, so the coverage gate is satisfied by testing the edge rather than by retrofitting a query |

**The trap that made this worth writing down.** `policy_documents()` means M2 legitimately reads
the `documents` table. An implementer who notices that can reason "M2 already touches documents,
so linking them to a customer is in scope" — and every sentence of v2 that should have stopped
them was either contradicted (defect 17) or unenforceable prose (defect 19). §A9.2 names that trap
explicitly and B1/B5 make taking it fail the build.

**Why the boundary is cleaner this way.** Derived links and canonical edges are different kinds of
knowledge — one is a provenance-backed fact, the other an inference carrying a `linker_version`,
a matched token and the evidence a reviewer checks it against. Keeping them behind separate
interfaces, with `app/evidence` reading `app/relationships` and never the reverse, turns §A11's
central rule — *no VS-01 signal is derived from any document link* — into a structural property
of the import graph rather than a rule a reviewer must remember. It also preserves M2's stated
rollback property: M4 adds a package instead of reopening M2's.

---

## 0.2 What M3 closure recorded, 2026-09-21

Implementation commit **`34486eb`**. Measured at closure: suite **4731** (unit 3834, contract
185, integration 632, e2e 80), `app/` coverage **100%**, ruff **69**, mypy **9**, secret scan
**0** over 258 files, Layer 1 fingerprint `1d891b0b…` unchanged, `app/relationships/`
byte-identical to `bc0525d`. Mutation audit over the signal engine, the windows and the band
table: **28 of 29 killed** (§0.2.4).

### 0.2.1 The band decision table is authored, not specified

**This is the entry a reader is most likely to get wrong, so it is stated first.** Neither this
plan nor the strategy ever stated a band threshold. §A5 fixes the four band *names* and says a
versioned decision table in configuration assigns them; §A10 fixes which seven signals may be
*inputs*; §A15 and §A27 fix what the *outcome* must be. The rows themselves did not exist
before M3 and were written by the implementer to reproduce that outcome.

Provenance of every rule and constant M3 introduced. **A** = stated by this plan, **B** = stated
by the strategy, **C** = forced by a pinned acceptance or example value, **D** = authored
implementation choice.

| Rule or constant | Class | Evidence |
|---|---|---|
| Four band names, ordinal, assigned by a versioned table in configuration | **A** | §A5; strategy §4.2 |
| Band inputs limited to S1, S2, S3, S4, S5, S6, S8 | **A** | §A10 "band input: yes" |
| S7, S9, S10, S11–S15 may not be band inputs | **A**, **B** | §A10; strategy §4.3 (money), §4.4 (chronic backlog) |
| `escalation.window_days: 14`, `ticket_threshold: 3` | **A** | §A5, quoted from DOC-003 |
| `sla_resolution_targets: {high: 1, medium: 5}` | **A** | §A5, quoted from DOC-003 |
| `lookback_days: 90` | **B** | strategy §4.4: "constrained to a recency lookback from `as_of` (default 90 days)" |
| Ordering `band ↓, S8 ↓, S4 ↓, source_id ↑` | **A** | §A15 |
| Default band `NONE` when no rule is satisfied | **A**, **C** | §A5; §A23 ticketless → `NONE`; §A25 test 10 |
| `R-CRIT-001` — `S5` **and** `S8 ≥ 2` → `CRITICAL` | **D** | Chosen so CUST-007 is the only `CRITICAL` customer (M3 *Acceptance*, §A25 test 1) **and** so `CRITICAL` requires `S5`, which is what makes §A25 test 11 observable: raising DOC-003's threshold 3 → 6 de-escalates CUST-007 and drops the band |
| `R-ELEV-001` — `S5` → `ELEVATED` | **D** | Strategy §4.4 names the escalation state the *primary discriminator*; the band it maps to is authored. Keeps a de-escalated CUST-007 at `ELEVATED`, which §A15's conflict policy needs (`support_band_at_least: ELEVATED`) |
| `R-ELEV-002` — `S8 ≥ 2` → `ELEVATED` | **D** | Authored. No customer other than CUST-007 reaches it on the demo dataset |
| `R-WATCH-001` — `S8 ≥ 1` → `WATCH` | **D** | Authored. Produces the only two non-CUST-007 banded customers, CUST-025 and CUST-036 |
| `R-WATCH-002` — `S4 ≥ 2` **and** `S6 ≤ 30` → `WATCH` | **D** | Authored, for §A5's "active deterioration": velocity plus recency. The 30-day recency bound is authored |
| `R-WATCH-003` — `S1 ≥ 2` → `WATCH` | **D** | Authored |
| Chronic backlog (S9) = open **and** past its SLA target **and** created before the lookback window | **D** | §A5 defines it as "far past target but isolated in time" with no number. Chosen to reproduce §A10's pinned `S9 = 0` for CUST-007 while making TKT-010 (CUST-009) and TKT-005 (CUST-048) the backlog cases strategy §4.4 names. Introduces no threshold beyond `lookback_days` |
| Window tie → earliest start; category tie → lexicographically smallest | **D** | §A24 requires determinism; the tiebreaks themselves are authored |
| A ticket is open at `as_of` when it carries no resolution date on or before `as_of` | **D** | §A5 measures open tickets created→`as_of`, but never says which column decides. The resolution *date* decides, not `status`, so a ticket resolved after `as_of` is open at `as_of` |

**Nothing in class D is frozen architecture.** Each is a configuration row or a documented
convention that a later milestone may revise, provided §A27's acceptance criteria still hold.

**Measured consequence of the authored table**, recorded so M7 and M6 are not surprised. At
`ACCEPTANCE_AS_OF` the 50 customers band as: `CRITICAL` CUST-007 (1); `ELEVATED` none;
`WATCH` CUST-025 and CUST-036 (2); `NONE` the remaining 47, which include all 15 ticketless
customers. **Three** customers are therefore band ≥ `WATCH` and would receive a brief under
§0's defect-11 decision. CUST-007's band is ≥ `ELEVATED`, so §A15's conflict-policy
precondition is met.

**One measured caveat for M5.** §A16 says CUST-007 triggers all six non-`NO_ACTION` actions at
the pinned `as_of`. Five of the six are decidable from M3's `SignalSet` alone and all five hold
for CUST-007: `S5` is true, `S11 > 0`, `S8 = 3`, an active `negotiation` deal exists, and its
probability is 90. The sixth, `REVIEW_INVOICE_DISPUTE`, requires *an open `billing` ticket* —
ticket-level detail no signal carries, since `S10` reports only the dominant category
(`performance`). The precondition is satisfied on the data (TKT-079 is an open `billing`
ticket), but it must be evaluated from the ticket rows §A14 already puts in the
`SupportRiskAnalyst` context, not from the signal set. **M3's `SignalSet` is not by itself a
sufficient input to the §A16 catalogue**, and no signal was added to make it one.

### 0.2.2 Recorded specification gap — NULL `created_at`

**Affected field:** `support_tickets.created_at` (nullable in Layer 1; not required by D1).

**Current M3 behaviour.** A ticket with a NULL `created_at` cannot be placed on any UTC date, so
it enters no window, no lookback, no recency and no SLA arithmetic. It is excluded from every
signal, and **it produces no data-quality note**. It is therefore absent from M3 intelligence
output altogether.

**Why no note was added.** §A23 defines data-quality observation for the *source-key* states
only — a NULL `customer_id` FK, and a non-NULL key that did not resolve. A missing `created_at`
is an attribute-level defect, not a missing or unresolved relationship. Inventing a fourth note
type would have been reinterpreting §A23 rather than implementing it, so **no new signal, note
type or state was created**.

**Standing of this gap.** No row in `data/demo/` exercises the condition; the behaviour is
reached only through a synthetic row in the isolated test database, where it is tested. It
**does not invalidate M3's acceptance**, every criterion of which is measured over the committed
dataset. It is recorded here as an open decision: **any future production-validity work must
explicitly decide how a NULL `created_at` is represented** — quarantined at ingestion, reported
as an attribute-level observation, or excluded silently as now. Until that decision is taken,
§A23 continues to mean exactly its three source-key states — missing, unresolved, resolved, of
which the first two produce a note — and nothing more.

### 0.2.3 The M3 → M2 consumption boundary, and the import initialiser rule

**M3 consumes M2 through its public relationship queries and resolves nothing itself.** Which
tickets, deals and projects belong to a customer is answered once, by `neighbourhood()`; M3
reads the attributes of the rows that query names.

M3 must not, and does not: import M2's internal modules (`edges_of_type`, `EdgeType`,
`EdgeSpec`, `spec_for`, `EDGE_SPECS` and the edge builders); reconstruct source-key resolution;
recreate relationship traversal; or query Layer 1 to duplicate a relationship M2 already
computes. The executable form is that **`app/intelligence/signals.py` performs no join at all** —
a relationship resolver has to join — and imports neither the `Employee` nor the `Document`
model, and reads no `*_source_id` carrier but `customer_source_id`.

**Direct Layer 1 access is permitted for one purpose only:** §A23's data-quality observations.
That read is the complement of M2's job and M2 cannot express it, because an edge that does not
exist has no basis to carry. It is a single-table read of two frozen columns,
`customer_source_id` and `customer_id`, over the three entities of §A9.1 row 2.

**Import initialiser rule, verified empirically rather than argued.** `app/relationships/`
imports `app.intelligence`, and M3's modules import `app.relationships`. That is loadable only
because **`app/intelligence/__init__.py` does not import or re-export the M3 modules**. Adding
such an import raises `ImportError: cannot import name 'EdgeBasis' from partially initialized
module 'app.intelligence'`. **M3 consumers therefore import the submodule explicitly**, as in
`from app.intelligence.signals import compute_signals`. This is a concrete dependency
constraint on these modules, not a general style rule about package initialisers.

`tests/unit/test_m1_boundary.py` records the same direction statically: `app.relationships` is
allowed to the three M3 module paths by name, and a separate test asserts no M1 foundation
module imports it.

### 0.2.4 The mutation survivor, and why 29/29 was not pursued

28 of 29 mutants were killed. The survivor replaces `.order_by(SupportTicket.source_id)` with
`.order_by(SupportTicket.source_id.desc())` in the ticket read.

**Verified, not assumed.** The full M3 payload — every signal for all 50 customers plus the
data-quality list, serialised with §A24's canonical JSON — was captured clean and mutated
against a freshly ingested database. Both are SHA-256
`7a978e6adae212f5ee0613fdb41b87b6bec650528eab2e34b82f94caaa91542c`: **byte-identical**. The
ticket rows feed only order-independent aggregations — counts, a maximum window with an explicit
tiebreak, and a minimum category with an explicit tiebreak — so read order cannot reach the
output.

The mutant is therefore **semantically equivalent**, and no order-sensitive test was added to
reach 29/29; such a test would assert an implementation detail rather than a behaviour. The
`ORDER BY` is retained as defence in depth, so the read stays reproducible for any future
consumer that does depend on row order. The analogous mutant on the *deal* read is **not**
equivalent and is killed, because `active_deals` is an ordered, observable tuple — which is what
shows the equivalence claim is a property of this particular read rather than a blanket excuse
for unordered ones.


---

## 0.3 M4 decision resolution — pre-implementation, 2026-09-21

The M4 pre-implementation audit at `0c11dcc` found that M4 could **not** be implemented
unambiguously. Six architectural questions were unresolvable from the plan as written; two of
them were not underspecification but error, established against the live 233-row database.

**D-1 through D-6 have architectural resolutions**, recorded below. That phrasing is deliberate
and is narrower than "every M4 and M5 question is answered", which is **not** true:

- **D-6 establishes M4's ownership of the S14 composition function** and its deterministic
  contract (§0.3.6 A).
- **The production caller remains an M5 responsibility** (§0.3.6 B): M5 invokes the function
  when it constructs the executive context of §A14.
- **The M5 invocation decision is intentionally deferred** to M5's specification.
- **This does not block implementation of the M4 function itself**, which is complete when the
  function exists, is pure, and reproduces the measured expectation. The deferred M5
  responsibility **must not be turned into an M4 requirement**.

§0.3.7 separately lists the lower-level details left open on purpose, and §0.3.9 specifies —
**without authorising** — the test evolution M4 will require.

This section is **documentation only**: no package, table, migration, test or configuration key
was created by it, and `app/`, `tests/`, `config/`, `migrations/`, `data/` and `README.md` are
byte-identical to `34486eb`.

Every decision below is classified with the same four-way vocabulary §0.2.1 introduced, so a
reader can tell what the architecture forced from what this section chose:

| Classification | Meaning |
|---|---|
| **FROZEN** | Already fixed by committed M1/M2/M3 code or by a section of this plan that predates the audit |
| **OBSERVED** | Measured from the committed dataset. A fact about the data, **never** an architectural rule |
| **DERIVED** | Follows necessarily from FROZEN material; a different choice would contradict something already built |
| **AUTHORED** | A genuine choice this section makes. Not forced, not frozen architecture, and reversible by a later decision that says so |

**Lower-level details are deliberately left open.** §0.3.7 lists them. They depend on the grain
and evidence model settled here and must not be decided by an implementer in passing.

---

### 0.3.1 D-1 — `TOPIC` is removed from VS-01

**The requirement as it stood.** §A11's table read:

> | `TOPIC` | Document topic overlaps the dominant ticket category | **No** | DOC-010 (supporting only) |

and §A9's edge table carried a fourth row, `document_relates_to_topic` · `DERIVED_TOPIC_MATCH`,
produced by **M4**. M4's *Change* list named `TOPIC` as one of three rules to implement.

**Evidence.**

1. **No input field exists.** `documents` holds exactly `title`, `document_type`, `body_text`,
   `source_uri`, `owner_source_id`, `created_at`, `updated_at`
   (`BUSINESS_FIELDS['documents']`, `app/persistence/models/document.py`, migration
   `8bfd73b6af60`). There is no topic column, and Layer 1 is frozen (§A31).
2. **The two vocabularies are disjoint.** OBSERVED: `document_type` ∈ {`policy`, `report`,
   `contract`, `meeting_notes`, `proposal`, `runbook`}; ticket `category` ∈ {`integration`,
   `billing`, `onboarding`, `auth`, `performance`, `data`}. No value of either appears in the
   other. DOC-010's `document_type` is `report`.
3. **The stated expectation is not reproducible.** OBSERVED: under literal ticket-category token
   overlap across title and body, DOC-010 matches `data` — never `performance`, CUST-007's
   dominant category. The only documents containing `performance` are DOC-005 and DOC-009, both
   of which are already `ID_TOKEN` and `EXACT_NAME` links. No rule over any existing column
   yields the DOC-010 → CUST-007 pairing §A11 expected.
4. **The contract cannot represent it.** `DerivedLink` (FROZEN, `app/intelligence/contract.py`)
   requires a `target: EntityRef` whose `entity_type` is a canonical entity — there is no topic
   entity — and requires a **non-empty** `matched_token` and a **non-empty** `evidence` tuple.
   A topical overlap asserts no token and no span naming the customer.
5. **It contradicts the project's own grounding guarantee.** Strategy §7.4: *every asserted fact
   must carry a machine-resolvable reference to a record id plus field name, or a document id
   plus character span.* A `TOPIC` link has neither.
6. **The plan contradicted itself on what a `TOPIC` link even is.** §A9 named the edge
   `document_relates_to_topic` (Document → **Topic**); §A11's table placed it in a **customer**
   column; M4's *Tests* said DOC-010 "is reachable only as a `TOPIC` link and **never as a
   customer association**".
7. **Nothing in VS-01 consumes it.** §A27's ten acceptance criteria never name DOC-010 or a
   topic link; criterion 3 cites DOC-003, DOC-006 and DOC-009. §A25's fourteen named tests
   contain no topic test. §A10's S14 expects DOC-006 only. Before this section was written,
   DOC-010 appeared in exactly two places in the whole plan — §A11's `TOPIC` row and M4's
   *Tests* — and both are the wording being removed here.
8. **No planned slice names it either.** `topic` appears in the strategy only in the two rows
   describing this same mechanism (§5.2, §7.2) and nowhere in VS-02–VS-08's requirements. It
   appears nowhere in `AI_CEO_PROJECT_CONTEXT.md`.
9. **§A9.1 already supplies the membership test**, and it is the test `project_owned_by` and
   `document_owned_by` were excluded under: *an edge is modelled when it is a Layer 1 fact that
   a **named** slice needs, and left out when it is speculative or unsafe.* A topic overlap is
   not a Layer 1 fact at all, and no named slice needs it.

**Decision.**

> **`TOPIC` is not implemented in VS-01.** M4 derives Document → Customer links by `ID_TOKEN`
> and `EXACT_NAME` only. Specifically:
>
> - **No topic entity, topic column, topic vocabulary or topic configuration is introduced.**
>   Layer 1 gains nothing; `config/intelligence/` gains no topic mapping.
> - **No embedding, similarity, keyword-expansion or other semantic inference replaces it.**
>   §A13 and §A31 are unchanged and this decision does not reopen them.
> - **DOC-010 is not forced into a customer association by any means.** It remains what the
>   data says it is: a postmortem that names no customer. OBSERVED, and recorded at
>   `M0_BASELINE_REPORT.md:560` — it contains neither `CUST-007` nor the customer name.
> - **M4 is deterministic textual evidence linking only.** Every link M4 emits quotes the text
>   that asserts the relationship.
> - **`LinkBasis.TOPIC`, `LinkConfidence.SUPPORTING` and `EdgeBasis.DERIVED_TOPIC_MATCH` stay
>   in M1's contract as reserved vocabulary and are not deleted.** M1 is frozen at `29776e0`
>   and this decision does not touch it. They are reserved exactly as
>   `EvidenceKind.MODEL_NARRATIVE` is reserved: declared so the vocabulary is complete, and not
>   constructible in VS-01. A later slice that acquires a real topic model may use them, and
>   must state its input field before it does.

**Classification.** The removal is **DERIVED** — evidence 1, 4 and 5 make the mechanism
impossible to build, not merely unattractive, so no other resolution exists that leaves Layer 1
and M1 frozen. Evidence 2 and 3 are **OBSERVED** and are the reason the defect was invisible
until the data was measured. Treating `LinkBasis.TOPIC` as reserved rather than deleting it is
**AUTHORED**, chosen because deleting it would modify frozen M1 code for no behavioural gain.

**Consequences.** §A9's edge table, §A11's rule table and narrative, §A29's limitations, and
M4's *Change*, *Tests* and *Non-goals* are all amended below. M4's linker implements two
mechanisms. **Every link M4 produces is therefore `LinkConfidence.HIGH`**, which removes the
need for a confidence predicate in §0.3.6. §A9.2's prohibition on M2 deriving links by
`ID_TOKEN`, `EXACT_NAME` or `TOPIC` is **left exactly as written**: it forbids M2 from doing
these things whether or not M4 does them, and M2 is frozen at `bc0525d`.

**Remaining uncertainty.** None for VS-01. A future slice that wants topical evidence must
introduce a topic field or classifier and state its input, its vocabulary and its grounding
reference first; this section does not pre-authorise one.

---

### 0.3.2 D-2 — the `EXACT_NAME` expectation is corrected to DOC-005/006/009

**The requirement as it stood.** §A11's table read `EXACT_NAME` → **DOC-006, DOC-009**, and M4's
*Tests* read "exact-name finds DOC-006/009".

**Evidence.**

1. **OBSERVED, live database, 233 rows, `source_system='csv_demo'`:** DOC-005's body contains
   `Meridian Textiles` at offset 174 — *"Escalation: Meridian Textiles (CUST-007) raised 5
   tickets between 2026-08-18 and 2026-08-27…"* — at token boundaries, case-insensitively. The
   correct set is **DOC-005, DOC-006, DOC-009**, identical to `ID_TOKEN`'s.
2. **This plan already contradicted itself.** `M0_BASELINE_REPORT.md` §12.2 tabulates DOC-005
   as ✅ under *both* the `CUST-007` token and the exact-name column. `M0_CLOSURE_REPORT.md`
   finding F7 states plainly that "DOC-005 matches CUST-007 by both `ID_TOKEN` and
   `EXACT_NAME`". Both predate this plan's table and both were measured.
3. **Precedence cannot rescue the old value.** If a pair carried only its strongest basis, all
   three documents carry `ID_TOKEN`, so `EXACT_NAME` would return **nothing** for CUST-007 —
   wrong by two rather than by one. The old row is wrong under either grain (§0.3.3).

**Decision.**

> `EXACT_NAME` for CUST-007 is **DOC-005, DOC-006, DOC-009**. §A11's table and M4's *Tests* are
> corrected below. The old DOC-006/009 value is **not** preserved anywhere, in any wording, and
> an implementation that reproduces it is wrong.
>
> M4's acceptance — "links reproduce the measured expectation" — binds to this corrected set.
> **An implementer who measures a different set must report it, not adjust the expectation.**

**Classification.** **OBSERVED**, promoted to a corrected expectation. The *rule* ("full
customer name, case-insensitive, at token boundaries") is FROZEN and unchanged; only the
expected result of applying it was wrong.

**Consequences.** §A11's table and M4's *Tests* are amended. §A27's criteria are unaffected:
criterion 3 cites DOC-003, DOC-006 and DOC-009 for their *content*, not for their basis, and
DOC-005's standing as a link was never what §A25 test 4 protects — that test removes DOC-005
and asserts every signal is unchanged, which stays true because no VS-01 signal is
document-derived (§A11).

**Remaining uncertainty.** The corpus-wide expectation beyond CUST-007 is recorded in §0.3.8 as
OBSERVED. It is measurement, not architecture, and M4's tests should assert it as such.

---

### 0.3.3 D-3 — link grain is one row per (document, customer, basis)

**The requirement as it stood.** Nothing in §A11 or §A18 said whether a document–customer pair
matching on two mechanisms yields one row or two. OBSERVED: this is not hypothetical — after
§0.3.2, **all three** of CUST-007's documents match on both `ID_TOKEN` and `EXACT_NAME`.

**The two candidates, and what each costs.**

| | **A — one row per pair, strongest basis** | **B — one row per (pair, basis)** |
|---|---|---|
| `DerivedLink` | fits: one `basis`, one `matched_token` | fits: one link per basis |
| **Matched token** | **loses one.** `ID_TOKEN`'s token is `CUST-007`; `EXACT_NAME`'s is `Meridian Textiles`. A single row can record only one | both retained, each with its own span |
| `documents_for()` | returns ≤1 link per document | returns one link per basis |
| Unique constraint | `(document, customer, …)` | `(document, customer, basis, …)` |
| Citations | one span per pair | one span per basis — two independent places a reviewer can check the same association |
| Idempotency | unaffected either way | unaffected either way |
| **Requires a precedence rule** | **yes** — which basis wins | **no** — the mechanisms do not compete |
| §A11's "exact-name finds …" test | **cannot be written**: under `ID_TOKEN` precedence, exact-name finds nothing | writes naturally |
| S14 | needs a basis-aware predicate | needs none after §0.3.1 |

**Evidence.** The architecture already chose. M4's *Tests* enumerate the two mechanisms'
results **separately** — "id-token matching finds …; exact-name finds …". That sentence is only
satisfiable if each mechanism has its own independently observable result set, which is grain B.
Under grain A the second clause is unwritable. `DerivedLink`'s FROZEN shape — a single `basis`,
a single `confidence` **fixed by that basis**, and a single `matched_token` — is a
one-link-per-basis record, and §A18's columns (`basis`, `matched_token`, `match_start`,
`match_end`, all singular) are its row-wise image. §A11's requirement that every association
carry "a basis, a matched token and a citation into the text, or it does not exist" is satisfied
per row under B and forces the loss of a real matched token under A.

**Decision.**

> **Grain B.** One persisted row, and one `DerivedLink`, per `(document, customer, basis)`.
> A pair matching on both mechanisms produces **two** links, each carrying its own
> `matched_token`, its own span and its own evidence.
>
> **There is no precedence between mechanisms, and none may be introduced.** They do not
> compete: both results are recorded, and a consumer that needs a single answer per pair states
> its own rule at the point of consumption rather than discarding evidence at derivation time.
> `ID_TOKEN` is not "stronger than" `EXACT_NAME`; after §0.3.1 both are
> `LinkConfidence.HIGH` and both may derive signals in a later slice.

**Classification.** **DERIVED.** Grain A contradicts a test this plan already specifies and
discards a `matched_token` the contract requires each link to carry.

**Consequences.** §A11 gains an explicit grain statement; §A18 gains the unique constraint in
§0.3.4; `documents_for()` returns a tuple that may contain more than one link per document.
A consumer asking "is this document linked to this customer?" asks whether **any** link exists
for the pair — which is what S14 does in §0.3.6.

**Remaining uncertainty.** The **ordering** of the returned tuple is deliberately not decided
here; it is a determinism detail listed in §0.3.7. Grain fixes *what* is returned, not *in what
order*.

---

### 0.3.4 D-4 — uniqueness key and re-derivation semantics

**The requirement as it stood.** §A18 declared a unique constraint on `risk_assessments` and on
`risk_briefs` and **none** on `document_customer_links`, while §A23 stated "concurrent identical
assessments → unique constraint makes the second a read" and §A27.8 required "re-run inserts
nothing". Nothing said what happens when the snapshot or the linker changes.

**Evidence.**

1. §A24 (FROZEN): "An assessment is a pure function of (`as_of`, `source_system`,
   `layer1_fingerprint`, `rules_version`, `policy_version`, `linker_version`)." Of these, the
   inputs that can change a **link** are `layer1_fingerprint` (the document and customer text)
   and `linker_version` (the matching rules). `as_of`, `rules_version` and `policy_version`
   cannot: no link depends on the evaluation date or on the band or conflict policy.
2. §A18's sibling table shows the pattern: `risk_assessments` is unique over
   `(customer_id, as_of, source_system, layer1_fingerprint, rules_version)` — **the identity
   inputs that affect the output are in the key**, so a changed snapshot yields a *new* row
   rather than overwriting the old conclusion. §A27.8 states the same behaviour in words:
   "changing the Layer 1 snapshot produces a new assessment."
3. §0 defect 9 (FROZEN): links are stamped with `linker_version` + `layer1_fingerprint`
   precisely so that a link derived under a superseded snapshot or linker is identifiable
   rather than silently stale.
4. Grain B (§0.3.3) puts `basis` in the key.
5. `source_system` needs no column and no place in the key: both foreign keys point at rows
   that already carry a `source_system`, and a link between two source systems is forbidden, so
   the FK pair determines it.

**Decision.**

> **Unique key:** `(document_id, customer_id, basis, linker_version, layer1_fingerprint)`.
>
> - **Repeated derivation with identical inputs is a no-op.** The second insert is refused by
>   the constraint and read instead, exactly as §A23 specifies for assessments. §A27.8's "re-run
>   inserts nothing" is satisfied by the constraint, not by an application-level check.
> - **A changed `layer1_fingerprint` appends.** New rows are written for the new snapshot; rows
>   from the previous snapshot are **retained**, so a past assessment's links remain attributable
>   to the snapshot they were derived from. This is `risk_assessments`' behaviour, applied to
>   links.
> - **A changed `linker_version` appends**, for the same reason and on the same key.
> - **Nothing is ever updated in place, and nothing is deleted** by a re-derivation. The table
>   grows only when an identity input changes.
> - **No `computed_at`, no `superseded_by`, no validity interval and no history table is
>   introduced.** §0 defect 9 was closed by the two stamps, and the stamps are sufficient: the
>   rows a given assessment used are exactly the rows carrying its fingerprint and linker
>   version. This decision adds no versioning machinery beyond the key.

**Classification.** **DERIVED** — evidence 1–3 fix which columns are identity, and §A18's
sibling constraint fixes how identity is expressed. The exclusion of `as_of`, `rules_version`
and `policy_version` from the key is DERIVED from evidence 1: a link does not depend on them,
so including them would mint duplicate rows for identical content. The choice **not** to add
history machinery is **AUTHORED**, and is the minimal reading of §0 defect 9.

**Consequences.** §A18's `document_customer_links` row gains the constraint. M4 must test the
no-op re-run and the append-on-fingerprint-change. Downgrade still drops only the new table.

**Remaining uncertainty.** Whether a `source_system` column is nonetheless carried for
readability is a schema detail, not an identity question, and is listed in §0.3.7. It cannot
change the key.

---

### 0.3.5 D-5 — `linker_version`

**The requirement as it stood.** §A7 said `linker_version` comes "from configuration"; §A18 and
§A24 required it on every link and in the assessment identity; `DerivedLink` requires it to be a
**non-empty string**. `config/intelligence/risk_rules.yaml` contains no such key, and
`app/intelligence/config.py` validates a closed set of keys that does not include one.

**Evidence.**

1. `DerivedLink.linker_version` is validated by `_require_text` (FROZEN): it must be a non-empty
   **string**. `rules_version` is validated as a **positive int** by `config.py` — the two are
   not interchangeable, and the string requirement is the frozen side.
2. §A7 lists `linker_version` alongside `lookback_days`, `rules_version` and `policy_version` as
   configuration, not as a constant.
3. `risk_rules.yaml` already establishes the file's versioning convention in prose next to
   `rules_version`: *"Bumped whenever a rule that can change a band or an action changes. It is
   part of an assessment's identity, so a rule change yields a new assessment rather than
   silently overwriting the old conclusion."*
4. `risk_rules.yaml` is the Layer 2 policy file and already holds every other VS-01 version and
   pinned value. No second configuration file exists or is planned.

**Decision.**

> - **Key name:** `linker_version`.
> - **Location:** top level of `config/intelligence/risk_rules.yaml`, beside `rules_version`,
>   and admitted by `app/intelligence/config.py`'s key whitelist. **No new configuration file
>   and no new versioning framework is introduced.**
> - **Type:** YAML **string**, validated as non-empty, because `DerivedLink` requires a string.
>   It is deliberately *not* modelled on `rules_version`'s integer type; the frozen contract
>   wins over the file's local convention.
> - **Initial value:** `"1"`.
> - **Bump rule:** bumped whenever a change to the linker can change which links are derived,
>   which token is matched, or where a span falls — the same test `rules_version` applies to
>   bands and actions. A refactor that provably cannot change any emitted link does **not** bump
>   it.
> - **Effect on existing persisted links:** governed by §0.3.4 — a bump appends. Rows carrying
>   the previous `linker_version` are retained and remain attributable to it. No migration, no
>   backfill and no rewrite accompanies a bump.

**Classification.** Key name, location, type and bump rule are **DERIVED** (evidence 1–4).
The literal initial value `"1"` is **AUTHORED**: the frozen contract fixes the *type* but no
repository evidence fixes the *format*, and `"1"` mirrors `rules_version: 1` as closely as a
string can. It is recorded here rather than left to an implementer precisely because it is a
choice, and a later decision may restate it — but it may not be invented differently at
implementation time.

**Consequences.** M4's *Change* list gains the configuration key and its validation. §A7 is
unchanged and now resolvable.

**Remaining uncertainty.** None.

---

### 0.3.6 D-6 — S14: M4 owns the composition function, M5 owns invoking it

**The requirement as it stood.** §A10 said M3 "states `contract_document_ids = ()` for every
customer and **M4 populates it**", while M4's *Change*, *Tests*, *Acceptance* and *Non-goals*
never mentioned S14, named no owner, and stated no rule for which links are contract documents.
"M4 populates it" conflated two different responsibilities, which this section separates.

**Evidence.**

1. `SignalSet` is an **M1** type (`app/intelligence/contract.py`), frozen at `29776e0`. It is
   **not** an M3 type. M3's `signals.py` merely constructs one.
2. `SignalSet` is a frozen dataclass, so a populated copy is produced by replacement, not by
   mutation. Producing that copy requires the **type** only.
3. M3's `signals.py` hard-codes `contract_document_ids=()`, and
   `tests/unit/test_m3_boundary.py` pins that literal by scanning the source text. M3 is frozen
   at `34486eb`. **Any resolution that edits `signals.py` is therefore excluded**, and this
   section does not edit it.
4. The selection rule is determined by three things together: the signal's own name
   (`contract_documents`), its OBSERVED expectation for CUST-007 (DOC-006), and the fact that
   DOC-006 is the only `document_type = 'contract'` document linked to CUST-007. §A27.3 and
   §A14 both consume it as *contract terms*.
5. **Filtering documents by `document_type` is an established, frozen pattern**, not an
   invention: M2 exports `POLICY_DOCUMENT_TYPE = "policy"` and `policy_documents()` filters on
   it (`app/relationships/queries.py:64`, `:248`).
6. After §0.3.1 every M4 link is `LinkConfidence.HIGH`, so no confidence predicate is needed.
7. §A14 places contract documents in `CommercialContext`, which **M5** builds — "plain
   dataclasses built by a factory". §A6's workflow orders evidence (step 5) after signals
   (step 3) and before the analyst contexts (step 6), so the assembled executive context is the
   first place a populated `SignalSet` is actually needed.
8. M4's own deliverables are the linker, `documents_for()`, citations, the link model, its
   repository and the first additive migration. **None of them reads a `SignalSet`.** S14 is not
   an input to, or an output of, deriving or persisting a link.
9. **No frozen type expresses a link *and* its document type.** `DerivedLink` (M1, frozen)
   carries both endpoints, the basis, the matched token, the evidence and the provenance stamps
   but **no `document_type`**; `app/persistence/models/` contains no `DocumentCustomerLink`
   module, since that model is itself an unbuilt M4 deliverable. The selection rule needs
   `document_type`, so the minimal pairing below is M4-owned.

**Decision — two responsibilities, held by two milestones.**

> **A. M4 owns the composition function and its deterministic contract.**
>
> **The representation it consumes.** The frozen M1 `DerivedLink` already expresses a link's
> document (`source`), its customer (`target`), its basis, confidence, matched token, evidence
> and provenance stamps. It carries **no** `document_type`, and the selection rule needs one. No
> `DocumentCustomerLink` type exists in the repository — `app/persistence/models/` holds no such
> module — so M4 defines a new type of its own:
>
> ```
> LinkedDocument                   # new, M4-owned
>     link           DerivedLink   # a frozen M1 value, held by composition
>     document_type  str | None    # Layer 1's documents.document_type, which is nullable
> ```
>
> **`LinkedDocument` is a new M4-owned wrapper that *contains* a frozen `DerivedLink` alongside
> the Layer 1 `document_type`. It does not extend, subclass, widen or modify `DerivedLink`, and
> `document_type` is never added to `DerivedLink`.** `app/intelligence/contract.py` is frozen at
> `29776e0` and M4 does not touch it. Composition, not extension: that is the whole point of
> introducing a second type rather than editing the first.
>
> `link.source` is the document and `link.target` is the customer: that direction is frozen by
> M1's own contract test, whose fixture builds `source=EntityRef("documents", …)` and
> `target=EntityRef("customers", …)`. `LinkedDocument` carries these two members and no others.
> It is M4-owned and specified here, not implemented here.
>
> **The function.**
>
> ```
> with_contract_documents(
>     signals: SignalSet,
>     links:   tuple[LinkedDocument, ...],
> ) -> SignalSet
> ```
>
> - **Input `signals`** is M1's frozen `SignalSet`, imported from `app.intelligence.contract`.
> - **Input `links`** is a tuple of `LinkedDocument` — the one named representation above. The
>   tuple shape matches every other collection in M1's contract (`tuple[Evidence, ...]`,
>   `tuple[DealSignal, ...]`, `tuple[str, ...]`).
> - **Returns a NEW `SignalSet`.** `SignalSet` is a frozen dataclass; the result is a replacement
>   copy, never a mutation.
> - **Every other field is carried through unchanged.** Only `contract_document_ids` differs
>   between input and output. S1–S13 and S15 are untouched.
> - **Zero contract links → `()`**, not an error.
> - **Contract links → distinct document ids**, as described under *Projection* below.
> - **Deterministic**: same `signals` and same `links` in, same `SignalSet` out.
> - **No database, no session, no query, no clock, no randomness.**
> - **No import from M3** — not `app.intelligence.signals`, `windows` or `bands`.
>
> **Selection rule.** A customer's contract documents are the documents linked to that customer
> by any M4 mechanism whose `document_type` **is exactly equal to** the string `"contract"`.
>
> - **The constant is named `CONTRACT_DOCUMENT_TYPE` and its value is exactly `"contract"`.**
>   It is declared in `app/evidence/` the way M2 declares `POLICY_DOCUMENT_TYPE = "policy"`
>   (`app/relationships/queries.py:64`). The identifier is fixed here so no implementer chooses
>   one.
> - **The comparison is exact string equality and case-sensitive.** `document_type ==
>   CONTRACT_DOCUMENT_TYPE`, and nothing else. **No normalization, no case folding, no
>   stripping, no substring or prefix matching, no `in` test, no fallback, no synonym list, no
>   regular expression.** `"Contract"`, `"CONTRACT"`, `" contract"` and `"contract_amendment"`
>   are **not** contract documents. This matches the source-system discipline the rest of the
>   project applies to canonical string values, and it matches M2's frozen
>   `Document.document_type == POLICY_DOCUMENT_TYPE` predicate.
> - **`document_type is None` is not a contract document and contributes nothing to S14.** This
>   is stated as a rule rather than left to ordinary Python comparison semantics: `None ==
>   "contract"` is false, but the behaviour must be a specified property, not an accident of the
>   expression an implementer happens to write. NULL means *unknown*, and an unknown document
>   type is never treated as a contract.
>
> **Projection — S14 is document grain, the link table is evidence grain.** Under §0.3.3 one
> customer–document pair legitimately has **more than one** evidence link: DOC-006 reaches
> CUST-007 on both `ID_TOKEN` and `EXACT_NAME`, and **both rows are correct evidence and both
> are kept**. `contract_document_ids` is a tuple of document ids, not of links, so the function
> **projects evidence grain onto document grain**:
>
> 1. filter `links` to those whose `document_type` is exactly `CONTRACT_DOCUMENT_TYPE`;
> 2. collect each one's document id — `link.source.source_id`;
> 3. **collapse multiple evidence links for the same document to a single document id.
>    Deduplication is by `document_id` and by nothing else;**
> 4. **order the surviving ids lexicographically ascending by `document_id`.**
>
> This is why CUST-007's **two** contract links yield `("DOC-006",)` and not
> `("DOC-006", "DOC-006")`.
>
> **The projection reads exactly one field of each link.** A `LinkedDocument` contributes only
> its `link.source.source_id`, after its `document_type` has decided whether it takes part at
> all. **The customer identity, `link.target`, `basis`, `confidence`, `matched_token`,
> `evidence`, `source_system`, `layer1_fingerprint` and `linker_version` are not consulted by
> S14 at any point.** They remain on the evidence rows, where a reviewer reads them; S14 is a
> list of document ids and nothing more. Narrowing the read surface to one field is what makes
> the absence of evidence priority structural rather than merely promised.
>
> **What the projection must not do.** It **does not choose one evidence basis over another**:
> there is no evidence priority, no `EXACT_NAME`-over-`ID_TOKEN` preference, and no rule that
> reads `basis` at all. It **deletes nothing**: the underlying evidence links remain intact in
> `document_customer_links` and in `documents_for()`'s result, both of which stay at evidence
> grain. It introduces no history, no supersession, no validity interval and no new relationship
> semantics. S14 is a **document-level projection only** — a view of the evidence layer, never a
> replacement for it.
>
> **Ordering — frozen for S14, still deferred for `documents_for()`.** Determinism and ordering
> remain **independent properties**: a function can be deterministic while its order is
> unspecified, which is exactly the state two correct implementations could exploit to return
> `("DOC-002", "DOC-006")` and `("DOC-006", "DOC-002")` from the same input. Because
> `contract_document_ids` is a **contract field that M5 consumes**, its order is frozen here:
> **lexicographic ascending by `document_id`, applied after deduplication** (step 4 above).
> It is a sort key, **not** a priority: it ranks document ids, never evidence, and it reads no
> link metadata. It also matches the ordering discipline already frozen elsewhere in the
> project — §A5.1's fingerprint and M2's queries both order by `source_id`.
>
> `documents_for()`'s ordering remains **deferred** at §0.3.7 #9. That is a different function
> returning a different grain, and this decision does not settle it.
>
> M4 **proves** the function: composing an M3 signal set with M4's links in a test yields exactly
> `("DOC-006",)` for CUST-007.
>
> **B. M5 owns invoking it in production, when it constructs the executive context.**
>
> - §A14's `CommercialContext` is where a populated S14 is consumed, and M5 builds that context.
>   The production call therefore belongs to **M5**, not to M4 and not to M7.
> - **The invocation design is intentionally deferred to M5's specification** — where in M5's
>   context factory the call sits, what it is handed, and how the populated `SignalSet` flows
>   into `CommercialContext`. Deferring it is safe precisely because A is a pure function with a
>   fixed contract: M5 can wire it without reopening M4.
>
> **What M4 must not do.**
>
> - **M4 must not invoke the function anywhere in its own linking or persistence pipeline.**
>   The linker, `documents_for()`, the citation builder, the link repository and the migration
>   neither call it nor depend on it. M4's pipeline derives and persists links; composing a
>   `SignalSet` is a separate, caller-driven operation.
> - M4 assembles and persists **no** assessment. `risk_assessments` and its `signals` JSONB
>   remain M7's.
> - **M4 does not import M3.** The M4 → M3 dependency question does not arise and is not
>   authorised; M4's permitted import surface stays M1 + M2, exactly as the DAG in M4's section
>   states. A later milestone that needs M3's signal engine imports it itself.
> - **M3 is not modified.** `app/intelligence/signals.py` continues to state
>   `contract_document_ids=()`, its boundary test continues to pin that literal, and M3's
>   closure at `34486eb` stands. **The frozen M3 `SignalSet` contract is unchanged.**
> - **No signal becomes document-derived.** S14 remains evidence only (§A10, §A11). S1–S13 and
>   S15 are untouched by M4, and §A25 test 4 continues to assert byte-equality of every signal
>   value with DOC-005 removed — which holds, because DOC-005 is a `report` and S14 selects
>   `contract` documents.

**Classification.** Stated per element, because this decision mixes all three kinds.

| Element | Class | Why |
|---|---|---|
| M4 owns the composition function; it imports nothing from M3 | **DERIVED** | Evidence 1–3: `SignalSet` is M1's type, and editing M3 is excluded by the freeze |
| Selection rule — linked ∧ `document_type = 'contract'` | **DERIVED** | Evidence 4–6, following M2's frozen `POLICY_DOCUMENT_TYPE` filter pattern |
| Keeping the call out of M4's own pipeline | **DERIVED** | Evidence 8: nothing in M4's pipeline holds a `SignalSet` to compose |
| Projection to document grain; **deduplication by `document_id`** | **DERIVED** | `contract_document_ids` is `tuple[str, ...]` on the frozen `SignalSet`, and §0.3.3's grain makes two evidence links for one document the measured norm. The acceptance value `("DOC-006",)` is unreachable any other way without reading `basis`, which the rule forbids |
| **Assigning the production call to M5** | **DIRECTED, then corroborated** | This was an explicit instruction during the 2026-09-21 review, not a conclusion this plan reached on its own. Evidence 7 corroborates it — §A14 puts the consumer in `CommercialContext`, which M5 builds — but the directive came first and is the reason it is recorded as settled rather than deferred |
| `LinkedDocument` as the name and shape of the links parameter | **AUTHORED** | Nothing frozen fixes it. It is the minimal wrapper that closes the `document_type` gap of evidence 9 and carries no other member |
| `LinkedDocument` **wraps** `DerivedLink` by composition and never extends or modifies it | **DIRECTED** (2026-09-21 review) | Prevents the requirement being read as "add `document_type` to `DerivedLink`", which would break the M1 freeze |
| `with_contract_documents` as the function name | **AUTHORED** | Nothing frozen fixes it; it is named here so an implementer does not invent one |
| **`CONTRACT_DOCUMENT_TYPE = "contract"`** as the constant's identifier and value | **DIRECTED** (2026-09-21 review) | The value follows M2's frozen `POLICY_DOCUMENT_TYPE` pattern; fixing the *identifier* removes an implementation choice without touching architecture |
| **Exact, case-sensitive equality to `"contract"`; `None` and every other value contribute nothing** | **DIRECTED** (2026-09-21 review) | Matches M2's frozen `document_type ==` predicate and the project's source-system string discipline. Stated as a rule so NULL handling is a specified property, not a by-product of Python comparison |
| **`contract_document_ids` ordered lexicographically ascending by `document_id`** after deduplication | **DIRECTED** (2026-09-21 review) | Determinism alone permits two correct implementations to disagree on order. S14 is a contract field M5 consumes, so its order is frozen. A sort key over ids, never a priority over evidence |
| S14 reads only `document_type` and `link.source.source_id` | **DIRECTED** (2026-09-21 review) | Extends the existing `basis` prohibition to every other evidence attribute, making the narrow semantics structural |
| Zero contract links yield `()` rather than raising | **AUTHORED** | A genuine micro-decision. No frozen material forces either behaviour; the empty tuple matches `SignalSet`'s other empty-collection defaults |
| The function is **total and pure** | **AUTHORED** | Also a micro-decision, and the property that makes M5's deferred invocation design safe |

**Consequences.** §A10's S14 paragraph and M4's *Change*, *Tests*, *Acceptance* and *Non-goals*
are amended below; §A14 gains a pointer naming M5 as the caller. `app/evidence/` gains
`with_contract_documents`, the `LinkedDocument` representation and the `contract`
document-type constant — and **nothing in M4 calls any of them**.

**Remaining uncertainty — recorded, not hidden.** M5's **invocation design** is deferred to M5's
specification (B above). It is a deferred M5 responsibility and **must not be turned into an M4
requirement**: M4 is complete when the function exists, is pure, and is proved against the
measured expectation.

---

### 0.3.7 Deliberately deferred — do not decide these while implementing

These depend on the grain and evidence model settled above, or on decisions a later milestone
owns. An implementer who needs one of them must have it decided **in this plan** first; none of
them may be settled in passing.

**Rows 1–8 were closed on 2026-09-21 by §0.3.10** and are struck through below so the record of
what was open, and when, survives. **Rows 9, 10 and 11 remain genuinely open.**

| # | Open detail | Status |
|---|---|---|
| ~~1~~ | `ID_TOKEN` tokenization predicate, case sensitivity, and text normalization | **CLOSED** — §0.3.10.4 |
| ~~2~~ | NULL `title` semantics (NULL `body_text` is already specified by §A23) | **CLOSED** — §0.3.10.4, citable text |
| ~~3~~ | Which occurrence yields the span when a token or name appears more than once | **CLOSED** — §0.3.10.4, first occurrence |
| ~~4~~ | Which `EvidenceKind` a link's evidence carries | **CLOSED** — §0.3.10.1, `DERIVED_RELATIONSHIP` |
| ~~5~~ | §A22's evidence length cap | **REASSIGNED** — §0.3.10.5 proves it is a rendering control; its value is deferred to **M7**, and it does not constrain M4 |
| ~~6~~ | The link repository's module name and session/transaction ownership | **CLOSED** — §0.3.10.3 |
| ~~7~~ | `documents_for()`'s exact signature and return type | **CLOSED** — §0.3.10.2 |
| ~~8~~ | `source_system` column; column types, nullability, FK `ondelete`, indexes | **CLOSED** — §0.3.10.3 |
| 9 | Deterministic ordering of **`documents_for()`** — its grain is evidence rows, not document ids. *(S14's ordering is no longer open: §0.3.6 freezes it as lexicographic ascending by `document_id`.)* | §0.3.3 |
| 10 | B6's retirement mechanics (§0.3.9) | — |
| 11 | A test that `linker_version` loads and validates as a non-empty string. M4 *Tests* asserts only that it is stamped on every row. **Recorded as a future test requirement; it does not expand M4's scope** | §0.3.5 |

---

### 0.3.8 Measured link expectation — OBSERVED, not architecture

Recomputed during the audit against the live 233-row database at `source_system='csv_demo'`,
using whole-token and token-boundary matching. **This is a property of the committed dataset.**
It is the expectation M4's tests assert; it is **not** a rule, and no rule may be inferred from
it.

| Customer | `ID_TOKEN` | `EXACT_NAME` |
|---|---|---|
| CUST-007 Meridian Textiles | DOC-005, DOC-006, DOC-009 | DOC-005, DOC-006, DOC-009 |
| CUST-015 Unity Pharma | — | DOC-004, DOC-008 |
| CUST-021 Deltaforge Analytics | DOC-007 | DOC-007, DOC-011 |
| the other 47 customers | — | — |

Under §0.3.3's grain this is **11 persisted rows**: 3 + 3 for CUST-007, 2 for CUST-015, 1 + 2
for CUST-021. DOC-001, DOC-002, DOC-003, DOC-010 and DOC-012 are linked to no customer by any
mechanism — correctly: they name none.

Two OBSERVED facts M4's fixtures must not ignore:

- **The name-collision surface is 26 groups, not one.** The dataset holds 16 shared first name
  tokens and 10 shared last tokens — `Westbrook` × 5, `Quantix` × 4, `Health` × 9, `Foods` × 9,
  and, most pointedly, **`Meridian Foods` (CUST-038)** beside Meridian Textiles and
  **`Deltaforge Health` (CUST-027)** beside Deltaforge Analytics. §A25 test 7 names three
  customers; the rule it protects faces all 26 groups. Token-boundary matching answers all of
  them correctly — measured, zero false links — which is *why* substring matching is banned.
- **A link can be mechanically right and semantically thin.** DOC-004 links to CUST-015 by
  `EXACT_NAME`, but the match comes from a **deal title** — *"Largest open negotiation: Unity
  Pharma - Integration Services (DEAL-010)"* — not from a statement about the customer. VS-01
  accepts this: a link is evidence that a document *mentions* a customer, and the reviewer reads
  the cited span. It is recorded here so a later slice does not mistake link presence for
  aboutness.

---

### 0.3.9 D-7 — test evolution that M4 will require: **specified, not authorised**

The audit found five committed assertions that M4 will contradict. This section **specifies**
the exact evolution each one needs, so that it is designed and reviewed now rather than
discovered as a red suite later.

> **Status of this section.** It is a **specification of future work**. It is **not executed**,
> and it **is not an authorisation**. No approval has been given for any of these changes.
> An implementation may carry out T1–T5 **only after M4 itself is explicitly approved**, and
> only in the form specified here. Nothing in this section licenses a change made before that
> approval, and nothing in it licenses a change beyond the five rows below.

The governing principle is unchanged and is not weakened by anything here: **M1, M2 and M3
implementation remains frozen.** T1–T5 describe changes to *test files and the README* that
assert the absence of a thing M4 legitimately adds. **None of them changes
`app/intelligence/`, `app/relationships/`, any Layer 1 module, any migration, or `data/`.**

| # | Assertion | Why M4 contradicts it | Specified evolution (not yet authorised) |
|---|---|---|---|
| T1 | `tests/unit/test_m3_boundary.py::test_app_evidence_does_not_exist` | asserts `app/evidence` does not exist | **Remove this obsolete M4-existence assertion only.** Its purpose — "M4 has not started; M3 must not have started it either" — expires exactly when M4 starts. **The unrelated M3 boundary assertions beside it are retained unchanged**: no M3 module imports `app.evidence`, and no M3 module names M4's vocabulary. Those two become the whole of M3's side of the boundary. `app/intelligence/` is not touched |
| T2 | `tests/unit/test_m1_boundary.py`, the importer scan asserting every importer of `app.intelligence` lives under `app/relationships/` | `app/evidence/` must import M1's contract | **Extend the whitelist to `{app/relationships/, app/evidence/}`** for the legitimate `app/evidence` import boundary — extend, never relax. The test's own docstring already describes this evolution: it named M2 rather than being relaxed when M2 arrived, and must name M4 the same way. An importer that is neither still fails the build |
| T3 | `tests/unit/test_m2_boundary.py::test_documents_for_does_not_exist_in_the_package` (B6) | `documents_for()` becomes an M4-owned API | **Move, do not drop.** §A11's mirror invariant requires the negative half — `app/relationships/` still exports no `documents_for` — to survive, so it is re-homed in M4's test file beside the positive half. `app/relationships/` itself is untouched and stays byte-identical to `bc0525d` |
| T4 | `tests/integration/test_h3_migrations.py`, the exact table-set equality after `upgrade head` | the first additive Layer 2 table breaks set equality | **Extend the expected set with the Layer 2 table** — extend, never weaken equality to a subset check. §A27.10's "full Layer 1 suite passes unchanged" means no Layer 1 *behaviour* changes; the canonical and operational tables, their columns, constraints and indexes are unaltered, and the downgrade path still returns the database to empty |
| T5 | `tests/unit/test_i2_readme.py`, which collects each test layer and asserts the counts the README quotes, including the "4731 tests in four layers" total, **and separately pins the `ruff check app/ tests/ scripts/` and `mypy app/` counts** | M4 adds tests, so the quoted counts stop matching; M4 also adds source files, so the lint counts may move | **Update the README test counts as the existing I2 mechanism requires, and — per §0.3.11 D-M4-B4 — the Ruff and Mypy counts on the same terms.** This is not a new obligation for the test counts: `29776e0`, `bc0525d` and `34486eb` each updated `README.md` by exactly four lines for the same reason. The lint half is recorded by §0.3.11: these are informational project-state counts, so **`ruff = 69` and `mypy = 9` are M3-era observations, not M4 contracts**, and no test may be weakened or skipped to preserve them |

**Current state, verified.** At the time of writing, `app/`, `tests/`, `config/`, `migrations/`,
`data/` and `README.md` are byte-identical to `34486eb`; `app/relationships/` is byte-identical
to `bc0525d`; `app/evidence/` does not exist; and the Layer 1 fingerprint is `1d891b0b…`. **None
of T1–T5 has been performed.**

---

### 0.3.10 The four implementation-gate blockers, closed 2026-09-21

The gate of 2026-09-21 found four questions that M4's deliverables need and §0.3.7 deferred.
They are closed here. §0.3.6's S14 decisions are **not** reopened: `CONTRACT_DOCUMENT_TYPE`,
exact case-sensitive matching, `document_id` deduplication, lexicographic ordering,
`LinkedDocument` as composition, the absence of evidence priority and of any history framework,
the M3 import ban and the M4-owns / M5-invokes split all stand unchanged.

---

#### 0.3.10.1 B1 — `EvidenceKind.DERIVED_RELATIONSHIP`

**Decision.** Every `Evidence` M4 attaches to a `DerivedLink` carries
**`EvidenceKind.DERIVED_RELATIONSHIP`**, citing a `DocumentCitation`. No new `EvidenceKind` is
introduced and none of the other four is used for a link.

**Evidence, from frozen M1 code.**

1. `EvidenceKind`'s own docstring glosses its four usable members in declaration order — *"a
   measured canonical value … a link this system inferred … text a document happens to contain …
   a rule the project chose"*. `DERIVED_RELATIONSHIP` is the second: **a link this system
   inferred**. A `DerivedLink` is exactly that.
2. `_EVIDENCE_CITATIONS` lets `DERIVED_RELATIONSHIP` cite **either** citation shape, while
   `DOCUMENT_SPAN` accepts only a `DocumentCitation`. The wider allowance exists for the kind
   that describes an inference, which may be grounded in a record field or in text.
3. **M1's committed test asserts it on the wire.**
   `test_a_derived_link_serialises_both_ends_and_its_whole_provenance` pins
   `DerivedLink.to_payload()` to `"evidence": [{"kind": "DERIVED_RELATIONSHIP", "citation":
   {"kind": "document", …}}]`. That is not a fixture convention: it is a frozen assertion on a
   `DerivedLink`'s serialised form, and any other kind would fail it.
4. The same kind is used in the second `DerivedLink` the M1 suite builds.

**Classification: DERIVED.** Point 3 is decisive — a committed M1 test already fixes the
serialised kind of a derived link's evidence, so no other choice is available without breaking
the M1 freeze.

---

#### 0.3.10.2 B2 — `documents_for()` returns `tuple[LinkedDocument, ...]`

**The contract as it stood.** §A11 describes `documents_for(customer)` as returning *"derived
links with basis, matched token and offsets"*. That is a statement about **content**, not a
Python type; §0.3.7 #7 recorded the signature and return type as still open, so nothing is being
overridden here.

**Decision.**

```
documents_for(
    session: Session,
    scope:   Scope,
    customer_source_id: str,
) -> tuple[LinkedDocument, ...]
```

- **The return type is `tuple[LinkedDocument, ...]`.** §A11's description is preserved: a
  `LinkedDocument` holds the `DerivedLink`, so every returned value still carries its basis,
  matched token and offsets.
- **There is no adapter, and no unnamed seam.** The composition happens in exactly one place.
  **§0.3.11 D-M4-B1 revises *which* place.** As originally written this bullet put the
  construction of `LinkedDocument` in the repository read; that was found, at the 2026-09-21
  implementation gate, to contradict §0.3.9 T2, because reconstructing the contained
  `DerivedLink` forces `app/persistence/` to import `app.intelligence`. **The repository
  performs the query and the `documents` join and returns persisted data only;
  `app/evidence/documents.py` is the sole constructor of `LinkedDocument` and of the
  `DerivedLink` it holds.** Nothing else in VS-01 constructs a `LinkedDocument`, and the
  single-place property this bullet exists to protect is preserved — it now names the
  evidence layer rather than the repository. See §0.3.11.
- **`document_type` is read from Layer 1, never stored on the link.** §A18's column list gains
  no `document_type` column; the value is joined at read time from `documents.document_type`,
  so a Layer 1 correction is reflected without re-deriving links.
- **Signature shape** follows M2's query convention — `(session, scope, customer_source_id)`,
  as in `neighbourhood`, `escalation_path` and `policy_documents`. Following it is a **choice**:
  no committed test compels M4 to adopt M2's parameter order.
- **`documents_for()` reads persisted rows.** §A11 says links *"are produced by
  `app/evidence/linker.py`, read through `documents_for(customer)`"*: the linker derives and the
  repository persists; `documents_for` reads back. It does not re-run the linker.

**Classification. Every element of this decision is AUTHORED**: the signature shape (M2's
convention, followed by choice), the return type, the placement of the composition in the
repository read, and the read-persisted-rows reading of §A11. Nothing frozen compels any of them
— §0.3.7 #7 recorded the whole question as open, and it is answered here rather than derived. The alternative — returning
`tuple[DerivedLink, ...]` and naming a separate component to attach `document_type` — was
considered and rejected: it adds a second query or a second type-mapping step for a value that
is already on a row the read must touch, and it is the shape that leaves a seam.

**Still deferred:** `documents_for()`'s **ordering** (§0.3.7 #9). It does not block M4 — M4's
acceptance asserts which links are returned, not their order, and S14 sorts its own output — but
it is a public API M5 will consume, and the argument that froze S14's order applies to it. It is
recorded here as the next ordering question, not answered.

---

#### 0.3.10.3 B3 — the persistence contract

Every item below is grounded in an existing Layer 1 convention where one exists; the rest are
labelled.

**Session and transaction.**

- **The caller owns the session.** Every Layer 1 repository function takes `session: Session` as
  its first parameter (`app/persistence/repositories/canonical.py::upsert`, `load_states`,
  `canonical_row`), and no other pattern exists in the codebase. M4's repository does the same.
  **AUTHORED**, grounded in that uniform convention — a repository that opened its own session
  would contradict no committed test, so this is a choice to follow the house rule, not a
  deduction from it.
- **The caller owns the transaction.** No Layer 1 repository calls `commit`, `rollback` or
  `begin`; the orchestrator opens `sessions.begin()` and its context manager commits
  (`app/ingestion/orchestrator.py`). **M4's repository calls none of
  `commit`/`rollback`/`begin`/`close`.** **AUTHORED**, grounded in the same convention. Note that
  M2's frozen rule is *read-only*, caller-owned; M4 writes, so only the ownership half carries
  over and it carries over by choice.
- **No explicit `flush`.** Nothing downstream needs the generated primary keys inside the same
  call, so the repository issues its statements and returns. **AUTHORED.**

**Conflict behaviour.**

- The insert is `insert(...).on_conflict_do_nothing(constraint=
  "uq_document_customer_links_identity")` — **DO NOTHING, never DO UPDATE**. §0.3.4 states that
  nothing is ever updated in place; `on_conflict_do_update`, which Layer 1 uses for canonical
  upserts, would contradict it. The conflict is resolved **by the database**, not by a
  pre-existence check. **DERIVED** from §0.3.4 plus Layer 1's named-constraint `on_conflict`
  pattern.
- **Rows are sorted before insertion**, matching `upsert`'s `ordered = sorted(rows, …)`, so the
  statement is byte-stable across runs. **AUTHORED**, grounded in that convention.

**Model.** `app/persistence/models/document_customer_link.py`, registered on `Base.metadata`.
**It does not use `ProvenanceMixin`**: a derived link has no source system, no ingestion run and
no `record_hash`, and §A18's column list contains none of the eight provenance columns. **DERIVED.**

| Column | Type | Null | Grounding |
|---|---|---|---|
| `id` | `UUID` primary key `pk_document_customer_links` | NOT NULL | Every Layer 1 table uses a UUID surrogate key; the constraint *name* is forced by `NAMING_CONVENTION`. The UUID *type* is **AUTHORED**, grounded in that convention — a bigserial would contradict no committed test |
| `document_id` | `UUID` FK → `documents.id` | NOT NULL | **DERIVED** |
| `customer_id` | `UUID` FK → `customers.id` | NOT NULL | **DERIVED** |
| `basis` | `String(50)` | NOT NULL | Layer 1 sizes short enumerated strings at 50 (`status`). **AUTHORED** |
| `matched_token` | `String(255)` | NOT NULL | It is a copy of either `customers.name` or `documents.source_id`, both `String(255)`. **DERIVED** |
| `match_start` | `Integer` | NOT NULL | Offsets into text. Layer 1 has no precedent. **AUTHORED** |
| `match_end` | `Integer` | NOT NULL | As above. **AUTHORED** |
| `linker_version` | `String(50)` | NOT NULL | A short version string (§0.3.5). **AUTHORED** |
| `layer1_fingerprint` | `String(64)` | NOT NULL | A SHA-256 hex digest, exactly as `record_hash` is `String(64)`. **DERIVED** |

**No `source_system` column.** Both foreign keys point at rows that already carry one, a link may
never cross source systems, and §A18's list does not include it. This closes the first clause of
§0.3.7 #8. **DERIVED.**

**Every column is NOT NULL**, because `DerivedLink` validates each corresponding value as
present and non-empty before a row can exist. **DERIVED.**

**Foreign keys: `ondelete='CASCADE'` on both.** Layer 1 uses `SET NULL` for canonical entity FKs
and `CASCADE` for dependent child rows. `SET NULL` is **structurally impossible** here because
both columns are NOT NULL, and a link row without either endpoint asserts nothing. **DERIVED.**

**Uniqueness, database-enforced.** `UniqueConstraint(document_id, customer_id, basis,
linker_version, layer1_fingerprint, name="uq_document_customer_links_identity")` — the key
§0.3.4 fixed, named in Layer 1's `uq_<table>_<suffix>` style. **DERIVED.**

**Indexes.** `ix_document_customer_links_customer_id` on `customer_id`, because `documents_for()`
queries by customer and the unique constraint's index leads with `document_id`, which does not
serve that lookup. Layer 1 indexes every FK column, so
`ix_document_customer_links_document_id` is added for consistency although the unique index
already covers that access path. **DERIVED** (the customer index), **AUTHORED** (keeping the
redundant document index for convention).

**Repository responsibilities** — `app/persistence/repositories/document_links.py`, module name
**AUTHORED** in the style of `canonical.py`, `cursors.py`, `runs.py`:

- **write:** one function taking `(session, links)` that sorts, inserts with
  `on_conflict_do_nothing`, and returns the number of rows actually inserted — which is how a
  caller observes that a re-run inserted nothing (§A27.8).
- **read:** one function taking `(session, scope, customer_source_id)` that joins the link rows
  to `documents` and returns **the persisted link data together with the joined
  `document_type`** — rows, not domain objects. **Revised by §0.3.11 D-M4-B1**, which moves the
  construction of `LinkedDocument` out of this function and into
  `app/evidence/documents.py`; the join itself stays here, so the repository remains the sole
  location of the query.
- The repository performs **no derivation** — it never matches text — and **no rendering**.
- **The repository imports neither `app.intelligence` nor `app.evidence`** (§0.3.11 D-M4-B2).
  It is infrastructure code, and the M1 importer whitelist of §0.3.9 T2 is unchanged.

---

#### 0.3.10.4 B4 — linker matching semantics

`DocumentCitation` is frozen as `(document_id, start, end)` with **no field discriminator**, so a
span can address only one text per document. That forces the first decision below.

**Citable text.** A document's **citable text** is

```
citable_text(document) = (title or "") + "\n" + (body_text or "")
```

Every offset this milestone produces — `match_start`, `match_end` and the `DocumentCitation`
span — indexes **that string and no other**. One definition serves both the persisted columns and
the citation, so the two can never diverge.

- §A11 permits a match in *"title or body"*. Addressing `body_text` alone would silently drop
  the title half and make a title-only match **unrepresentable**, since `DerivedLink` requires
  non-empty evidence and `DocumentCitation` requires a non-empty span.
- A NULL `title` contributes the empty string; this closes §0.3.7 #2. A NULL `body_text` never
  arises, because §A23 already makes the linker skip such a document entirely.
- **Classification: AUTHORED.** The frozen `DocumentCitation` shape forces *a* single text; which
  one is a choice, and this is it. **OBSERVED:** the committed corpus has **zero** title-only
  matches, so this decision changes no measured value in §0.3.8 — it decides what happens on data
  that does not yet exist.

**Matching rules.**

| Aspect | Rule | Class |
|---|---|---|
| `ID_TOKEN` predicate | The canonical `source_id` appears in citable text bounded on both sides by a character that is **not** `[A-Za-z0-9_-]`, or by the start/end of the text. The hyphen is inside the class, so `CUST-007` matches in `… (CUST-007) …` but **not** in `CUST-007Z`, `CUST-0071` or `XCUST-007` | **AUTHORED** |
| `ID_TOKEN` case | **Case-sensitive.** §A11 says the *canonical* `source_id` appears; a differently cased string is not that identifier | **AUTHORED** |
| `EXACT_NAME` predicate | The full `customers.name` appears bounded on both sides by a character that is **not** `[A-Za-z0-9]`, or by the start/end of the text | **AUTHORED** |
| `EXACT_NAME` case | **Case-insensitive** | **FROZEN** — §A11 states it |
| Normalization | **None.** No Unicode normalization, no case folding beyond `EXACT_NAME`'s own comparison, no whitespace collapsing, no punctuation stripping, no accent folding. Citable text is searched exactly as Layer 1 stores it | **AUTHORED** |
| Multiple occurrences | **The first occurrence in citable text wins** — the one with the lowest `match_start`. Exactly one link row is written per `(document, customer, basis)`, carrying that one span | **AUTHORED** |
| `match_start` / `match_end` | The half-open span `[start, end)` of that first occurrence in citable text. `match_end - match_start` equals the matched text's length | **AUTHORED** |
| Quoted-span semantics | **`citable_text(document)[match_start:match_end] == matched_token`** must hold for every persisted row, and the `DocumentCitation` on the link's evidence carries the identical `(document_id, match_start, match_end)`. `matched_token` is therefore the text **as the document writes it**, not the canonical form — for a case-insensitive `EXACT_NAME` hit on "meridian textiles", `matched_token` is `"meridian textiles"` | **AUTHORED** |

**DOC-009, the adversarial fixture.** Measured on the live database, DOC-009 contains
`Meridian Textiles` **three** times and `CUST-007` once:

| Field | Basis | Offsets within that field |
|---|---|---|
| `title` (`Account Review Notes - Meridian Textiles`) | `EXACT_NAME` | `[23, 40)` |
| `body_text` | `EXACT_NAME` | `[16, 33)` and `[219, 236)` |
| `body_text` | `ID_TOKEN` | `[35, 43)` |

In **citable text** those become `EXACT_NAME` at `[23, 40)`, `[57, 74)` and `[260, 277)`, and
`ID_TOKEN` at `[76, 84)`. Under the first-occurrence rule DOC-009 therefore persists **exactly
two** rows for CUST-007:

```
(DOC-009, CUST-007, EXACT_NAME, "Meridian Textiles", 23,  40)
(DOC-009, CUST-007, ID_TOKEN,   "CUST-007",          76,  84)
```

These values are **uniquely determined** — no other pair of offsets satisfies the rules — which
is what the gate required beyond mere determinism. M4's tests assert them literally.

---

#### 0.3.10.5 §A22's evidence length cap — a rendering control, not a storage one

The gate asked for proof rather than reassignment. §A22's control reads: *"**Rendered** only as
quoted, length-capped, escaped evidence with id and span. The linker never treats body text as
configuration."* Two independent sentences: the first governs **rendering** and carries the cap;
the second governs the **linker** and carries no length component.

§A17 confirms the split: the hashed decision payload's evidence contract is
`{kind: "document", document_id, start, end}` — **a span, never the text** — and the *"rendered
narrative"* is separately described as *"a view, not hashed"*. Nothing that M4 stores contains
document prose, so a cap has nothing to apply to at the storage or derivation layer.

**Conclusion: the cap constrains rendering, and belongs to the milestone that renders** — M7,
whose *Change* names `app/decisions/brief.py` (narrative rendering) and
`app/decisions/templates/`. **The cap's value stays deferred to M7**; this section assigns
ownership, it does not invent a number. It does not block M4: the only text M4's
`citations.py` returns is the span of a matched token, whose length is bounded by the match
itself. §0.3.7 #5 is amended accordingly.

---

### 0.3.11 M4 boundary clarification — three verified contradictions, closed 2026-09-21

A second implementation gate, run before any M4 file was created, measured three conflicts
between §0.3.10 and committed tests. The first two are genuine contradictions: the
specification as written could not be implemented without failing a test the plan itself
declares authoritative. The third is a latent obligation §0.3.9 under-described.

Nothing measured in §0.3.8 or §0.3.10.4 changed. **The 11-row corpus expectation, the DOC-009
offsets, the 26 collision groups and every matching rule were independently re-measured against
the live 233-row `csv_demo` database during this gate and reproduced exactly.** This section
moves a construction step between two modules, preserves one whitelist, and records two
reporting rules. It alters no behaviour a test can observe at the linker's boundary.

**All four decisions below are AUTHORED.** None is forced by frozen code: each resolves a
conflict between two things the plan had already chosen, and a different resolution was
available in every case. They are recorded here rather than left to an implementer precisely
because they are choices.

---

#### D-M4-B1 — persistence reads; evidence reconstructs

**The contradiction.** §0.3.10.2 placed the construction of `LinkedDocument` — and therefore of
the `DerivedLink` it contains — inside
`app/persistence/repositories/document_links.py`. Reconstructing a `DerivedLink` from a
persisted row requires `EntityRef`, `LinkBasis`, `LinkConfidence`, `Evidence` and
`DocumentCitation`, all of which live in `app/intelligence/contract.py`. §0.3.9 T2 fixes the
M1 importer whitelist at exactly `{app/relationships/, app/evidence/}` and states that an
importer which is neither *"still fails the build"*.
`tests/unit/test_m1_boundary.py::test_only_the_relationship_model_depends_on_the_foundation`
scans `app/`, `scripts/`, `migrations/` and `docker/`, so the repository module is in its scope
and the build would fail. Routing the import through `app.evidence` instead would invert the
Layer 1 → Layer 2 direction *and* close an import cycle between `documents.py` and
`document_links.py`.

**Decision.**

> **The repository owns persistence and read concerns only.**
> `app/persistence/repositories/document_links.py`:
>
> - queries `document_customer_links`;
> - joins `documents`;
> - returns the persisted link data together with the joined `document_type`, as rows;
> - constructs **no** `DerivedLink` and **no** `LinkedDocument`;
> - imports **no** `app.intelligence` module and **no** `app.evidence` module.
>
> **The evidence layer owns domain reconstruction.** `app/evidence/documents.py` builds
> `EntityRef`, `LinkBasis`, `Evidence`, `DocumentCitation`, `DerivedLink` and `LinkedDocument`
> from the repository's rows, **using the frozen M1 contract definitions**. M1 is not modified
> and none of its dataclasses is duplicated, re-declared or shadowed.
>
> **`documents_for()` remains the public evidence-layer API**, with the signature §0.3.10.2
> fixed and unchanged:
>
> ```
> documents_for(session, scope, customer_source_id) -> tuple[LinkedDocument, ...]
> ```
>
> Its behaviour is: call the repository, receive persisted link and document data, construct
> `LinkedDocument` values in `app/evidence/documents.py`, return the tuple.

**This is not the unnamed adapter seam §0.3.10.2 rejected**, and the distinction is the reason
this resolution is admissible rather than a reversal. The seam that section forbade was a
*third* component — a converter sitting between the repository and the evidence layer, owned by
neither, with a second query or a second type-mapping step. No such component exists here.
There remain exactly two modules and one query: the repository is the **sole** location of the
database read and the `documents` join, and `app/evidence/documents.py` is the **sole**
location of conversion into `LinkedDocument`. §0.3.10.2's load-bearing property — that exactly
one place constructs a `LinkedDocument` — is preserved verbatim; only which place is named has
changed. The repository is not permitted to return a competing domain abstraction of its own,
and **no additional public adapter module is introduced.**

**Why the repository must not reconstruct `DerivedLink`**: doing so forces `app/persistence/`
to depend on `app.intelligence`, which is exactly what T2 forbids and what D-M4-B2 preserves.

**Consequences.** §0.3.10.2's second bullet and §0.3.10.3's *read* bullet are amended above.
`document_type` is still read from Layer 1 at join time and still never stored on the link
row (§A18 gains no `document_type` column), so a Layer 1 correction is still reflected without
re-deriving links. Every other element of §0.3.10.2 and §0.3.10.3 — the signature shape, the
return type, the read-persisted-rows reading of §A11, the write function, the unique key, the
column table, the FK and index decisions — stands unchanged.

**Remaining uncertainty.** `documents_for()`'s **ordering** remains deferred (§0.3.7 #9). This
section does not settle it.

---

#### D-M4-B2 — the T2 whitelist is unchanged

**Decision.**

> **§0.3.9 T2 stands exactly as written.** The allowed importers of `app.intelligence` remain
> `app/relationships/` and `app/evidence/`. **`app/persistence/` is not added**, and the
> existing architectural boundary test remains authoritative rather than being extended to
> accommodate M4.

The resulting dependency direction, which an M4 boundary test must assert:

```
app.evidence  →  app.intelligence        (permitted, T2)
app.evidence  →  app.persistence         (permitted; the repository read)
app.evidence  →  app.relationships       (permitted, unused by M4)

app.persistence   ✗→  app.evidence
app.persistence   ✗→  app.intelligence
app.relationships ✗→  app.evidence
M3                ✗→  app.evidence
```

**Post-implementation verification is required**, not assumed: M4 must assert that
`app/persistence/repositories/document_links.py` imports neither `app.intelligence` nor
`app.evidence`. The repository remains infrastructure code.

Note that T1 still removes `test_app_evidence_does_not_exist` — that assertion expires when M4
starts — while **every other M3-side assertion is retained**, including that no M3 module
imports `app.evidence`. The existence of `app/evidence/` is not permission for M3 to reach it.

---

#### D-M4-B3 — the CUST-007 literal must not weaken the secret scanner

**The conflict.** `scripts/secret_scan.py`'s `quoted_secret_assignment` rule matches any
identifier containing `token` assigned a quoted, whitespace-free value of at least
`GENERIC_MIN_LENGTH = 8` characters. `matched_token` contains `token`, and `CUST-007` is
exactly 8 characters, so the natural spelling of §0.3.10.4's pinned assertion — that id
assigned to `matched_token` in the quoted form — **is flagged**. Verified by running the
committed rule set against a probe file. The same assignment of `"Meridian Textiles"` is
**not** flagged: the rule's
value group `["']([^"'\s]+)["']` rejects a value containing a space. M1 met the same rule in
`LinkBasis` and resolved it by deriving member values with `auto()` instead of writing quoted
literals — the precedent for working around the scanner rather than changing it.

**Decision.**

> - **The secret scanner is not weakened, and its rules are not modified.** No change to
>   `scripts/secret_scan.py`, its patterns, its minimum length or its prose-skipping behaviour.
> - **`CUST-007` is not added to `ALLOWED_FINDINGS`.** The allowlist is for clearly synthetic
>   credential-shaped fixtures; a customer identifier is not one, and pinning it there would
>   teach the next reader that the allowlist absorbs inconvenient matches.
> - **The test suite asserts the exact literal `"CUST-007"`**, and must do so through an
>   expression that does not assign it to a `token`-named identifier. The preferred form is the
>   inline comparison:
>
>   ```
>   assert link.matched_token == "CUST-007"
>   ```
>
>   Any semantically equivalent expression preserving the exact contract is acceptable.
> - **The runtime value remains exactly `CUST-007`.** The scanner constrains how a test is
>   *spelled*, never what it asserts. **No test may be weakened, loosened or skipped to satisfy
>   the scanner**, and an implementation that asserts a different value, a prefix, a length or a
>   truthiness check in place of the literal is wrong.

**Classification: AUTHORED.** Three resolutions existed — amend the scanner, pin the finding,
or spell the assertion differently — and the third is chosen because it is the only one that
leaves both the security tooling and the asserted contract untouched.

---

#### D-M4-B4 — T5 covers the Ruff and Mypy counts too

**The gap.** §0.3.9 T5 named only the per-layer test counts. `tests/unit/test_i2_readme.py`
also pins the counts the README quotes for `ruff check app/ tests/ scripts/` and `mypy app/`,
currently **69** and **9**. M4 adds source files, so either may legitimately move, and T5 as
written did not authorise updating them.

**Decision.**

> **T5 authorises updating the README's test count, Ruff count and Mypy count** when those
> values change as a direct consequence of M4.
>
> - These are **informational project-state counts**, not behavioural contracts. The README
>   test's job is to keep the README honest about the current state, and it continues to do
>   exactly that.
> - **`ruff = 69` and `mypy = 9` are M3-era observations. They are not M4 acceptance criteria**,
>   and no historical M0 or M3 value is an immutable M4 contract.
> - **No test behaviour may be modified, and no lint finding suppressed, merely to preserve
>   them.** If M4 legitimately changes a count, the README is updated to the actual verified
>   value; if M4 changes none, the README is left alone.
> - The distinction that matters: a *count* may move, but a *gate* may not. M4 introducing new
>   Ruff findings of its own is a defect to fix, not a number to re-quote — this decision
>   licenses recording reality, never lowering the bar.

**Classification: AUTHORED**, and narrow: it extends an existing reporting obligation to two
sibling values the same mechanism already validates.

---

## 0.4 M5 re-specification — pre-implementation, 2026-09-22

M4 closed at `65eb462` (specification `42f9eeb`, correction `0b017e2`). A takeover audit run
before M5 began measured the repository against this plan and found **six** places where an
implementer would have had to invent architecture. Five are the ones the audit named; the sixth
was found while closing the first and is the most serious of the set.

> **Status of this section.** Unlike §0.3.9, this section **is an authorisation**. Each decision
> below is settled, and §0.4.4 explicitly authorises the test and README evolution M5 requires.
> Nothing here licenses a change outside the rows it names.
>
> **M1, M2, M3 and M4 remain frozen.** No decision below edits `app/intelligence/`,
> `app/relationships/`, `app/evidence/`, `app/persistence/`, any migration, `data/`, or any
> Layer 1 module. Every one of them was checked against the committed source before being
> written, and each records what it was checked against.

**The six.**

| # | Blocker | Closed by |
|---|---|---|
| B1 | §A16 requires six satisfied actions for CUST-007; frozen `Position.proposed_action` carries **one**, and no rule mapped many to one | §0.4.1 |
| B2 | `SupportContext` needs ticket facts that exist only in M3's **private, frozen** `_Ticket` | §0.4.2 |
| B3 | Nothing in the plan owns the **production** call to `derive_and_persist()`; without it S14 is silently empty | §0.4.3 |
| B4 | M5 necessarily fails a committed M1 boundary test, and no §0.3.9 equivalent authorised the fix | §0.4.4 |
| B5 | `app/analysts/` → `app/evidence/` was required by §0.3.6 B but never authorised as a dependency | §0.4.5 |
| **B6** | §A16 makes **Support** propose an action on `DEAL-001` while §A14 forbids `SupportContext` any deal field — the contested object was structurally unnameable | §0.4.6 |

**A second review pass, 2026-09-22, found three further defects — all of them in §0.4 itself, none
in M1–M4 — and §0.4.9 closes them: the `SupportContext` carrier for S1–S10 (D-M5-B7), S14's
unstated status (D-M5-B8), and a silently narrowed §A16 precondition (D-M5-B9).** §0.4.3's M7
forward amendment and §0.4.7's purity language were reviewed and confirmed sound.

---

### 0.4.1 D-M5-B1 — one `Position` per (function, contested object): **AUTHORED**, on derived foundations

**The requirement as it stood.** §A16 states that at the pinned `as_of` CUST-007 "triggers all
six non-`NO_ACTION` entries", and §0.2.1's *"One measured caveat for M5"* instructs M5 to
evaluate `REVIEW_INVOICE_DISPUTE` from the context's ticket rows. Frozen `Position` carries a
single `proposed_action`. M5's *Acceptance* named two positions. No rule mapped five satisfied
Support entries onto one action, and no carrier held the rest.

**Evidence, verified against the committed source.**

1. **`Position.object_ref` is a required, non-empty field** of the frozen M1 contract
   (`app/intelligence/contract.py:511`, enforced by `_require_text`). §A5's one-line Position
   definition omits it; M1's implementation does not. It is load-bearing and was unspecified.
2. §A15 detects a conflict "over the same object identity (**here `DEAL-001`**)", and §A5
   defines a conflict as two positions "over the same object".
3. `Conflict.__post_init__` enforces one position per function **per conflict**, and that every
   position's `object_ref` equals the conflict's. **It places no bound on how many positions a
   function states overall.**
4. §A18's `risk_positions` is `assessment_id` FK, `function`, `stance`, `proposed_action`,
   `rationale`, `citations` — **with no unique constraint**. Several rows per function per
   assessment are structurally permitted, and always were.
5. §A16's own closing sentence — "CUST-007 triggers all six non-`NO_ACTION` entries, **and the
   last two conflict**" — is satisfied exactly and only by six positions of which two share an
   object.

**Decision.**

> **An analyst emits one `Position` per satisfied catalogue entry, each carrying that entry's
> contested object in `object_ref`. Nothing is discarded, nothing is ranked, and no action is
> selected over another.**
>
> The apparent "many actions, one field" contradiction was an artefact of reading `Position` as
> *one per function* rather than *one per function per contested object*. The frozen contract
> already expresses the intended shape.
>
> **§A16 gains an `Object` column**, fixing `object_ref` for every entry so no implementer
> chooses one:

| Action | `object_ref` | Multiplicity |
|---|---|---|
| `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA` | the customer `source_id` | at most one |
| `SCHEDULE_EXECUTIVE_SPONSOR_CALL` | the customer `source_id` | at most one |
| `ASSIGN_DEDICATED_SUPPORT_OWNER` | the customer `source_id` | at most one |
| `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` | the **deal** `source_id` | one per qualifying deal |
| `REVIEW_INVOICE_DISPUTE` | the **ticket** `source_id` | one per qualifying ticket |
| `ACCELERATE_DEAL_CLOSE` | the **deal** `source_id` | one per qualifying deal |
| `NO_ACTION` | the customer `source_id` | at most one |

> **`stance`.** `RESTRAIN` for `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED`; `ADVANCE` for
> `ACCELERATE_DEAL_CLOSE`; `NEUTRAL` for every other entry. Stance is load-bearing only for the
> contested pair, where it is what makes the opposition legible to a reader of the brief.
>
> **`NO_ACTION` is emitted by neither analyst.** §A16 leaves its *Proposed by* column empty. A
> function with no satisfied entry emits **no position**, not a `NO_ACTION` one; the empty tuple
> is the representation of "this function has nothing to say".
>
> **Ordering — a sort key, never a priority.** An analyst returns
> `tuple[Position, ...]` ordered **ascending by `(function, object_ref, proposed_action)`**, all
> three compared as strings. This is required by §A24 and mirrors the discipline already frozen
> for S14 (§0.3.6) and M2's queries: it ranks positions for reproducibility and **expresses no
> precedence between actions**. No rule anywhere in M5 reads it to choose a winner — choosing is
> M6's, by policy, and only between positions sharing an object.
>
> **The public M5 contract** is therefore `tuple[Position, ...]` per analyst, not `Position`.
> M5's *Change*, *Tests* and *Acceptance* are amended accordingly.

**Measured consequence at `ACCEPTANCE_AS_OF`, for CUST-007 — six positions.**

| # | Function | Action | `object_ref` | Stance |
|---|---|---|---|---|
| 1 | SUPPORT | `ASSIGN_DEDICATED_SUPPORT_OWNER` | `CUST-007` | NEUTRAL |
| 2 | SUPPORT | `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA` | `CUST-007` | NEUTRAL |
| 3 | SUPPORT | `SCHEDULE_EXECUTIVE_SPONSOR_CALL` | `CUST-007` | NEUTRAL |
| 4 | SUPPORT | `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` | `DEAL-001` | RESTRAIN |
| 5 | SUPPORT | `REVIEW_INVOICE_DISPUTE` | `TKT-079` | NEUTRAL |
| 6 | SALES | `ACCELERATE_DEAL_CLOSE` | `DEAL-001` | ADVANCE |

Exactly one SUPPORT and one SALES position share `DEAL-001`, so M6 detects **exactly one**
conflict and `Conflict`'s "at most one position per function" holds without M5 doing anything to
make it hold. Rows 1–3 and 5 never enter a conflict because no SALES position names their
object. §A16's "all six … and the last two conflict" is reproduced literally.

**What §A17's *"resolved action set"* means, recorded so M6 and M7 are not surprised.** It is the
set of proposed actions that survive reconciliation: every emitted action, minus those on
positions M6 overrules. For CUST-007 that is rows 1–5 (Support's five), with row 6 preserved as
dissent under `ConflictResolution.dissent`, which derives it from the conflict rather than
storing it. **This paragraph settles nothing that is M6's**; it records the arithmetic that D-M5-B1
makes possible, and no more. *(M6's own statement of it — `resolved_positions` as `Position`s,
not action ids — is §0.5.7 D-M6-B7.)*

**Classification.**

| Element | Class | Why |
|---|---|---|
| One `Position` per satisfied entry; nothing discarded | **DERIVED** | Evidence 3–5: the frozen `Conflict` invariant and the unconstrained `risk_positions` grain both already permit it, and only this reading reproduces §A16's closing sentence |
| Analysts return `tuple[Position, ...]` | **DERIVED** | Follows from the above and matches every other collection in M1's contract |
| The `Object` column of §A16 | **AUTHORED** | Nothing frozen fixes which object each action contests. §A15 fixes only `DEAL-001` for the pair; the other five are authored here so an implementer does not choose |
| `stance` per entry | **AUTHORED** | §A5 and M1 fix the vocabulary, not the mapping |
| Ordering by `(function, object_ref, proposed_action)` | **AUTHORED** | §A24 demands determinism; the key itself is authored, and is explicitly not a priority |
| `NO_ACTION` emitted by neither analyst | **DERIVED** | §A16's *Proposed by* column is empty for it |

---

### 0.4.2 D-M5-B2 — ticket facts: an **M5-owned derivation, pinned to M3's signals**: **AUTHORED**

**The requirement as it stood.** §A14 puts "Tickets" in `SupportContext` and has the analyst
report breaches; §0.2.1 requires the `billing` precondition to be evaluated "from the ticket
rows §A14 already puts in the `SupportRiskAnalyst` context". No public contract carries them.

**Evidence, verified against the committed source.**

1. `CustomerSignals` (`app/intelligence/signals.py:164`) exposes `customer`, `signals`,
   `escalation_window`, `backlog_ticket_ids` — **no ticket attributes**. Category B of the audit
   ("an existing public M3 contract suffices") is **ruled out**, and §0.2.1 ruled it out in
   writing already: `S10` reports only the dominant category.
2. `_Ticket` and `_tickets` (`signals.py:184`, `:411`) are private to a module frozen at
   `34486eb`. Category "make them public" is **excluded by the freeze**.
3. **M2 already answers a different question with a different rule.** `escalation_path()`
   returns `open_tickets`, but `_open_ticket_ids` (`app/relationships/queries.py:216`) selects
   `SupportTicket.status == 'open'` with **no `as_of`**, while M3's `_Ticket.is_open_at` ignores
   `status` and tests the resolution date against `as_of`. §0.2.1 records M3's as the authored
   rule: "The resolution *date* decides, not `status`." **The two definitions are not
   interchangeable, and M5 must use M3's**, because S1, S2, S8 and therefore the band are built
   on it. Consuming `escalation_path().open_tickets` would give `SupportContext` an
   `as_of`-insensitive notion of "open" that disagrees with the signals beside it.
4. **Every semantic M5 needs is already stated normatively in this plan and available from
   public M1 surfaces**, so the derivation reuses rules rather than reinventing them:
   - *open at `as_of`* — §0.2.1: no resolution date on or before `as_of`;
   - *SLA breach* — §A5: elapsed business days exceed DOC-003's target for the priority;
     resolved measured created→resolved, open measured created→`as_of`;
   - the targets come from the public `RiskRulesConfig.sla_resolution_targets`
     (`app/intelligence/config.py:73`), and the arithmetic from the public
     `app.intelligence.timeutil.business_days_between` and `utc_date`. Both are M1, both are
     already exported from `app.intelligence`.
   - *membership* — M2's `neighbourhood()`, exactly as M3 obtains it (§0.2.3).

**Decision.**

> **M5 owns a context-local ticket derivation. M3 is neither modified nor imported for it, and
> no rule is re-authored — only re-applied from its statement in this plan, using M1's public
> arithmetic and configuration.**
>
> **Owner.** `app/analysts/context.py`, inside the context factory of §0.4.7.
> **Input.** `(session, scope, customer_source_id, config: RiskRulesConfig)`.
> **Output.** `tuple[TicketFact, ...]`, ordered ascending by `source_id`.
> **M3 involvement.** None for this derivation. **Database access.** Yes — one read, through the
> factory, which owns the session (§0.4.7). **Writes.** None.
>
> ```
> TicketFact                    # new, M5-owned, frozen
>     source_id     str
>     priority      str | None  # Layer 1's column, nullable
>     category      str | None  # Layer 1's column, nullable
>     is_open       bool        # at scope.as_of
>     breaches_sla  bool        # at scope.as_of
> ```
>
> `TicketFact` carries **no** subject, description, assignee, customer key, deal, project or
> monetary field. It is the smallest shape that answers §A16's ticket-level preconditions and
> grounds a `RecordCitation`, and it carries nothing else.
>
> **Exact semantics, restated so they are a specified property and not an accident of whichever
> expression an implementer writes.**
>
> - **Placed in time.** A ticket with NULL `created_at` is **excluded entirely** and produces no
>   note, matching M3 exactly and the open gap of §0.2.2. A ticket whose `created_at` date is
>   after `as_of` is **not yet visible** and is excluded. Dates are UTC dates via `utc_date`.
> - **`is_open`.** `resolved_at` is NULL, **or** its UTC date is strictly after `as_of`.
>   `status` is **not read**, is not consulted as a fallback, and does not break a tie. This is
>   M3's rule verbatim (§0.2.1) and deliberately **not** M2's.
> - **`breaches_sla`.** `target = sla_resolution_targets[priority]`. **A priority the policy does
>   not name, and a NULL priority, have no target and therefore cannot breach** — inventing one
>   would manufacture breaches DOC-003 never states. The measured interval ends at the resolution
>   date when one falls on or before `as_of`, and at `as_of` otherwise; the breach holds when
>   `business_days_between(created, end) > target`.
> - **`billing`.** Exact, case-sensitive equality to the string `"billing"`, declared in
>   `app/analysts/` as `BILLING_CATEGORY = "billing"`. **No normalization, no case folding, no
>   stripping, no substring or prefix match, no synonym list.** `None` is not `billing` and
>   contributes nothing. This is the discipline §0.3.6 fixed for `CONTRACT_DOCUMENT_TYPE` and M2
>   fixed for `POLICY_DOCUMENT_TYPE`, applied to the one Layer 1 category string M5 reads.
> - **Breach representation.** A boolean per ticket, plus the counts already on `SignalSet`
>   (S7, S8). **M5 introduces no breach severity, no overdue-by measure and no new note type.**
>
> **The divergence risk is closed by a test, not by a promise.** Because two implementations of
> one stated rule now exist, **M5 is not complete without an equivalence test** asserting, over
> **every** customer in the demo dataset at both `2026-09-18` and the `2026-08-27` fallback:
>
> | M5 derivation | must equal | M3 signal |
> |---|---|---|
> | `sum(f.is_open)` | = | `S1 open_ticket_count` |
> | `sum(f.is_open and f.priority == 'high')` | = | `S2 open_high_priority_count` |
> | `sum(f.priority == 'high')` | = | `S2b high_priority_total` |
> | `sum(f.breaches_sla)` | = | `S7 sla_breach_count` |
> | `sum(f.is_open and f.priority == 'high' and f.breaches_sla)` | = | `S8 open_sla_breach_high_count` |
> | `{f.source_id}` | = | the ids `neighbourhood()` returns, minus those excluded above |
>
> This makes drift a **build failure** rather than a latent defect, and it is the reason this
> decision is acceptable at all. It is the same technique B9(b) and §A25 test 13b already use:
> write the would-be-wrong computation out and assert against it.

**What this decision does not do.** It does not read `status`; it does not re-resolve
relationships (membership stays `neighbourhood()`'s, §0.2.3); it does not touch
`app/intelligence/`; it adds no signal, no note type and no configuration key; and it does not
give `SupportContext` any field §A14 forbids.

**Classification: AUTHORED.** The *rules* are pre-existing and cited above; the *ownership*, the
`TicketFact` shape, the `BILLING_CATEGORY` identifier and the equivalence test are authored here.
It is recorded as authored rather than derived because nothing frozen forced a second
implementation of the open-ness predicate to exist — the freeze did.

---

### 0.4.3 D-M5-B3 — production ownership of `derive_and_persist()`: **AUTHORED**

**The requirement as it stood.** M4's *Change* says links "are derived inside an assessment run".
No milestone's *Change* list owns that call, and the audit confirmed **zero production callers**
of `derive_and_persist`, `documents_for` or `with_contract_documents` anywhere in `app/` or
`scripts/`. `documents_for()` reads persisted rows and never derives (`app/evidence/documents.py:86`),
and §0.3.6 fixes "zero contract links → `()`, not an error" — so a run that never derived would
hand M5 an **empty S14 that is indistinguishable from a customer with no contract**.

**Evidence.**

1. `derive_links(session, scope, *, config)` (`app/evidence/linker.py:107`) takes **no customer
   argument**: it derives over the whole snapshot. Derivation is therefore naturally **per scope,
   once per run** — not per customer. This is read off the signature, not chosen.
2. `persist_links` uses `on_conflict_do_nothing` against the §0.3.4 constraint, so a second
   identical derivation inserts **0** rows and raises nothing. Idempotency already exists.
3. No M4 module commits, rolls back, begins or closes (pinned by
   `tests/unit/test_m4_boundary.py`). The **caller owns the transaction**, as every Layer 1
   repository does.
4. **M5's *Non-goals* name persistence.** M5 therefore may not call `derive_and_persist` itself.
5. The first milestone that owns an assessment run and may write is **M7** (`risk_assessments`
   and the second additive migration). M8 exposes it over HTTP; M9 drives it from
   `make verify-vs01`.

**Decision.**

> **The production call to `derive_and_persist()` belongs to the assessment run, which is
> M7's. M5 never derives and never writes.**
>
> **A forward amendment to M7, recorded now because M5's correctness depends on it.** M7's
> *Change* list gains `app/decisions/assessment.py` — the assessment run that orders §A6's steps.
> The order it must implement, read off the real call graph rather than assumed:
>
> ```
>   caller (M8 route, or M9's acceptance script) opens a Session and a transaction
>         ↓
>   resolve_pinned_scope(session, …)                       M1   — fails closed on a fingerprint mismatch (§A27.1b)
>         ↓
>   derive_and_persist(session, scope, config=…)           M4   — ONCE per run, per scope, before any customer is visited
>         ↓
>   for each customer in scope:
>       compute_signals(session, scope, customer, …)       M3
>       assign_band(signals, rules, floor=…)               M3
>       build_contexts(session, scope, customer, …)        M5   — reads documents_for(), calls with_contract_documents()
>       SupportRiskAnalyst / CommercialAnalyst             M5   — tuple[Position, …]
>         ↓
>   conflicts, policy, reconciliation,                     M6   — pure; one Reconciliation per customer,
>   worthiness, ordering                                         then order_reconciliations() (§0.5)
>         ↓
>   payload, hash, persistence, narrative                  M7
>         ↓
>   caller commits
> ```
>
> - **Session ownership.** The caller opens and owns it, matching every Layer 1 repository. No
>   module under `app/evidence/`, `app/analysts/` or `app/decisions/` opens, commits, rolls back
>   or closes one.
> - **Transaction boundary.** One transaction for the run. Derivation and any M7 write are in it;
>   a failure anywhere rolls the whole run back, so **no partial assessment is ever durable**
>   (§A23).
> - **Customer scope.** Derivation is **scope-wide and customer-independent** (evidence 1). A
>   single-customer assessment still derives the whole snapshot's links; that is correct, because
>   the link table is keyed by fingerprint and linker, not by the customer being assessed, and
>   because re-deriving is free (evidence 2).
> - **Idempotency.** Exactly §0.3.4's: an unchanged snapshot and linker insert **0** rows and
>   raise nothing; a changed `layer1_fingerprint` or `linker_version` **appends**. Nothing is
>   updated in place or deleted.
> - **Failure behaviour.** `UnciteableLinkError` — or any exception from derivation — **aborts
>   the run before any context is constructed**. The run does not continue with partial evidence,
>   does not retry, and does not fall back to whatever was persisted earlier. **No retry,
>   backoff, history, supersession or validity-interval semantics are introduced**, consistent
>   with §0.3.4's prohibition.
>
> **Until M7 exists, M5 is not independently runnable in production**, which is already true of
> it: no entry point reaches Layer 2 at all. M5's own tests derive links in an explicit arrange
> step, and M5's acceptance (§0.4.8) asserts `("DOC-006",)` reaches `CommercialContext`, so the
> silent-empty hazard fails loudly the moment the ordering is got wrong.

**Classification: AUTHORED.** The sequence's *shape* is §A6's and the per-scope grain and
idempotency are read off M4's committed signatures; **assigning the call to M7 and naming
`app/decisions/assessment.py` are new design choices**, made here because leaving them open is
what lets an implementer put a write inside M5's factory.

---

### 0.4.4 D-M5-B4 — M5 test and README evolution: specified **and authorised**: **AUTHORED**

§0.3.9 specified M4's test evolution without authorising it. That separation was right for M4,
which had not yet been approved. **M5's equivalent is authorised here**, in this exact form and
no wider, because each row was measured against the committed suite rather than anticipated.

The governing rule is unchanged: **extend, move or remove only the obsolete assertion. Never
weaken the surrounding test.** None of the rows below changes `app/intelligence/`,
`app/relationships/`, `app/evidence/`, `app/persistence/`, any migration, or `data/`.

| # | Test / file | Exact assertion affected | Why M5 contradicts it | Authorised evolution | What stays frozen |
|---|---|---|---|---|---|
| **T-M5-1** | `tests/unit/test_m1_boundary.py` | `LAYER2_PACKAGES = ("app/relationships/", "app/evidence/")`, used by `test_only_the_relationship_model_depends_on_the_foundation:212` to assert **every** importer of `app.intelligence` under `app/`, `scripts/`, `migrations/`, `docker/` lives in one of them | `app/analysts/` must import `Position`, `Function`, `Stance`, `ActionId`, `Evidence`, `SignalSet`, `Scope`, `MoneyValue` | **Extend the tuple to `("app/relationships/", "app/evidence/", "app/analysts/")`** — extend, never relax to a substring or a prefix check. The test's own docstring already describes this evolution: it named M2 rather than being relaxed when M2 arrived, and §0.3.9 T2 named M4 the same way | The scan itself, its four scanned directories, its `assert importers` non-vacuity guard, and the rule that an importer which is none of the three **still fails the build** |
| **T-M5-2** | `README.md` + `tests/unit/test_i2_readme.py::test_the_test_counts_the_readme_quotes_are_the_counts:247` | The per-layer counts the `Layer / Command / Tests / Needs` table quotes for `pytest tests/unit` (**4030**) and `pytest tests/integration` (**694**), and the two "`N` tests in four layers" totals (README:1162, :1277) | M5 adds unit and integration tests | **Update the two per-layer counts and both totals to the actual collected values** — the mechanism is unchanged and already recomputes them by `pytest --collect-only`. `29776e0`, `bc0525d`, `34486eb` and `65eb462` each did exactly this | That the totals must **agree with each other** and with the sum of the per-layer rows; the contract layer count; the e2e count |
| **T-M5-3** | `README.md:1380` + `test_the_lint_counts_the_readme_quotes_are_the_counts:279` | "`ruff check app/ tests/ scripts/` reports **69** findings" | M5 adds source and test files, so the count may move | **Re-quote the actually observed value.** Per §0.3.11 D-M4-B4 these are informational project-state counts, **not** M5 acceptance criteria | **No lint finding may be suppressed, and no test weakened or skipped, to preserve a number.** A *count* may move; the *gate* may not. New Ruff findings of M5's own are a defect to fix, never a number to re-quote |
| **T-M5-4** | `README.md:1381` + the same test | "`mypy app/` reports **9** errors" | as T-M5-3 | as T-M5-3 | as T-M5-3. The test already **skips** when the installed tool version differs from the quoted one, so a version bump is not a failure and is not a licence either |

**Measured, so that nothing is left implied.** The audit scanned the committed suite for every
other assertion M5 could contradict and found **none**:

- **No test asserts `app/analysts/` does not exist.** The M4 analogue (§0.3.9 T1,
  `test_app_evidence_does_not_exist`) has no M5 counterpart. Nothing to remove.
- `tests/unit/test_m2_boundary.py:30` already lists `app.analysts` in `FORBIDDEN_PACKAGES` —
  in the **forbidding** direction, `app/relationships/` must not import it. **This is correct
  and must not change.** M5 makes M2 import nothing.
- **No whitelist governs who may import `app.evidence`.** `test_m4_boundary.py` forbids
  `app/persistence/`, `app/relationships/` and the M3 modules from importing it and constrains
  nothing else, so `app/analysts/` → `app/evidence/` trips no committed test (see §0.4.5).
- `test_no_m4_module_invokes_the_s14_composition:343` scans **only** `EVIDENCE_DIR`, so M5
  invoking `with_contract_documents` from `app/analysts/` is already outside its scope, exactly
  as §0.3.6 B intended. **It must not be touched.**
- `test_m3_still_states_no_contract_document:366` and
  `test_the_signal_set_m3_builds_states_no_contract_document` pin `contract_document_ids=()` in
  `signals.py` from both sides. **M5 populates S14 by composition at context-construction time
  and never by editing M3, so both assertions stand unchanged.**
- `test_the_architecture_section_carries_a_diagram_and_the_repository_layout:100` checks only
  top-level directories (`app/`, `config/`, `data/`, `migrations/`, `scripts/`, `tests/`). M4
  needed no layout edit and **M5 needs none**.
- `tests/integration/test_h3_migrations.py` is untouched: **M5 adds no table and no migration.**

**Anything not in T-M5-1…T-M5-4 is not authorised.** An implementer who finds a sixth
contradiction must report it and stop, exactly as §0.3.8 requires of a measured link set.

---

### 0.4.5 D-M5-B5 — the M5 dependency boundary: **AUTHORED**

**The package is `app/analysts/`**, as M5's *Change* list and §A22's no-executor row both already
name. M5 introduces no other package; `app/decisions/` is M6's and M7's.

**The DAG, extended by one node.** Verified against the committed import graph, which contains no
reverse edge today:

```
app.intelligence (M1)  ←  app.relationships (M2)  ←  app.evidence (M4)
         ↑                        ↑                        ↑
         └────────────────────────┴────────────────────────┴──  app.analysts (M5)
```

`app/analysts/` is a **leaf**: it is the top of the graph and nothing imports it. Adding it
creates no cycle and reverses no edge.

| Direction | Status | Enforced by |
|---|---|---|
| `app.analysts` → `app.intelligence` (M1 contract, scope, money, timeutil, config) | **authorised** | T-M5-1 extends the importer whitelist to admit it |
| `app.analysts` → `app.intelligence.signals` / `.bands` (M3) | **authorised**, submodule-explicit | §0.2.3's import-initialiser rule: `from app.intelligence.signals import compute_signals`, never via `app.intelligence`'s `__init__`, which must continue not to re-export the M3 modules |
| `app.analysts` → `app.relationships` (M2 `neighbourhood`) | **authorised** | membership is answered once, by M2 (§0.2.3), and M5 resolves nothing itself |
| **`app.analysts` → `app.evidence` (M4)** | **explicitly authorised** | Required by §0.3.6 B: `documents_for()` and `with_contract_documents()` are M5's to call. **No M4 boundary test is modified to permit it** — none forbids it (§0.4.4), because M4's scans constrain `app/persistence/`, `app/relationships/` and the M3 modules only |
| `app.analysts` → `app.persistence.models` (Layer 1 ORM, for D-M5-B2's one ticket read) | **authorised for the context factory only** | §0.4.7; and the analyst modules themselves are forbidden it, below |
| `app.analysts` → `app.decisions` (M6/M7) | **forbidden** | would reverse the DAG |
| `app.relationships` / `app.evidence` / `app.intelligence` → `app.analysts` | **forbidden** | `test_m2_boundary.py:30` already forbids it for M2; M5 adds the mirrored assertions for M1, M3 and M4 |
| `app.analysts` → any outbound HTTP/SMTP/source-write | **forbidden** | §A22; the transitive no-executor test is **M8's** (§A22 lists all five packages), and M5 adds only the `FORBIDDEN_INFRASTRUCTURE` scan over its own package |

**Two M5-side boundary assertions, mirroring M1's and M2's rather than inventing a style.**

- **No module under `app/analysts/` reads a clock or a random source** — the M1
  `datetime.now` / `date.today` / `utcnow` scan and `FORBIDDEN_RANDOM_MODULES`, extended to this
  package. Determinism stays structural.
- **No module under `app/analysts/` writes** — the M1 `FORBIDDEN_WRITES` scan (`commit`,
  `rollback`, `add`, `add_all`, `flush`, `delete`, `merge`, `begin`, `begin_nested`, `close`,
  `bulk_save_objects`), extended to this package. This is what makes D-M5-B3's "M5 never
  persists" executable rather than promised.

**And the one §A14 already names, stated as an import rule:** `support_risk.py` and
`commercial.py` import **neither `Session` nor any ORM model**, directly or transitively through
an `app.analysts` sibling. `context.py` is the only module in the package permitted either.

---

### 0.4.6 D-M5-B6 — Support's visibility of the contested object: **AUTHORED**

**This blocker was not in the takeover audit's list. It is the most serious of the six**, because
the slice's central conflict was structurally inexpressible.

**The contradiction, stated exactly.**

1. §A16 assigns `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` to **Support**, with the precondition
   "`S8 >= 1` **and an active `negotiation` deal**".
2. §A15 requires the conflict to be "over the same object identity (**here `DEAL-001`**)", and
   `Conflict.__post_init__` requires every position's `object_ref` to equal the conflict's.
3. `Position.object_ref` is a **required, non-empty** string in the frozen M1 contract.
4. §A14 forbids `SupportContext` "**any deal, project or monetary field**", and M5's *Tests*
   assert a context-purity test enforcing it.
5. M5's *Acceptance* requires Support to propose exactly this action for CUST-007.

Support must therefore propose an action it cannot evaluate, on an object it cannot name. **A
literal reading of §A14 makes M5's own acceptance criterion unsatisfiable.**

**Two resolutions were considered, and one is rejected on the record.**

> **Rejected — use `S15 deal_under_pressure` as a proxy.** S15 is a boolean already on the frozen
> `SignalSet`, and §A10 labels it "conflict input", so it is the obvious shortcut. It is wrong on
> two counts. **It is not the same predicate**: S15 is "an active `negotiation` deal exists
> **while `S5` is true**", whereas §A16's precondition is `S8 >= 1` and an active `negotiation`
> deal, with no `S5` term — so a customer with breaches and a negotiation deal but no escalation
> state would be treated differently by the two rules. On the committed dataset they happen to
> agree, because **no customer other than CUST-007 has both `S8 >= 1` and an active
> `negotiation` deal** (CUST-025 has no deal; CUST-036's DEAL-037 is `qualification`) — which
> makes the divergence invisible to every test and is precisely why it must not be adopted. And
> **a boolean cannot supply `object_ref`**, so it does not solve the naming half at all.

**Decision.**

> **`SupportContext` carries the contested object's identity, and nothing else about it.**
>
> ```
> SupportContext
>     …
>     contested_deal  EntityRef | None    # identity only
> ```
>
> - It is populated by the **context factory** — which is the assembler and sees everything, not
>   an analyst — from the same `SignalSet.active_deals` that `CommercialContext` consumes,
>   filtered to `stage == NEGOTIATION_STAGE`. M5 reuses M3's existing
>   `NEGOTIATION_STAGE = "negotiation"` constant rather than redeclaring the literal.
> - Where more than one active `negotiation` deal exists, `contested_deal` holds the one with
>   the **lexicographically smallest `source_id`**, and §0.4.1's "one per qualifying deal"
>   multiplicity for `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` is bounded to that single deal.
>   No customer in the demo dataset has two, so this tiebreak is exercised only by a fixture and
>   is recorded as a **known limitation** (§A29) rather than a behaviour the dataset proves.
> - Support then evaluates §A16's precondition **literally** — `S8 >= 1 and contested_deal is not
>   None` — with no proxy, no `S5` term and no divergence from the written rule.
>
> **The field-scope rule of §A14 is restated precisely, because "any deal field" was too coarse
> to implement.** *Field scope* is what a context may hold; it is unrelated to the *functional*
> purity of `build_contexts()`, which §0.4.7 answers separately and in the negative.
> `SupportContext` must carry:
>
> - **no** `DealSignal`, `MoneyValue` or `Decimal` field;
> - **no** deal or project *attribute* — no amount, currency, stage, probability, close date,
>   deal count or project count;
> - **no** `exposure_by_currency`, and **no** S11, S12, S13 or S15;
> - it **may** carry `contested_deal: EntityRef | None` — an `(entity_type, source_id)` pair and
>   nothing more — and `has_active_deal: bool` (§0.4.9 D-M5-B9), a boolean that carries no
>   amount, currency, stage, probability, identity or count, not even *how many*.
>
> **The complete field list is §0.4.9 D-M5-B7**, which also settles what carries S1–S10:
> `SupportContext` holds `SupportSignals`, **never a `SignalSet`**.
>
> **Why identity is not a field-scope violation.** §A14's column exists to stop Support *reasoning
> commercially* — the v2 defect 6 it answers is "any module holding a session can read any
> table". An `EntityRef("deals", "DEAL-001")` supports no commercial reasoning whatever: exposure,
> ranking, worthiness and every §A15 ordering term need attributes the context does not have, and
> §A15 already forbids money as a sort key. Knowing *that there is a contested deal, and what to
> call it* is the minimum §A15 requires of any participant in a conflict, and it is strictly less
> than §A10 already grants Support through S15. **The context field-scope test is written against
> the list above**, so it is enforced by field inspection and not by the word "any". §0.4.9
> D-M5-B7 tightens it to reject a `SignalSet` field, which this earlier wording would have
> admitted.
>
> `CommercialContext` is unchanged by this decision and keeps S11–S15, deals, projects and
> contract documents.

**Classification: AUTHORED**, and recorded as the resolution of a contradiction between two
Part A sections rather than as a new capability. §A14 gains the precise list; §A16 gains the
`Object` column of §0.4.1; no frozen type changes, and `Position` is **not** modified.

---

### 0.4.7 M5 context factory — ownership, session and purity

Resolved against the repository's existing conventions; no second transaction abstraction is
introduced.

| Question | Answer |
|---|---|
| Who creates the context? | `build_contexts()` in `app/analysts/context.py` — **the one factory**, and the only module in `app/analysts/` that may import `Session` or an ORM model |
| Who owns the `Session`? | **The caller**, exactly as every Layer 1 repository and both Layer 2 packages already require. The factory **receives** a session and never creates one |
| Does the factory open or close anything? | **No.** Pinned by the `FORBIDDEN_WRITES` scan of §0.4.5, which includes `begin`, `begin_nested` and `close` |
| Does it mutate persistence? | **No.** It reads. Derivation is M7's (§0.4.3), and M5's *Non-goals* name persistence |
| Is it **functionally** pure? | **No, and it does not claim to be** — it performs four database reads. It is *deterministic*, *side-effect-free* and *read-only*: same database state, same scope, same output; no clock, no randomness, no write, no log. Determinism and purity are independent properties, exactly as §0.3.6 notes for ordering. This is a different question from the *field-scope* rule of §0.4.6, which governs what a context may hold; `support_signals()` and `with_contract_documents()` **are** functionally pure, the factory around them is not |
| Signature | `build_contexts(session, scope, customer_source_id, *, config=None) -> AnalystContexts` — the `config` keyword defaulting to `default_risk_rules()`, matching `compute_signals` and `derive_links` |
| What it does, in order | 1. `compute_signals` and `assign_band` (M3). 2. `documents_for(session, scope, customer_source_id)` (M4). 3. `with_contract_documents(signals, links)` (M4) — **this is the production invocation §0.3.6 B assigned to M5**; its populated `SignalSet` goes to `CommercialContext`. 4. `policy_documents(session, scope)` (M2) for `SupportContext`. 5. The D-M5-B2 ticket derivation. 6. `support_signals(signals)` — the S1–S10 projection (§0.4.9 D-M5-B7); `has_active_deal` and `contested_deal` from `signals.active_deals`. 7. Construct both frozen context dataclasses (§0.4.9 D-M5-B7 lists every field) |
| What it must not do | Call `derive_and_persist` (§0.4.3); construct a `DerivedLink` or a `LinkedDocument` (M4 owns both, and `test_m4_boundary.py` pins the single place each is built); re-resolve membership (§0.2.3); edit `app/intelligence/signals.py` to populate S14 |

**The analysts receive a context and nothing else.** `SupportRiskAnalyst(context) ->
tuple[Position, ...]` and `CommercialAnalyst(context) -> tuple[Position, ...]`. Scope is a
property of construction, and `support_risk.py` and `commercial.py` import neither `Session` nor
any ORM model (§0.4.5).

---

### 0.4.8 M5 scope and acceptance

#### M5 IN-SCOPE

1. `app/analysts/context.py` — `SupportContext`, `CommercialContext`, `SupportSignals`,
   `TicketFact`, `AnalystContexts`, `BILLING_CATEGORY`, `support_signals()` and
   `build_contexts()`. Every field of every one of them is listed in §0.4.9 D-M5-B7; the
   factory's contract is §0.4.7.
2. The D-M5-B2 ticket derivation and its equivalence test.
3. The **production invocation** of `documents_for()` and `with_contract_documents()`
   (§0.3.6 B), populating S14 on `CommercialContext`.
4. `app/analysts/base.py` — the shared analyst abstraction and the catalogue-precondition
   evaluation of §A16.
5. `app/analysts/support_risk.py` and `app/analysts/commercial.py`, each returning
   `tuple[Position, ...]` per §0.4.1.
6. The `has_active_deal` and `contested_deal` seams of §0.4.6 and §0.4.9 D-M5-B9, which let
   Support evaluate both of §A16's commercial preconditions literally.
7. The boundary assertions of §0.4.5 and the test/README evolution of §0.4.4.

#### M5 OUT-OF-SCOPE

Conflict detection, policy loading, reconciliation, dissent, `conflict_policy.yaml`,
`action_catalogue.yaml`, §A15's worthiness and ordering (**M6** — corrected 2026-09-24 by §0.5.1
D-M6-B1; this line first read "(M7)" for the last two) · `risk_assessments`, `risk_positions`,
`risk_briefs`, payload hashing, narrative rendering, templates, `template_version`, §A22's evidence
length cap, persisting `executive_worthy`, `app/decisions/assessment.py`, the second migration
(**M7**) · routes, approval, `brief_decisions`, the transitive no-executor test
(**M8**) · `make verify-vs01`, the e2e scenario, §A26 fixtures, the mutation audit (**M9**) ·
**any** persistence, migration, table or configuration key · any model, embedding, vector store,
semantic retrieval or `TOPIC` mechanism (§0.3.1, §A13, §A31) · any history, supersession or
validity-interval machinery (§0.3.4) · any change to M1, M2, M3, M4, Layer 1 or `data/demo/` ·
settling §0.3.7 rows 9, 10 or 11 · any refactoring not named in §0.4.4.

#### M5 acceptance criteria — expected outcomes, stated before the tests are written

Binary, and measured at `ACCEPTANCE_AS_OF = 2026-09-18` over the clean full-dataset path of §A28
unless a row says otherwise.

| # | Criterion | Expected outcome |
|---|---|---|
| 1 | **Action resolution** | CUST-007 yields **exactly six** positions, matching §0.4.1's table row for row — function, action, `object_ref` and stance — in `(function, object_ref, proposed_action)` order |
| 2 | **Multiple satisfied actions** | All five Support entries are emitted; **none is dropped, ranked or merged**. Exactly one SUPPORT and one SALES position carry `object_ref = "DEAL-001"`, so M6 will detect exactly one conflict |
| 3 | **Support ticket condition** | `REVIEW_INVOICE_DISPUTE` is emitted with `object_ref = "TKT-079"` — the one open `billing` ticket. A fixture ticket with category `"Billing"`, `"BILLING"`, `" billing"` or `None` yields **no** such position |
| 4 | **Ticket breach reporting** | The D-M5-B2 equivalence table holds for **every** customer at both `2026-09-18` and `2026-08-27`. TKT-079 has `breaches_sla = True` yet is absent from S8, because S8 counts open **high**-priority breaches; a NULL-priority fixture ticket has `breaches_sla = False` |
| 5 | **Contract-document integration** | `CommercialContext`'s `SignalSet.contract_document_ids == ("DOC-006",)` — reached through `documents_for()` and `with_contract_documents()` in the factory, with **both** DOC-006 evidence links still returned by `documents_for()` |
| 6 | **Empty evidence** | A customer with links but no `contract` document yields `()` and **no error** (§0.3.6) |
| 7 | **Missing evidence** | With no links persisted at all, the factory still builds both contexts and S14 is `()`. This is the silent-empty hazard of §0.4.3, and criterion 5 is what detects it in the real ordering |
| 8 | **No qualifying tickets** | A ticketless customer yields band `NONE`, an empty `TicketFact` tuple and **no SUPPORT position at all** — not a `NO_ACTION` one (§0.4.1). It is **not** silent commercially: §A16's `ACCELERATE_DEAL_CLOSE` carries no band term, so of the 15 ticketless customers the **three** with a qualifying deal — CUST-019 (DEAL-011), CUST-042 (DEAL-005), CUST-043 (DEAL-029), each `negotiation` at 90% — emit exactly one SALES position and no conflict. The other 12 emit nothing |
| 9 | **Qualifying tickets** | CUST-025 and CUST-036 (`WATCH`) emit Support positions for the entries they satisfy and **no** `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED`, because neither has an active `negotiation` deal — the case that would have been wrong under the rejected S15 proxy of §0.4.6 |
| 10 | **Deterministic output** | Two runs in one session, and once more after reinsertion in a different physical order, give exactly equal ordered tuples of positions and identical `to_payload()` output. No clock or random source is reachable from `app/analysts/` |
| 11 | **Session and transaction behaviour** | The factory receives a session and never opens, commits, rolls back or closes one; no module under `app/analysts/` calls a `FORBIDDEN_WRITES` method; `support_risk.py` and `commercial.py` import neither `Session` nor an ORM model |
| 12 | **Production `derive_and_persist` invocation** | **No module under `app/analysts/` calls `derive_and_persist`, `derive_links` or `persist_links`** — asserted by AST scan, mirroring `test_no_m4_module_invokes_the_s14_composition` |
| 13 | **M4 → M5 handoff** | `app/evidence/`, `app/relationships/` and `app/intelligence/` are byte-identical to `65eb462`; `signals.py` still states `contract_document_ids=()`; the Layer 1 fingerprint still recomputes to `1d891b0b…`; every M4 and M3 boundary test passes **unchanged** |
| 14 | **Context field scope** | By field-**type** inspection: `SupportContext` has **no field of type `SignalSet`**, `DealSignal`, `MoneyValue` or `Decimal`, and none whose type contains one as a member or element; `SupportSignals` has **exactly** D-M5-B7's eleven fields and no other; `CommercialContext` has no `TicketFact` field or collection of them. The `SignalSet` clause is load-bearing — without it `signals: SignalSet` passes while carrying every forbidden value. Also: **every `Position` validates and carries at least one `Evidence`**, and every citation in every position resolves |
| 15 | **Multi-currency** | A two-currency fixture customer renders both in `CommercialContext`, and summing them raises (§A12) |
| 16 | **Regression** | Full suite green, `app/` coverage **100%**, secret scan **0**, migration history **one head and no new migration**, and the README counts updated per §0.4.4 to their actually observed values |

**Measured corpus-wide expectation — OBSERVED, not architecture.** Counted from `data/demo/` on
2026-09-22, and recorded so an implementer verifies rather than assumes. **Eight** customers hold
an active `negotiation` deal at probability ≥ 80 and therefore draw a SALES
`ACCELERATE_DEAL_CLOSE` position: CUST-003, CUST-007, CUST-019, CUST-031, CUST-042, CUST-043,
CUST-046, CUST-050. **Only CUST-007 also draws a SUPPORT position on the same deal**, because it
is the only customer with both `S8 >= 1` and an active `negotiation` deal — CUST-025 has no deal
and CUST-036's DEAL-037 is `qualification`. **The demo dataset therefore contains exactly one
conflict, and §A15's claim is a measured property of the data rather than an assertion.**

An implementer who measures a different set must report it rather than adjust this paragraph,
exactly as §0.3.8 requires of the link expectation.

**An implementer who measures a position set different from §0.4.1's table must report it rather
than adjust the expectation**, exactly as §0.3.8 requires of the measured link set. That table is
the acceptance criterion.

**The tooling gate of M4 applies unchanged.** M5 does not close until `pytest`, `ruff` and `mypy`
have actually been **run** and their results reported. A static argument that the suite would
pass is not evidence that it passed, and may not be recorded as one.

---

### 0.4.9 Second-pass review findings, closed 2026-09-22

A focused review of §0.4.6 and §0.4.3, run before the specification was committed, found three
defects **in §0.4 itself** — not in M1–M4. §0.4.3's M7 forward amendment and §0.4.7's purity
language were both confirmed sound and are unchanged. The three below are closed here.

| Finding | Defect | Closed by |
|---|---|---|
| 1 | §A14 says `SupportContext` contains "S1–S10", but frozen `SignalSet` is **one dataclass carrying all sixteen** signal fields, so "S1–S10" named no implementable representation | **D-M5-B7** |
| 2 | S14 appeared in neither §A14 column for `SupportContext` — neither granted nor forbidden | **D-M5-B8** |
| 3 | §A16's `SCHEDULE_EXECUTIVE_SPONSOR_CALL` was silently narrowed from `S11 > 0` to negotiation-only | **D-M5-B9** |

---

#### D-M5-B7 — the two context representations, field by field: **AUTHORED**

**Frozen source, verified.** `SignalSet` (`app/intelligence/contract.py:416–440`) is a single
frozen dataclass whose sixteen fields are S1, S2, S2b, S3, S4, S5, S6, S7, S8, S9, S10 (eleven
fields) followed by S11 `active_deals`, S12 `exposure_by_currency`, S13 `active_project_count`,
S14 `contract_document_ids` and S15 `deal_under_pressure`. `EntityRef` (`:308`) is
`(entity_type, source_id)` and nothing else. `EscalationPolicy` (`app/intelligence/config.py:56`)
is `window_days`, `ticket_threshold`, `because_documents` — no monetary member.
`app/analysts/` does not exist and no `SupportContext` or `CommercialContext` is implemented
anywhere, so nothing is being retrofitted.

**The defect.** A `SignalSet` field on `SupportContext` transitively carries `active_deals`
(`DealSignal`), `exposure_by_currency` (`MoneyValue`), `active_project_count`,
`contract_document_ids` and `deal_under_pressure` — every value §0.4.6 forbids. Worse, a purity
test that inspects field **types** would not catch it: the field's type is `SignalSet`, which is
not literally "a `DealSignal`, `MoneyValue` or `Decimal` field". The letter of §0.4.8 criterion
14 was satisfiable by an implementation that violated its whole purpose. This is the same
monolithic-frozen-type problem D-M5-B2 closed for tickets, left open for signals.

**Decision — one obvious representation, stated field by field.**

> **`SupportContext` never holds a `SignalSet`.** It holds `SupportSignals`, a new frozen
> M5-owned projection carrying **exactly** the eleven S1–S10 fields, with the **same names and
> the same types** as `SignalSet` declares them:
>
> ```
> SupportSignals                            # new, M5-owned, frozen
>     open_ticket_count           int         S1
>     open_high_priority_count    int         S2
>     high_priority_total         int         S2b
>     tickets_in_lookback         int         S3
>     max_tickets_in_14d_window   int         S4
>     policy_escalation_state     bool        S5
>     days_since_last_ticket      int | None  S6
>     sla_breach_count            int         S7
>     open_sla_breach_high_count  int         S8
>     stale_open_ticket_count     int         S9
>     dominant_ticket_category    str | None  S10
> ```
>
> Built by `support_signals(signals: SignalSet) -> SupportSignals` — **pure and total**: a
> field-by-field copy, no session, no clock, no derivation, no rounding, no defaulting. It
> **narrows by construction**: S11–S15 have no field to land in, so Support cannot receive them
> even by mistake. Same name, same type, same value — so no second definition of any signal is
> created, and nothing needs pinning to M3 the way `TicketFact` does.
>
> ```
> SupportContext                            # new, M5-owned, frozen
>     customer           EntityRef
>     signals            SupportSignals            S1–S10 only
>     band               str                       from BandAssignment.band
>     satisfied_rules    tuple[str, ...]           from BandAssignment.satisfied_rules
>     tickets            tuple[TicketFact, ...]    §0.4.2, ordered by source_id
>     sla_targets        Mapping[str, int]         RiskRulesConfig.sla_resolution_targets
>     escalation         EscalationPolicy          DOC-003's rule and the document it quotes
>     policy_documents   tuple[EntityRef, ...]     M2's policy_documents()
>     has_active_deal    bool                      S11 > 0, any stage — D-M5-B9
>     contested_deal     EntityRef | None          the active negotiation deal — D-M5-B6
> ```
>
> ```
> CommercialContext                         # new, M5-owned, frozen
>     customer           EntityRef
>     signals            SignalSet                 the FULL set, S14 populated
>     band               str
>     satisfied_rules    tuple[str, ...]
> ```
>
> ```
> AnalystContexts                           # new, M5-owned, frozen
>     support            SupportContext
>     commercial         CommercialContext
> ```
>
> `CommercialContext` needs no projection: S11, S12, S13, S14 and S15 are exactly what §A14
> grants it, and they live on the `SignalSet` that `with_contract_documents()` returns. §0.4.8
> criterion 5 already pins `CommercialContext`'s `SignalSet.contract_document_ids`, so this is
> the shape that section was already written against.

**The asymmetry is deliberate, and rests on the source material rather than on convenience.**
`CommercialContext` holds S1–S10 as a by-product of holding the `SignalSet`; `SupportContext`
holds no commercial signal at all. Three reasons, all pre-existing:

1. **§A14's two prohibitions are not the same kind.** Support may hold no deal, project or
   monetary **field** — a prohibition on values. Commercial may hold no ticket **record** — a
   prohibition on rows. `TicketFact` is a record and is absent from `CommercialContext`; S1–S10
   are aggregates and are not records.
2. **A commercial signal already depends on a ticket signal.** S15 is "an active `negotiation`
   deal exists **while `S5` is true**" (§A10). Denying Commercial every ticket aggregate would
   make its own S15 unexplainable.
3. **§A27.3 requires the brief to cite ticket counts and commercial facts together**, and both
   positions must ground their claims.

**The purity test is tightened so the letter matches the purpose.** §0.4.8 criterion 14 is
amended to assert, by field-type inspection:

- `SupportContext` has **no field of type `SignalSet`**, `DealSignal`, `MoneyValue` or `Decimal`,
  and no field whose type contains one of those as a member or element;
- `SupportSignals` has **exactly** the eleven fields above and no other;
- `CommercialContext` has **no field of type `TicketFact`** and no collection of them.

The first clause is the one that closes this finding: without it, `signals: SignalSet` passes.

**Classification: AUTHORED.** The field lists, `SupportSignals`, `support_signals()` and
`AnalystContexts` are named here so an implementer chooses nothing. No frozen type is modified,
no signal is recomputed, and no value differs from M3's.

---

#### D-M5-B8 — S14 is **not** in `SupportContext`: **AUTHORED**, on derived grounds

**Frozen source.** §A14 lists "contract documents" under `CommercialAnalyst`, never under
`SupportRiskAnalyst`. §A10 classifies S14 as "evidence only". §0.3.6 B states that
"`CommercialContext` is where S14 is consumed" and assigns M5 the production call on that basis.
`with_contract_documents()` returns a `SignalSet`, and §0.4.8 criterion 5 asserts the populated
value on `CommercialContext`.

**The defect.** §A14's *contains* column said "S1–S10" and its *cannot contain* column said
"S11, S12, S13, S15". **S14 was named in neither**, so its status for `SupportContext` was
implicit in a list §0.4.6 had declared explicit.

**Decision.**

> **S14 IS NOT in `SupportContext`.** It is consumed **only** in `CommercialContext`, through the
> populated `SignalSet` that `build_contexts()` obtains from `with_contract_documents()`
> (§0.4.7 steps 2–3).
>
> The exclusion is **structural, not merely stated**: `SupportSignals` has no
> `contract_document_ids` field, so no contract document id can reach a Support analyst by any
> route. §A14's *cannot contain* column is corrected to read **S11–S15**, which names S14
> explicitly instead of skipping it.
>
> No Support catalogue entry reads a contract document: `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA`,
> `SCHEDULE_EXECUTIVE_SPONSOR_CALL` and `ASSIGN_DEDICATED_SUPPORT_OWNER` read S5, S8 and
> `has_active_deal`; `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` reads S8 and `contested_deal`;
> `REVIEW_INVOICE_DISPUTE` reads `TicketFact` rows. Support's document evidence is DOC-003, which
> reaches it through `escalation.because_documents` and M2's `policy_documents()` — a **policy**
> document, structurally cited (§A13, §7.3), never a derived contract link.

**Classification: AUTHORED** as a statement, **DERIVED** in substance — §A14, §A10 and §0.3.6 B
all already placed S14 on the commercial side; only the explicit exclusion was missing.

---

#### D-M5-B9 — `SCHEDULE_EXECUTIVE_SPONSOR_CALL` is restored to its frozen precondition: **CORRECTION**

**Frozen semantics.** The committed plan at `65eb462` states:

> `| SCHEDULE_EXECUTIVE_SPONSOR_CALL | S5 and S11 > 0 | Support |`

S11 is `active_deal_count` (§A10) — **every** active deal, of any stage.

**The defect.** The first §0.4 pass rewrote that precondition as `S5 and contested_deal is not
None`, where `contested_deal` is the active **`negotiation`** deal. That is a narrowing, not a
restatement: a customer with `S5` true and an active `qualification` deal satisfied the frozen
rule and fails the rewritten one. On the demo dataset the change is **unobservable**, because
CUST-007 is the only customer with `S5` true and it holds a `negotiation` deal — which is exactly
the invisible-divergence property §0.4.6 uses to **reject** the S15 proxy. The section applied a
standard to one rule and breached it in another.

**Decision — restore, and supply the seam the restoration needs.**

> **`SCHEDULE_EXECUTIVE_SPONSOR_CALL`'s precondition is `S5` and `S11 > 0`, exactly as frozen.**
> No narrowing, no stage filter.
>
> Support cannot hold S11 itself — it is a deal count, which §0.4.6 forbids — so `SupportContext`
> carries one further scalar beside `contested_deal`:
>
> ```
> has_active_deal  bool    # True iff len(signals.active_deals) > 0 — any stage
> ```
>
> The factory sets it from the same `SignalSet.active_deals` it already reads for
> `contested_deal`. Support then evaluates `S5 and has_active_deal`, which is `S5 and S11 > 0`
> and nothing else.
>
> **Both Support preconditions are now literal.** `SCHEDULE_EXECUTIVE_SPONSOR_CALL` is
> `S5 and has_active_deal` ≡ frozen `S5 and S11 > 0`. `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` is
> `S8 >= 1 and contested_deal is not None` ≡ frozen `S8 >= 1 and an active negotiation deal`.
> **Neither is a proxy, and neither diverges from §A16 for any customer, on this dataset or any
> other.**
>
> **`has_active_deal` does not widen Support's scope.** It is a boolean, not a count: it carries
> no amount, no currency, no stage, no probability, no identity and not even *how many*. It is
> strictly less than `contested_deal` already grants, and every §0.4.6 argument covers it
> unchanged. The two fields together are the whole of Support's commercial visibility, and the
> §0.4.8 criterion 14 type assertions bound them.

**Measured consequence: none, on this dataset.** `S5` is true for CUST-007 alone (M3 closure,
§0.2.1), and CUST-007 holds DEAL-001, so `has_active_deal` and `contested_deal is not None` agree
there. §0.4.1's six-position table for CUST-007 is **unchanged**. The correction matters for
correctness against the written rule, not for the acceptance numbers — which is precisely why it
had to be caught by reading rather than by testing.

**Classification: CORRECTION** of a §0.4 drafting defect. It restores frozen §A16 rather than
authoring anything, and `has_active_deal` is the minimum needed to make the restoration
expressible under §0.4.6.

---

## 0.5 M6 decision specification — pre-implementation, 2026-09-24

M5 closed at `6158f81` (specification `6a8d413`, implementation `d48c970`). A readiness audit run
against `6158f81` before M6 began found M6 **blocked on specification, not on code**: Part B's
M6 block is some twenty lines, and it and §A15/§A16 left eight places where an implementer would
have had to invent architecture. This section closes all eight, and the three further points the
milestone owner asked to be frozen explicitly, in the discipline §0.4 set for M5.

> **Status of this section.** Like §0.4, this section **is an authorisation**. Each decision below
> is settled, and D-M6-B3 authorises the test and README evolution M6 requires (T-M6-1…T-M6-4)
> and nothing wider.
>
> **M1, M2, M3, M4 and M5 remain frozen.** No decision below edits `app/intelligence/`,
> `app/relationships/`, `app/evidence/`, `app/persistence/`, `app/analysts/`, any migration,
> `data/`, or any Layer 1 module. Verified at `6158f81`: the first four are byte-identical to
> `65eb462`, and `app/analysts/` to `d48c970`. M6 **adds** `app/decisions/` and two files under
> `config/intelligence/`, and reads everything else through public surfaces.

**The eight audit gaps, and what closes each.**

| # | Gap, verified against `6158f81` | Closed by |
|---|---|---|
| G1 | **Worthiness and ordering had two owners.** Part B M6 puts them in `reconciler.py` and M6's *Tests* name a worthiness truth table and amount-invariant ordering; §0.4.8's M5 OUT-OF-SCOPE, Part B M5's *Non-goals* and Part B M3's closure block assign them to M7 | D-M6-B1 |
| G2 | **`action_catalogue.yaml` was a filename only** — no schema, loader, consumer or test. Strategy §8.3 wants "preconditions in configuration", but §A16's thresholds are frozen M5 constants (`app/analysts/base.py`), re-exported by `app/analysts/__init__.py` and imported by frozen tests | D-M6-B2 |
| G3 | **Two committed tests M6 necessarily contradicts**, with no authorisation: `test_m5_boundary.py::test_the_decision_layer_does_not_exist_yet` and `test_m1_boundary.py`'s `LAYER2_PACKAGES`; plus the README counts | D-M6-B3 |
| G4 | **"The resolution cites DOC-003 and DOC-009" named no evidence shape.** `ConflictResolution.evidence` must be non-empty; `DETERMINISTIC_RULE` and `DOCUMENT_SPAN` need a `DocumentCitation` span, and no module builds one for DOC-003 | D-M6-B4 |
| G5 | **CONF-001's `when` can be false for a detected conflict** — `S8 = 1` without `S5` bands `WATCH` (`R-WATCH-001`), and a `negotiation` deal at ≥ 80% still draws the pair — and no behaviour was stated | D-M6-B5 |
| G6 | **`version` or `policy_version`?** §A15's example carries only `version: 1`; §A7, §A18 and §A24 name `policy_version` | D-M6-B6 |
| G7 | **M6's output had no named type.** The M6 → M7 seam was unshaped, and "resolved action set" could mean positions or action ids | D-M6-B7, with D-M6-B8 and D-M6-B9 |
| G8 | **The status table still recorded M5 as "PLANNED — not started"**, and this plan forbids starting a milestone before the previous one is recorded complete | The status table, this revision |

D-M6-B10 (reconciliation scope) and D-M6-B11 (the frozen contracts suffice) close no gap; they
are stated so that neither can be reopened in passing. §0.5.12 freezes the policy schema,
§0.5.13 the dependency boundary, and §0.5.14 M6's scope and acceptance criteria.

---

### 0.5.1 D-M6-B1 — ownership: **AUTHORED**, resolving a contradiction

**Evidence.** Part B M6's *Change* list says `reconciler.py (worthiness, ordering, resolved action
set, dissent)`, and its *Tests* name a worthiness truth table and ordering unchanged under amount
perturbation. Strategy §8.1 gives the `ExecutiveReconciler` "executive-worthiness, ordering,
action selection". Against that, §0.4.8's M5 OUT-OF-SCOPE and Part B M5's *Non-goals* wrote
"§A15's worthiness and ordering (**M7**)", and Part B M3's closure block said `executive_worthy`
"belongs to the milestone that persists an assessment". The sources that assign the work to
**modules and tests** — Part B M6 and strategy §8.1 — put it in M6; the three that name M7 do so
in passing, inside the scope lists of *other* milestones, and none names an M7 module or test for
either computation.

**Decision.**

> **M6 owns:** conflict detection; loading and validating `conflict_policy.yaml` and
> `action_catalogue.yaml`; policy evaluation; reconciliation — the winning action and the
> preserved dissent; the resolved position set; **worthiness**; **deterministic ordering**, of
> positions within one customer's result and of customers within a run; and the M6 result type,
> which is the M6 → M7 seam (D-M6-B7).
>
> **M7 owns neither worthiness nor ordering.** It **persists** the value M6 computed —
> `risk_assessments.executive_worthy` is `Reconciliation.worthiness.executive_worthy` — and lists
> assessments in the order `order_reconciliations()` returns. It recomputes neither.
>
> **M6 does not:** persist anything; hash a payload; render narrative or templates; apply §A22's
> evidence length cap; approve; route; open, commit, roll back or close a session; or call
> `derive_and_persist()`, which is M7's `app/decisions/assessment.py` (§0.4.3).

**§A21's two M6 events are not emitted by M6.** `vs01.conflict_detected` and
`vs01.conflict_resolved` are deferred to the assessment run, on the ground M3 already used for
its own two events (Part B M3): M6's modules are pure, and a log line is a side effect. The run
owns the transaction and receives a `Reconciliation` carrying exactly what the two events name —
the applied policy ids and the resolved actions — so nothing is lost by the deferral.

**Corrections made by this revision, so the plan has one ownership model:** §0.4.8's M5
OUT-OF-SCOPE; Part B M3's closure block; Part B M5's *Non-goals*; Part B M6 and M7; §0.4.3's
sequence line for M6; §A15 and §A16; §A21. Strategy §8.1 already agrees.

**Strategy §4.3 is superseded on one clause.** It says commercial impact "is used only to decide
executive-worthiness **and ordering among equally-banded customers**". §A15 — authoritative — says
"**Money is never a sort key**", and the strategy's own next bullet requires the ranking not to
change when amounts are perturbed. §A15 governs; the strategy document is not edited in this
revision (it carries a pre-existing uncommitted edit that is not this milestone's to commit).

---

### 0.5.2 D-M6-B2 — the action catalogue is a declarative vocabulary: **AUTHORED**

**Decision.** `config/intelligence/action_catalogue.yaml` declares **what each action is** — who
may propose it, what kind of object it contests, and which way it pulls. It declares **no
precondition and no threshold.**

```yaml
version: 1              # file format; must be 1; read by the loader only, never propagated
actions:                # exactly one entry per ActionId member — no more, no fewer
  - id: <ActionId>                                  # exact, case-sensitive
    function: SUPPORT | SALES | null               # null for NO_ACTION, and only for it
    object: customers | deals | support_tickets    # the entity type the action contests
    stance: ADVANCE | RESTRAIN | NEUTRAL
```

**The committed content is §0.4.1's table and §A16's *Proposed by* column, exactly:**

| `id` | `function` | `object` | `stance` |
|---|---|---|---|
| `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA` | `SUPPORT` | `customers` | `NEUTRAL` |
| `SCHEDULE_EXECUTIVE_SPONSOR_CALL` | `SUPPORT` | `customers` | `NEUTRAL` |
| `ASSIGN_DEDICATED_SUPPORT_OWNER` | `SUPPORT` | `customers` | `NEUTRAL` |
| `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` | `SUPPORT` | `deals` | `RESTRAIN` |
| `REVIEW_INVOICE_DISPUTE` | `SUPPORT` | `support_tickets` | `NEUTRAL` |
| `ACCELERATE_DEAL_CLOSE` | `SALES` | `deals` | `ADVANCE` |
| `NO_ACTION` | `null` | `customers` | `NEUTRAL` |

**Validation — refused at load, naming the broken entry by index and id, with nothing partially
loaded:** top-level keys exactly `{version, actions}` and `version == 1`; `actions` a non-empty
list; each entry's keys exactly `{id, function, object, stance}`; `id` an `ActionId` value; no id
twice; **every** `ActionId` member present (a missing one is named); `function` a `Function`
value or `null`, and `null` **if and only if** the id is `NO_ACTION` (§A16 leaves its *Proposed
by* empty, and §0.4.1 has neither analyst emit it); `object` one of the three entity types
§0.4.1 fixes as contested objects — a later slice that contests another type widens the set
deliberately; `stance` a `Stance` value; and a YAML mapping that repeats a key is refused
(§0.5.12 row 10).

**What it does not hold, and why.** §A16's three thresholds stay exactly where M5 put them —
`ACCELERATE_PROBABILITY_THRESHOLD`, `DEDICATED_OWNER_BREACH_THRESHOLD` and
`PAUSE_BREACH_THRESHOLD` in `app/analysts/base.py` — **neither moved nor copied.** Moving them
edits frozen M5 source and a frozen test that imports them; copying them creates two sources for
one number. M5 remains the sole authority for generating positions, and M6 consumes the
positions M5 generates. Two consequences are recorded rather than left to be discovered:

- `app/analysts/base.py`'s docstring says the thresholds live there "until M6 loads the
  catalogue". **That forward reference is superseded**: in VS-01 they live there permanently.
  The docstring is frozen M5 source and is not edited.
- Strategy §8.3's "each entry declaring its preconditions in configuration" is **deliberately not
  implemented in VS-01**. Preconditions are code, with each number a named constant, and the
  catalogue declares the vocabulary. A later slice that moves them does so as its own decision.

**How M6 uses the catalogue — two load-bearing uses, so no field is decorative:**

1. **Policy validation.** Both `between` actions of a rule must be proposable (non-`null`
   `function`), of **different** functions, and share **one** `object` type. That is what makes
   a rule's scope structural (§0.5.12).
2. **Runtime agreement.** Every position M6 reconciles must propose a proposable action whose
   catalogue `function` and `stance` equal the position's own. A disagreement raises
   `ReconciliationError` naming the position, so drift between M5's code and the catalogue fails
   the run rather than reaching a brief.

`object` cannot be checked against a position at runtime: frozen `Position.object_ref` is a bare
source id with no entity type, and M6 does not parse identifiers.

**Versioning.** The catalogue has a file-format `version` and **no semantic version of its own**:
it is covered by `policy_version` (D-M6-B6), because the policy is validated against it.

**Loader.** `load_action_catalogue(path)` and the cached `default_action_catalogue()` in
`app/decisions/policy.py`, mirroring `load_risk_rules`: a missing file is named, invalid YAML is
reported with its location, every section is checked for exactly its keys, and the result is a
complete frozen object or an exception. Errors are `DecisionConfigError`, a subclass of M1's
`IntelligenceConfigError` — a deployment fault, deliberately not an `IntelligenceError`, by M1's
own convention.

---

### 0.5.3 D-M6-B3 — M6 test and README evolution: specified **and authorised**: **AUTHORED**

The governing rule is §0.4.4's, unchanged: **extend, move or replace only the obsolete assertion,
never weaken the surrounding test**, and never delete a test merely because M6 makes it obsolete
— replace its assumption with a stronger M6-aware one.

| # | Test / file | Exact assertion affected | Why M6 contradicts it | Authorised evolution | What stays frozen |
|---|---|---|---|---|---|
| **T-M6-1** | `tests/unit/test_m1_boundary.py` | `LAYER2_PACKAGES = ("app/relationships/", "app/evidence/", "app/analysts/")`, which `test_only_the_relationship_model_depends_on_the_foundation` uses to assert every importer of `app.intelligence` lives in one of them | `app/decisions/` must import `Position`, `Conflict`, `ConflictResolution`, `Evidence`, `RecordCitation`, `RiskBand`, `EntityRef` and M1's errors | **Extend the tuple with `"app/decisions/"`**, and name T-M6-1 in the test's docstring beside T-M5-1 | The scan, its four directories, its non-vacuity guard, and the rule that an importer outside the named packages fails the build |
| **T-M6-2** | `tests/unit/test_m5_boundary.py` | `test_the_decision_layer_does_not_exist_yet` asserts `app/decisions` is absent; `test_no_module_imports_the_decision_layer`'s docstring says it "does not exist yet" | M6 creates `app/decisions/` | **Replace** the absence test with `test_the_decision_layer_exists_so_the_scan_above_is_not_moot`: the package exists and imports, and the import scan demonstrably flags a `from app.decisions import …` line. Correct the docstring's tense | `FORBIDDEN_DOWNSTREAM`, the forbidding scan and every other M5 assertion. The inventory of `app/decisions/` — exactly M6's four modules, no M7 module — is asserted in `tests/unit/test_m6_boundary.py`, where it belongs |
| **T-M6-3** | `README.md` + `tests/unit/test_i2_readme.py::test_the_test_counts_the_readme_quotes_are_the_counts` | The per-layer counts for `pytest tests/unit` and `pytest tests/integration`, and both "`N` tests in four layers" totals | M6 adds unit and integration tests | **Update to the actually collected values**, as every milestone since M1 has | That the totals agree with each other and with the per-layer sum; the contract and e2e counts |
| **T-M6-4** | `README.md` + `test_the_lint_counts_the_readme_quotes_are_the_counts` | "reports **69** findings", "reports **9** errors" | M6 adds source and test files | **Re-quote an observed value only if it moves** (§0.3.11 D-M4-B4) | **No finding suppressed, no test weakened or skipped to keep a number.** A new finding of M6's own is a defect to fix, never a number to re-quote |

**Measured, so nothing is implied — every other assertion M6 could touch, and why it stands:**

- `test_m2_boundary.py`'s `FORBIDDEN_PACKAGES` contains `app.decisions` in the **forbidding**
  direction: M2 must not import it. Correct, and unchanged.
- `test_m5_boundary.py::test_no_module_imports_the_decision_layer` forbids `app/analysts/` from
  importing `app.decisions`. Correct, unchanged, and now non-vacuous.
- `test_m5_boundary.py`'s `UPSTREAM_DIRS` omits `app/decisions/`, correctly: the decision layer is
  **downstream** of M5 and must import it.
- `test_m4_boundary.py` constrains `app/evidence/`, `app/persistence/`, `app/relationships/` and
  the M3 modules only. Nothing there governs M6.
- `test_m1_config.py` pins `risk_rules.yaml`'s path only; M6 adds no key to it.
- `test_i2_readme.py`'s layout test checks top-level directories only.
- `tests/integration/test_h3_migrations.py` is untouched: **M6 adds no table and no migration.**
- The F1 and G2 whole-`app/` scans include `app/decisions/` automatically and must pass
  **unchanged**.

**Anything not in T-M6-1…T-M6-4 is not authorised.** A fifth contradiction is reported, not fixed.

---

### 0.5.4 D-M6-B4 — resolution evidence: structural citation by document id: **AUTHORED**

**Decision.** A `ConflictResolution`'s evidence is **one `Evidence` per document the matched rule
names in `because_documents`, ascending by document id**:

```
Evidence(kind=EvidenceKind.CANONICAL_FACT,
         citation=RecordCitation(entity_type="documents", source_id=<document id>,
                                 field_name="body_text"))
```

- **The document's identity is structural** — the citation's `source_id` — exactly as §A13 and
  strategy §7.3 cite policy documents: "the rule configuration names its source document".
- **No `Session`, no Layer 1 query, no span.** `DOCUMENT_SPAN` and `DETERMINISTIC_RULE` both
  require a `DocumentCitation`, which requires reading the text to find a span; M6 holds no
  session and no module builds a DOC-003 span. `CANONICAL_FACT` over a `RecordCitation` is the
  frozen M1 shape that needs neither, and M1 validates `body_text` as a citable business field of
  `documents` at construction.
- **No `DerivedLink` or `LinkedDocument` is constructed, and `app.evidence` is not imported.** A
  policy citation is not a derived link, and M4 alone builds those.
- **Resolvability** is proved by the integration test against Layer 1 rows, as §0.4.8 criterion 14
  proved it for positions. Quoting a span of `body_text` in a brief is rendering, which is M7's.

**For CUST-007:** CONF-001's resolution cites exactly DOC-003 then DOC-009. **The dissent keeps its
own evidence.** The overruled `ACCELERATE_DEAL_CLOSE` position is preserved whole — frozen
`ConflictResolution.dissent` derives it from the conflict — with the three `deals` record
citations M5 gave it. **M6 never edits, copies or rebuilds a `Position`**, so losing cannot
discard evidence.

---

### 0.5.5 D-M6-B5 — policy failure: an unresolvable conflict raises: **AUTHORED**

**Detection is policy-driven** (§A15): a conflict exists when one `SUPPORT` and one `SALES`
position over the same `object_ref` propose a pair of actions some rule's `between` declares
incompatible. Because no two rules may share a pair (§0.5.12 row 9), **every detected conflict has
exactly one candidate rule.**

> **The candidate rule matches if and only if every one of its `when` conditions holds** for the
> customer. **A rule whose `when` fails is not a matching policy.** M6 then raises
> `UnresolvableConflictError` naming the customer, the object, both actions, the rule id and each
> failing condition with the value observed.
>
> M6 does **not**: ignore the conflict, choose a default winner, return a partial result for the
> customer, drop the conflict, average the actions, or fabricate a rule. No `Reconciliation` is
> returned for that customer. The assessment run inherits §A23 — its transaction rolls back and
> **no partial assessment is durable**.

**One further shape is unresolvable by construction:** more than one declared pair over one object.
Frozen `Conflict` admits one position per function, and VS-01's policy resolves pairs; a
three-way or cyclic conflict is VS-04's (strategy §8.2; M6 *Non-goals*). It raises the same error,
with no rule id. The shipped catalogue cannot produce it — the only cross-function pair on one
object type is `PAUSE`/`ACCELERATE` — so it is exercised by a fixture catalogue.

**Measured:** raised for **no** customer of the demo dataset at `ACCEPTANCE_AS_OF`; the only
conflict is CUST-007's, which is `CRITICAL` with `S8 = 3`. The failing shape exists only off the
dataset, and is proved by fixture. **Recorded in §A29 as a known limitation:** a real snapshot
holding that shape would abort the run until CONF-001 is extended — by design, since the
alternative is a silent default.

`UnresolvableConflictError` subclasses `ReconciliationError`, which subclasses M1's
`IntelligenceError`: a runtime decision failure, distinguishable from a configuration fault.

---

### 0.5.6 D-M6-B6 — `policy_version` is the one decision-configuration version: **AUTHORED**

`conflict_policy.yaml` carries two integers whose meanings **do not overlap**, which is exactly
`risk_rules.yaml`'s convention (`version` beside `rules_version`):

| Key | Meaning | Where it goes |
|---|---|---|
| `version` | The **file format**. Must be `1` | Read by the loader and nowhere else. Never stored, never propagated, never part of an identity |
| `policy_version` | **The** version of the decision configuration: `conflict_policy.yaml` **and** the `action_catalogue.yaml` it is validated against. A positive integer, initially `1` | `ConflictPolicy.policy_version` → `Reconciliation.policy_version`, unchanged. It is §A7's input, §A18's `risk_briefs.policy_version` and §A24's identity term |

**Bumped** whenever a change to either file can alter a detected conflict, a resolution, the
resolved position set or the dissent — the analogue of `rules_version` for the band table. No
other M6 version field exists: the catalogue carries only its format `version`. §A15's example is
corrected to carry `policy_version`.

---

### 0.5.7 D-M6-B7 — the M6 result: **AUTHORED**

All frozen, in `app/decisions/reconciler.py`, and all tuples — no list, dict or set field.

```
Worthiness                                  # M6-owned
    band                   RiskBand
    active_deal_count      int              S11 — any stage
    active_project_count   int              S13
    executive_worthy       bool             derived (property) — D-M6-B8

Reconciliation                              # M6-owned — the M6 → M7 seam, one per customer
    customer            EntityRef                          stored
    policy_version      int                                stored
    ordered_positions   tuple[Position, ...]               stored
    resolutions         tuple[ConflictResolution, ...]     stored
    worthiness          Worthiness                         stored
    ranking_key         tuple[int, int, int, str]          stored
    conflicts           tuple[Conflict, ...]               derived (property)
    dissent             tuple[Position, ...]               derived (property)
    resolved_positions  tuple[Position, ...]               derived (property)
    policy_ids          tuple[str, ...]                    derived (property)
```

**Each field, exactly.**

- **`customer`** — the customer both contexts name. `reconcile()` refuses contexts that disagree
  on customer or band (`ReconciliationError`).
- **`policy_version`** — D-M6-B6.
- **`ordered_positions`** — **every** `Position` the two M5 analysts emit for this customer, each
  exactly once and **unmodified**: M6 invokes `SupportRiskAnalyst` and `CommercialAnalyst` on the
  contexts it is given, so positions and contexts cannot come from different customers. Prevailing,
  uncontested and overruled positions are all here, in D-M6-B9's position order. It is §A17's
  "positions".
- **`resolutions`** — one `ConflictResolution` per detected conflict, ascending by `object_ref`:
  `policy_id` is the matched rule's id (CONF-001), `rationale` the rule's, `evidence` D-M6-B4's,
  and `prevailing` the conflict's position proposing `resolve_to`.
- **`worthiness`** — D-M6-B8. **`ranking_key`** — D-M6-B9.
- **`conflicts`** (derived) — `tuple(r.conflict for r in resolutions)`. Every detected conflict is
  resolved or M6 raised, so a returned result has **no unresolved-conflict state** and conflicts
  cannot disagree with resolutions. Each `Conflict`'s positions are in D-M6-B9's position order.
- **`dissent`** (derived) — every position any resolution overrules, in `ordered_positions` order.
  **Dissent is represented as the whole `Position`**, with its own evidence — the M1 frozen
  `ConflictResolution.dissent` — never as an action id.
- **`resolved_positions`** (derived) — `ordered_positions` minus `dissent`, in the same order.
  **`Position` objects, not `ActionId`s**: an action id alone loses the object, and `PAUSE…`,
  `ACCELERATE…` and `REVIEW_INVOICE_DISPUTE` are per-object. It is §A17's "resolved action set",
  and exactly §0.4.1's arithmetic: every emitted position minus those overruled. **Every
  non-conflicting position remains.** A losing position is "removed" from this derived view only:
  it stays in `ordered_positions` and in its resolution's dissent, and nothing is deleted.
- **`policy_ids`** (derived) — the ids of the rules applied, in resolution order; empty when
  nothing conflicted. In the frozen model a policy's identity is `ConflictResolution.policy_id`
  (the rule), and the policy document's identity is its `policy_version`; **no separate
  policy-document id exists, and none is invented.**

**Why four fields are derived.** M1's `ConflictResolution` derives `dissent` rather than storing it,
"so there is no field a future change can leave empty". The same discipline here means
`conflicts`, `dissent`, `resolved_positions` and `policy_ids` **cannot disagree** with the stored
fields they come from.

**Invariants** (`__post_init__`, raising M1's `ContractViolationError`): `policy_version ≥ 1`;
`ordered_positions` is in canonical order with no two positions sharing
`(function, object_ref, proposed_action)`; every resolution's conflict positions are members of
`ordered_positions`; resolutions are strictly ascending by `object_ref`; `ranking_key` names this
customer and this worthiness band.

**Serialisation.** `to_payload()` composes the frozen M1 projections (`EntityRef`, `Position`,
`Conflict`, `ConflictResolution`) with the worthiness projection, as ordered lists, so
`canonical_json` of it is byte-stable. **It is a projection, not §A17's hashed decision payload**,
which is M7's.

**`reconcile()` is pure:** a function of `(AnalystContexts, ConflictPolicy)` with no session, no
clock, no randomness and no write.

**CUST-007 at `ACCEPTANCE_AS_OF` — the expected result, stated before the tests are written.**

| Field | Value |
|---|---|
| `ordered_positions` | 6: `SALES ACCELERATE_DEAL_CLOSE DEAL-001`; `SUPPORT ASSIGN_DEDICATED_SUPPORT_OWNER CUST-007`; `SUPPORT ESCALATE_TO_ACCOUNT_OWNER_PER_SLA CUST-007`; `SUPPORT SCHEDULE_EXECUTIVE_SPONSOR_CALL CUST-007`; `SUPPORT PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED DEAL-001`; `SUPPORT REVIEW_INVOICE_DISPUTE TKT-079` |
| `conflicts` | 1, over `DEAL-001`: the SALES and SUPPORT positions on it |
| `resolutions` | CONF-001; prevailing `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED`; evidence DOC-003, DOC-009 |
| `dissent` | the `ACCELERATE_DEAL_CLOSE` position, whole, with its three `deals` citations |
| `resolved_positions` | §0.4.1 rows 1–5 — the five Support positions |
| `worthiness` | `CRITICAL`, S11 = 1, S13 = 0 → **worthy** |
| `ranking_key` | `(-3, -3, -5, "CUST-007")` |
| `policy_version`, `policy_ids` | `1`, `("CONF-001",)` |

**Public API**, exported from `app/decisions/__init__.py`: the catalogue and policy types and
loaders (`ActionCatalogue`, `CatalogueEntry`, `ConflictPolicy`, `ConflictRule`,
`ResolutionCondition`, `load_action_catalogue`, `default_action_catalogue`,
`load_conflict_policy`, `default_conflict_policy`, `DecisionConfigError`); `detect_conflicts`,
`ReconciliationError`, `UnresolvableConflictError`; and `reconcile(contexts, *, policy=None) ->
Reconciliation`, `order_reconciliations(reconciliations) -> tuple[Reconciliation, ...]`,
`Reconciliation`, `Worthiness`.

---

### 0.5.8 D-M6-B8 — worthiness: §A15's rule, verbatim: **DERIVED**

> `executive_worthy = band ≥ ELEVATED and (S11 > 0 or S13 > 0)`

Inputs, and nothing else: the contexts' band parsed to `RiskBand` (compared with M1's
`RiskBand.at_least`); **S11** = the commercial `SignalSet.active_deal_count`, any stage; **S13** =
its `active_project_count`. **Never** an amount, currency, exposure, probability, stage, S14 (a
derived document count — §0 defect 7), a timestamp, input order, or a random value.

| band | S11 > 0 | S13 > 0 | `executive_worthy` |
|---|---|---|---|
| `NONE` or `WATCH` | any | any | **no** |
| `ELEVATED` or `CRITICAL` | no | no | **no** |
| `ELEVATED` or `CRITICAL` | yes | no | **yes** |
| `ELEVATED` or `CRITICAL` | no | yes | **yes** |
| `ELEVATED` or `CRITICAL` | yes | yes | **yes** |

All sixteen band × S11 × S13 combinations are tested individually. **Measured at
`ACCEPTANCE_AS_OF`: exactly one worthy customer, CUST-007** (§A27.2). No `ELEVATED` customer exists
(§0.2.1), and 16 customers have S13 > 0 but none is band ≥ `ELEVATED`, so the `ELEVATED` rows and
the S13-only row are proved by fixture.

---

### 0.5.9 D-M6-B9 — ordering: two total orders, neither reading money: **AUTHORED** on §A15

**(a) Positions within one result** — §0.4.1's key, `(function, object_ref, proposed_action)`
ascending as strings, applied with **M5's own `order_positions`**, reused rather than restated. It
is total because M6 refuses two positions sharing the whole key (`ReconciliationError`), which M5
never emits (§0.4.1). `resolutions` are ascending by `object_ref`, unique because an object holds at
most one conflict (D-M6-B5); a `Conflict`'s positions and the `dissent` follow the position key; a
resolution's evidence is ascending by document id. **None of these is a priority.**

**(b) Customers within a run** — §A15: **band desc → S8 desc → S4 desc → customer `source_id`
asc.** The key is M3's frozen `ranking_key` (`app/intelligence/bands.py`), which already implements
exactly this order; M6 **calls it** rather than restating it, so the codebase holds one definition
of §A15's order. `order_reconciliations()` sorts ascending by `ranking_key`, refusing a customer
that appears twice and a mix of `policy_version`s (`ReconciliationError`). It is therefore total:
`source_id` is the last component and is unique.

| Two customers X and Y first differ in | X is ordered before Y when |
|---|---|
| band | X's band ranks higher |
| S8, bands equal | X's S8 is larger |
| S4, bands and S8 equal | X's S4 is larger |
| none of the above | X's `source_id` is lexicographically smaller |

**Never an ordering input:** amount, currency, exposure, probability, stage, S11, S13, S14,
worthiness, rule ids, timestamps, database row order, input order, dict or set iteration,
randomness.

**Measured at `ACCEPTANCE_AS_OF`:** CUST-007 (`CRITICAL`, 3, 5) first; then CUST-025 and CUST-036
(`WATCH`, 1, 1) — equal in every term but `source_id`, which splits them; then CUST-009 (`NONE`,
0, 2); then the thirteen `NONE` customers with S4 = 1, then the thirty-three with S4 = 0, each group
ascending by id. The dataset exercises the band, S4 and `source_id` steps; the S8 step is proved by
fixture.

**Amount invariance** (§A25 test 5): multiplying every amount by 1000 changes **nothing** M6
returns — no position, conflict, resolution, worthiness or order. Asserted on hand-built contexts
that differ only in amount, and on the database, by the same `UPDATE deals SET amount = amount *
1000` M3's test uses.

---

### 0.5.10 D-M6-B10 — scope: one object identity: **DERIVED**

M6 compares positions **only** when their `Position.object_ref` values are equal — the frozen
field, compared as strings. It never compares across objects, never within one function (three
Support positions share `CUST-007` and none is compared with another), and never across customers:
`reconcile()` takes one customer's contexts. Only **declared** pairs conflict: two functions
proposing different actions on one object that no rule names do not conflict, and both survive.

**A customer whose two functions share no object has no conflict, no dissent and no resolution**,
and its `resolved_positions` equal its `ordered_positions`. Measured: of the ten customers with any
position at `ACCEPTANCE_AS_OF`, nine are in this case — including CUST-019, CUST-042 and CUST-043,
the ticketless customers with a qualifying deal.

---

### 0.5.11 D-M6-B11 — the frozen contracts suffice: **VERIFIED**, no mismatch

Checked against `6158f81` before any code was written:

| M6 needs | Frozen surface | Sufficient? |
|---|---|---|
| A detected pair | `Conflict` — ≥ 2 positions, one per function, one object, ≥ 2 distinct actions | yes |
| A resolution that cannot lose the dissent | `ConflictResolution` — `policy_id`, `prevailing ∈ conflict`, non-empty `rationale` and `evidence`; `dissent` derived | yes |
| Positions | `Position` — M6 constructs **none**; it reconciles M5's | yes |
| Customer identity | `EntityRef` | yes |
| Band comparisons | `RiskBand.at_least`, `RiskBand.rank` | yes |
| Document evidence | `Evidence(CANONICAL_FACT, RecordCitation("documents", id, "body_text"))` | yes |
| Catalogue vocabulary | `ActionId`, `Function`, `Stance` | yes |
| §A15's order | M3's `ranking_key` and `BandAssignment` | yes |
| Position order and generation | M5's `order_positions`, `SupportRiskAnalyst`, `CommercialAnalyst`, `AnalystContexts` | yes |

**No frozen type is modified.** `Conflict`, `ConflictResolution`, `Position`, `EntityRef`,
`RiskBand`, the citation types, the Layer 1 models and M1–M5 behaviour are untouched; M6 builds M1
types only through their validating constructors.

---

### 0.5.12 The conflict policy schema — frozen

```yaml
version: 1              # file format; must be 1 — D-M6-B6
policy_version: 1       # THE decision-configuration version — D-M6-B6
conflicts:
  - id: CONF-001
    between: [ACCELERATE_DEAL_CLOSE, PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED]
    resolve_to: PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
    when:
      support_band_at_least: ELEVATED
      open_sla_breach_high_count_at_least: 1
    because_documents: [DOC-003, DOC-009]
    rationale: >
      An active support-policy escalation outranks deal acceleration on the same
      account, and the customer has explicitly linked the deal decision to
      resolution of the open tickets.
```

**Refused at load, each naming the file, the rule's index and its id:**

| # | Rule |
|---|---|
| 1 | Top-level keys exactly `{version, policy_version, conflicts}`; `version == 1`; `policy_version` an integer ≥ 1 (a boolean is not one); `conflicts` a non-empty list |
| 2 | Each rule's keys exactly `{id, between, resolve_to, when, because_documents, rationale}` — all required, none unknown |
| 3 | `id` a non-empty string, unique across rules |
| 4 | `between` a list of **exactly two distinct** `ActionId` names, each in the catalogue, **neither `NO_ACTION`** nor any other non-proposable action, of **different** functions, sharing **one** catalogue `object` type |
| 5 | `resolve_to` one of the two `between` actions |
| 6 | `when` a **non-empty** mapping whose keys are drawn from the whitelist `{support_band_at_least, open_sla_breach_high_count_at_least}`; `support_band_at_least` an exact `RiskBand` name; `open_sla_breach_high_count_at_least` an integer ≥ 0 (not a boolean) |
| 7 | `because_documents` a non-empty list of document ids — non-empty strings with no surrounding whitespace — none repeated; held ascending |
| 8 | `rationale` a non-empty string, held stripped |
| 9 | **No two rules share an unordered `between` pair**, whatever their `when` — two candidate rules for one conflict are ambiguous by construction |
| 10 | **A YAML mapping that repeats a key is refused** — an authored strengthening over `load_risk_rules`: `yaml.safe_load` keeps the last duplicate silently, so a repeated `resolve_to` would flip the winner unseen, and that is exactly §A25 test 3's lever |
| 11 | Nothing partial: the loader returns a complete `ConflictPolicy` or raises |

**`scope` is removed** from §A15's example. D-M6-B10 fixes every rule's scope to one object
identity, and the object's type is the catalogue's, which row 4 requires both actions to share —
so CONF-001 is a same-deal rule by construction. A key with one legal value configures nothing.

**`when` evaluation.** Every condition must hold: `support_band_at_least` against the contexts'
band by `RiskBand.at_least`, `open_sla_breach_high_count_at_least` against Support's S8. A failing
condition makes the rule non-matching (D-M6-B5). `when` reads nothing else — in particular no
commercial value.

**Loader.** `load_conflict_policy(path, *, catalogue)` and the cached `default_conflict_policy()`,
beside the catalogue loader in `app/decisions/policy.py`. `ConflictPolicy` holds the catalogue it
was validated against, so a policy and a catalogue cannot be mismatched at the call site.

---

### 0.5.13 The M6 dependency boundary: **AUTHORED**

```
app.intelligence (M1, M3)  ←  app.relationships (M2)  ←  app.evidence (M4)  ←  app.analysts (M5)
         ↑                                                                          ↑
         └──────────────────────────────  app.decisions (M6)  ──────────────────────┘
```

| Direction | Status | Enforced by |
|---|---|---|
| `app.decisions` → `app.intelligence` (M1 contract and errors) | **authorised** | T-M6-1 |
| `app.decisions` → `app.intelligence.bands` (M3 `ranking_key`, `BandAssignment`) | **authorised**, submodule-explicit | §0.2.3's import-initialiser rule |
| `app.decisions` → `app.analysts` (M5 contexts, analysts, `order_positions`) | **authorised** | `test_m6_boundary.py` |
| `app.decisions` → `app.evidence`, `app.relationships` | **forbidden** — M6 cites by id (D-M6-B4) and resolves no membership | `test_m6_boundary.py` |
| `app.decisions` → `app.persistence`, `app.core.database`, `sqlalchemy`, `Session` | **forbidden** — M6 is pure | `test_m6_boundary.py` |
| `app.decisions` → any M7 module (`assessment`, `payload`, `brief`, `templates`, `approval`) | **forbidden**, and none may exist | `test_m6_boundary.py` |
| M1, M2, M3, M4, M5, `app/persistence` → `app.decisions` | **forbidden** | `test_m2_boundary.py` and `test_m5_boundary.py` already; `test_m6_boundary.py` adds the rest |

And, mirroring the M1 and M5 scans over `app/decisions/`: no clock and no random source; no
logging or printing (D-M6-B1); no `FORBIDDEN_WRITES` call; no call to `derive_and_persist`,
`derive_links` or `persist_links`; no construction of `DerivedLink` or `LinkedDocument`; no
`TOPIC`, `DERIVED_TOPIC_MATCH` or `LinkBasis`; no model, vector or outbound infrastructure; and
**no read of a monetary or deal attribute** — `.amount`, `.currency`, `.exposure_by_currency`,
`.probability`, `.stage`, `.active_deals`, `.contract_document_ids`. Code is scanned with
docstrings stripped, by M4's `_code()` technique, so a module may explain what it does not do.

---

### 0.5.14 M6 scope and acceptance

#### M6 IN-SCOPE

1. `app/decisions/__init__.py`, `policy.py`, `conflicts.py`, `reconciler.py` — exactly four modules.
2. `config/intelligence/action_catalogue.yaml` (D-M6-B2) and
   `config/intelligence/conflict_policy.yaml` (§0.5.12).
3. The M6 result, worthiness and both orders (D-M6-B7…B9).
4. The boundary assertions of §0.5.13 and the test/README evolution of D-M6-B3.

#### M6 OUT-OF-SCOPE

Persistence of any kind, any table, model, repository or migration; payload hashing;
`app/decisions/assessment.py`, `payload.py`, `brief.py`, `templates/`, `approval.py` (**M7/M8**);
narrative; §A22's cap; routes and approval (**M8**); the production call to `derive_and_persist`
(**M7**, §0.4.3); §A21's log events (deferred to the run, D-M6-B1); moving or copying §A16's
thresholds (D-M6-B2); more than two functions, three-way or cyclic conflicts (**VS-04**); any
model; any change to M1–M5, Layer 1 or `data/demo/`; any test evolution beyond T-M6-1…T-M6-4.

#### M6 acceptance criteria — expected outcomes, stated before the tests are written

Binary, at `ACCEPTANCE_AS_OF = 2026-09-18` over the clean full-dataset path unless a row says
otherwise.

| # | Criterion | Expected outcome |
|---|---|---|
| 1 | **Conflict detection** | CUST-007 yields **exactly one** conflict, over `DEAL-001`, between the SALES `ACCELERATE_DEAL_CLOSE` and SUPPORT `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` positions |
| 2 | **Corpus** | Across all 50 customers exactly **one** conflict exists and **no** customer raises |
| 3 | **Winner** | CONF-001 applies; `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` prevails; `policy_ids == ("CONF-001",)` |
| 4 | **Policy liveness** | With `resolve_to` flipped, `ACCELERATE_DEAL_CLOSE` prevails and `PAUSE…` is the dissent |
| 5 | **Resolution evidence** | Exactly two `CANONICAL_FACT` `RecordCitation`s, `documents`/DOC-003 then `documents`/DOC-009, field `body_text`; each resolves to a Layer 1 row |
| 6 | **Dissent** | The `ACCELERATE_DEAL_CLOSE` position is preserved **whole**, equal to the position M5 emitted, with its own three citations |
| 7 | **Resolved set** | `resolved_positions` is §0.4.1 rows 1–5 as `Position`s; `ordered_positions` is all six; `dissent` is row 6 |
| 8 | **No shared object** | A customer with no deal, and each ticketless customer with a qualifying deal, yields no conflict, no dissent and no resolution, and `resolved_positions == ordered_positions` |
| 9 | **Scope** | Positions on different objects, and positions of one function, are never compared; an undeclared cross-function pair on one object is not a conflict |
| 10 | **Unresolvable** | A detected conflict whose rule's `when` fails raises `UnresolvableConflictError` naming the rule and each failing condition; so does a multi-way conflict; nothing is returned |
| 11 | **Policy validation** | Every refusal of §0.5.12 is proved, each naming the broken rule; a flipped policy and the committed one differ only in the winner |
| 12 | **Catalogue validation** | Every refusal of D-M6-B2 is proved; the committed catalogue equals D-M6-B2's table; a catalogue disagreeing with a position's function or stance fails the run |
| 13 | **`policy_version`** | Loaded from the policy and carried unchanged by every `Reconciliation`; `version` is carried nowhere |
| 14 | **Worthiness** | All sixteen truth-table combinations; exactly CUST-007 worthy on the corpus |
| 15 | **Ordering** | Each step of D-M6-B9's table decides on a fixture; the measured corpus order holds; duplicate customers and mixed policy versions are refused |
| 16 | **Amount invariance** | Multiplying every amount by 1000 leaves every `Reconciliation` **equal** and the order unchanged — on fixtures and on the database |
| 17 | **Determinism** | Repeated runs, permuted positions and permuted customers give equal results and byte-identical `canonical_json(to_payload())` |
| 18 | **Immutability** | Every M6 type is frozen and holds tuples only |
| 19 | **Boundary** | §0.5.13, every row, each scan with a companion proving it would catch a reintroduction |
| 20 | **Frozen M1–M5** | `app/intelligence/`, `app/relationships/`, `app/evidence/`, `app/persistence/` byte-identical to `65eb462`, `app/analysts/` to `d48c970` (structural proof by `git diff`); every M1–M5 test passes, changed only by T-M6-1 and T-M6-2; the Layer 1 fingerprint still `1d891b0b…` |
| 21 | **Regression** | Full suite green, `app/` coverage **100%**, no new ruff or mypy finding, secret scan **0**, **one** migration head and no new migration, README counts per T-M6-3 |

**The tooling gate is unchanged:** M6 does not close until `pytest`, `ruff` and `mypy` have
actually been **run** and their results reported. A measured value different from this section's
is **reported, not accommodated** (§0.3.8).

---

## Part A — Specification

### A1. Business objective

Detect, with verifiable evidence, when one customer's **service relationship is deteriorating
while commercial pressure is being applied to the same account**, reconcile the opposing
functional views into a single executive recommendation, and place that recommendation in front
of a human for approval.

### A2. Executive question

"Which customers currently require executive attention, why, and what should we do?"

Demonstration instance: *"Why is Meridian Textiles at risk, and what should the CEO do?"*

### A3. Why this slice proves the concept

The AI CEO thesis is that fragmented signals across functions get reconciled into one executive
decision a human approves. A slice where two analysts agree would only demonstrate reporting.
This slice contains a **real conflict, present in the committed data**:

| Function | Reads | Concludes | Wants |
|---|---|---|---|
| Sales | `deals` | DEAL-001 is in `negotiation` at 90% probability and active | `ACCELERATE_DEAL_CLOSE` |
| Support | `support_tickets` + DOC-003 | Policy escalation active (5 tickets in 9 days); 3 open high-priority tickets past SLA resolution target | `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` |

These are incompatible actions on the same object (DEAL-001). DOC-009 records that the customer
*"tied the Meridian Textiles - Seat Expansion decision (DEAL-001) to resolving them"*. The
reconciler must therefore choose, justify the choice against a stated policy, and **preserve the
losing position as recorded dissent**. That is executive reconciliation, achieved
deterministically, with no model.

### A4. Personas

CEO / executive sponsor (decides) · account owner EMP-007 Vikram Pillai (owns the account) ·
Head of Customer Support EMP-004 Karan Kapoor (owns the breaches).

### A5. Definitions — fixed before any code

| Term | Definition |
|---|---|
| **Risk** | Observable deterioration in the service relationship. **Not** churn probability. Ordinal band, never a percentage |
| **Risk band** | `NONE` / `WATCH` / `ELEVATED` / `CRITICAL`, assigned by a versioned decision table in configuration |
| **Policy escalation state** | Boolean. True when three or more tickets fall in **any** 14-day window whose end lies within `lookback_days` of `as_of`. Threshold and window come from DOC-003 via config |
| **SLA resolution-target breach** | Elapsed business days exceed DOC-003's target for the ticket's priority (high 1, medium 5). Resolved: created→resolved. Open: created→`as_of` |
| **Active deterioration** | Ticket velocity in the lookback window plus open high-priority tickets. Drives the band |
| **Chronic backlog** | An open ticket far past target but isolated in time. Reported separately; **never** drives the band |
| **Position** | A function's stance: `{function, stance, proposed_action, rationale, citations}` |
| **Conflict** | Two positions proposing actions declared incompatible over the same object |
| **Executive-worthy** | Band ≥ `ELEVATED` **and** a `CANONICAL_FK`-backed commercial linkage (active deal or active project) |
| **`as_of`** | The evaluation date. Acceptance pins `2026-09-18`. Ad-hoc fallback: `max(support_tickets.created_at)` in scope. **`now()` is forbidden** |
| **Scope** | One `source_system` (default `csv_demo`) plus `as_of` plus `layer1_fingerprint` |
| **`layer1_fingerprint`** | SHA-256 over the scoped canonical `(source_id, record_hash)` pairs and per-entity counts, each entity's list ordered by `source_id`. Identifies the Layer 1 snapshot an assessment was computed from. Composition, exclusions and rationale: §A5.1 |

#### A5.1 `layer1_fingerprint` — composition (decided at M0 closure, 2026-09-19)

**Composition.** SHA-256 over the UTF-8 JSON serialisation of

```
{entity_type: {"count": n, "records": [[source_id, record_hash], ...]}}
```

for the seven canonical entity types within the scope, serialised with the same discipline as
Layer 1's `record_hash` (`sort_keys=True`, `separators=(",", ":")`).

**Ordering rule.** Each `records` list is read with an explicit `ORDER BY source_id`. PostgreSQL
guarantees no row order without one, and a fingerprint computed over unordered rows is not
reproducible.

**Excluded fields.** `ingested_at`, `ingestion_run_id` and `source_updated_at` are deliberately
**not** read. They change on every ingestion, so including them would make an unchanged
re-ingestion mint a new fingerprint — destroying the very idempotency the fingerprint exists to
protect.

**What it detects.** Measured against the clean 233-row demo database:

| Change | Detected |
|---|---|
| Business-content change (a `record_hash` differs) | yes |
| `source_id` rename that reorders the sequence | yes |
| `source_id` rename that **preserves** ordinal position (`CUST-007` → `CUST-007Z`) | yes |
| `source_id` addition | yes |
| `source_id` removal | yes |

**Why `source_id` must be included.** Layer 1's `record_hash` covers business fields only and
**excludes all provenance, including `source_id`** (`app/normalization/contract.py`). A
composition over `record_hash` values and counts alone is therefore blind to every `source_id`
rename — yet `source_id` is the join key for every `SOURCE_KEY_JOIN` edge, the input to
`canonical_id`, what E1 resolves the three customer FKs against, and the token quoted in
`ID_TOKEN` document links and brief citations. A rename re-keys rows, re-resolves FKs and
invalidates citations while leaving every `record_hash` untouched.

**Layer 1 stays frozen.** This is a **Layer 2 composition over two frozen Layer 1 columns**. It
requires no change to `record_hash`, no change to any Layer 1 module, no migration and no D1
vocabulary change.

**Determinism requirement.** The fingerprint must be byte-identical across independent clean
rebuilds of the database. Verified at M0 closure: two independently built databases (different
run ids, different `ingested_at` values) both yielded
`1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00` for
`source_system='csv_demo'` over the committed demo dataset.

### A6. End-to-end workflow

```
  operator / API caller
        │  as_of, source_system, [customer]
        ▼
  1. Scope resolution      source_system + as_of + layer1_fingerprint
        ▼
  2. Relationship model    customer neighbourhood; every edge carries its basis
        ▼
  3. Signal engine         S1..S15 computed as of the scope date
        ▼
  4. Risk band             decision table  →  band + satisfied rule ids
        ▼
  5. Evidence              derived customer↔document links + structural policy citations
        ▼
  6. Analyst contexts      two disjoint, pre-built context objects (no DB session)
        ▼
  7. Positions             SupportRiskAnalyst  →  Position(support)
                           CommercialAnalyst   →  Position(sales)
        ▼
  8. Conflict detection    incompatible proposed actions over the same object?
        ▼
  9. Reconciliation        versioned conflict policy → resolved action + preserved dissent
        ▼
 10. Brief                 decision payload (hashed) + rendered narrative (a view)
        ▼
 11. Human decision        APPROVED / REJECTED bound to the payload hash
        ▼
  (no executor exists)
```

### A7. Trigger and inputs

Explicit only. `POST /api/v1/risk/assessments` or `make verify-vs01`. No scheduler, no worker.
Inputs: `as_of: date | None`, `source_system: str = "csv_demo"`,
`customer_source_id: str | None`, plus `lookback_days`, `rules_version`, `policy_version`,
`linker_version` from configuration.

### A8. Layer 1 contracts consumed (unchanged)

`customers`, `support_tickets`, `deals`, `projects`, `employees`, `documents`, read in-process
through the existing repository layer. **VS-01 requires no Layer 1 contract extension.**

### A9. Relationship model

Nodes: `Customer`, `SupportTicket`, `Deal`, `Project`, `Employee`, `Document`.

| Edge | Basis | Produced by |
|---|---|---|
| `customer_has_ticket` / `customer_has_deal` / `customer_has_project` | `CANONICAL_FK` | M2 |
| `customer_owned_by`, `ticket_assigned_to`, `employee_reports_to`, `deal_owned_by` | `SOURCE_KEY_JOIN` (within one source system) | M2 |
| `document_mentions_customer` | `DERIVED_TEXT_MATCH` (id token or exact full name) | **M4** |
| ~~`document_relates_to_topic`~~ | `DERIVED_TOPIC_MATCH` | **not modelled in VS-01** (§0.3.1) |

The first two rows are the **relationship model** (M2). The third is the **derived link** (M4),
reached through the evidence interface below and never through the relationship API. The
`EdgeBasis` vocabulary that names all four bases is M1's and is not redeclared;
**`DERIVED_TOPIC_MATCH` is reserved vocabulary that VS-01 never constructs**, because `documents`
carries no topic field and a topical overlap cites no span (§0.3.1).

**`document_owned_by` is deliberately absent, and its absence is load-bearing.**

*The Layer 1 relationship is real.* `documents.owner_source_id` is a populated carrier field
(§A9.1 row 4): every document in the corpus names an owning employee — DOC-003 is owned by
EMP-004, DOC-006 and DOC-007 by EMP-007. Layer 1 records **who authored or stewards a document**,
which is a genuine fact and stays available to any later slice that needs it.

*VS-01 M2 does not expose it* for two independent reasons, either of which alone is sufficient:

1. **No consumer, in VS-01 or in any planned slice.** None of the three queries below asks for
   a document's owner, and no later slice names document ownership either — the same test that
   excludes `project_owned_by`, and the test that `deal_owned_by` passes (§A9.1).
2. **Unacceptable evidence semantics.** Exposing it creates a Document → Employee → Customer
   path that needs **no text matching at all**, composed entirely from edges M2 would be allowed
   to emit (§A9.2).

*Why ownership can never be customer–document evidence.* An employee owns many documents and
many customers, and the two sets are unrelated. EMP-007 owns DOC-006 (*Meridian Textiles* MSA),
**DOC-007 (*Deltaforge Analytics* MSA)** and DOC-009, and is simultaneously the account owner of
**16** customers — including CUST-007 Meridian Textiles, CUST-021 Deltaforge Analytics, CUST-002
Northstar Textiles and CUST-038 Meridian Foods. Treating ownership as evidence would place
**Deltaforge's signed contract inside Meridian's executive brief**, and Meridian's MSA inside
fifteen other customers' briefs. The stewardship fact says nothing about which customer a
document concerns.

> **Rule.** Employee ownership of a document is **not** evidence that the document belongs to,
> concerns, or supports a customer. **M4's derived linking is the sole mechanism for deriving any
> Document → Customer relationship in VS-01**, because only it cites the text that asserts the
> relationship.

Removing the edge makes this true **by construction** rather than by test: M2 emits no document
edge of any kind, so no composition into a customer exists to be forbidden. Invariant B9 is
retained as defence in depth against the same mistake being reintroduced (§A9.2).

#### A9.1 Counting convention — what "3 FKs and N source-key joins" means

Earlier drafts said "five" in one place and "six" in another because they were counting different
things and neither said which. **Eight** quantities exist — five facts about Layer 1, then three
about VS-01's scope. They are **not** interchangeable, and every document must name which one it
means. The first five are read off the frozen Layer 1 code, not estimated.

| # | Quantity | Count | Definition and source of truth |
|---|---|---|---|
| 1 | **Canonical FK columns** (entity → entity) | **4** | `ForeignKey(...)` on a canonical model, excluding provenance FKs: `deals.customer_id`, `projects.customer_id`, `support_tickets.customer_id`, `employees.organization_id` |
| 2 | **Resolved canonical FKs** | **3** | Entries in `REFERENCE_RULES` (`app/ingestion/reconciliation.py`) with a non-null `source_key_field` — the three `customer_source_id` rules. These are the only `CANONICAL_FK` edges VS-01 can emit |
| 3 | **Declared-but-unresolvable FKs** | **1** | `employees.organization_id`: its rule carries `source_key_field=None`, so it is never populated. Measured: 24 employees, **0** non-null. A B1/B2 contract gap (§A29), not an edge |
| 4 | **Source-key carrier fields** | **9** | Every `*_source_id` column on a canonical model |
| 5 | **Unresolved source-key joins** | **6** | The **9** carrier fields of row 4 minus the **3** consumed by FK resolution (the `customer_source_id` columns): 9 − 3 = 6. These are strategy §2.2's six, joined by a consumer at query time within one `source_system` |

Rows 1–5 are **facts about Layer 1**. They do not move when VS-01 changes its mind: removing an
edge from M2's surface changes what VS-01 *models*, never what Layer 1 *holds*. The next three
numbers are **VS-01 scope** and must never be quoted as if they were Layer 1 facts:

| # | Quantity | Count | Definition |
|---|---|---|---|
| 6 | **Source-key edge types modelled by M2** | **4** | Row two of the edge table: the **6** of row 5 minus `project_owned_by` and `document_owned_by`. Membership is decided by the substrate rule below, **not** by whether a VS-01 query consumes the edge — if it were, this row would equal row 7 |
| 7 | **Source-key edge types a query returns** | **3** | `customer_owned_by` (neighbourhood, escalation_path), `ticket_assigned_to` and `employee_reports_to` (escalation_path). See the note on row 6 vs row 7 below |
| 8 | **Public relationship queries** | **3** | §A9's numbered list below |

So the honest full sentence, which every document now uses, is: *VS-01 answers its questions with
**3 resolved canonical FKs** and **4 of the 6 unresolved source-key joins**, through **3 public
queries**.* A bare "six source-key joins" means row 5 — Layer 1's inventory — and a bare "four"
means row 6 — VS-01's modelled subset. Neither is wrong; an unqualified number is.

**What the `document_owned_by` removal did and did not change.** It changed **row 6 only**, 5 → 4.
Rows 1–5 are unchanged, because `documents.owner_source_id` still exists and Layer 1 still holds
six unresolved source-key joins. Row 8 is unchanged: no query was added or removed. The removal is
therefore a narrowing of **M2's exposed surface**, not a change to the relationship inventory, and
any document claiming Layer 1 "has five source-key joins" is wrong regardless of VS-01's scope.

**Rows 6 and 7 differ by one, and the difference is `deal_owned_by`.** It is modelled but no
query returns it: §A9's `neighbourhood` returns the **account** owner (`customer_owned_by`), not
the deal's, and §A14's `CommercialAnalyst` context carries deals without naming their owner.

> **Decision (2026-09-20, v2.2). `deal_owned_by` stays in M2's model.** M2 is the reusable
> relationship **substrate** later slices build on, not a projection of VS-01's three queries, and
> deal ownership is a Layer 1 fact that named future slices require. **No VS-01 consumer is
> claimed for it, and none may be invented to justify it.** Its presence in the model does not
> make it analytically meaningful to VS-01, and the three public queries continue to consume only
> the relationships §A9 specifies.

The asymmetry between rows 6 and 7 is therefore intentional and must survive review. Recording it
here is what stops a later reader from "fixing" the two numbers into agreement — in either
direction, by dropping the edge or, worse, by retrofitting a query that consumes it. Its
correctness is proved directly by invariant **B10**, not through a query.

**What decides membership of row 6 — and what does not.** "A VS-01 query consumes it" is **not**
the test. An edge is modelled when it is a Layer 1 fact that a **named** slice needs, and left out
when it is speculative or unsafe:

| Edge | Modelled? | Why |
|---|---|---|
| `deal_owned_by` | **yes** | No VS-01 consumer, but two already-named future ones: VS-02's **per-owner** pipeline aggregation (strategy §10.2) and VS-03's people map, which lists *deal owner* explicitly (strategy §10.3). Safe to model, because — unlike `document_owned_by` — a deal already carries a **resolved canonical FK** to its customer, so the ownership path is never needed to associate the two |
| `project_owned_by` | no | No consumer in VS-01 **or any planned slice**: strategy §10.3's people map enumerates account owner, ticket assignees, deal owner and their managers, and omits the project owner. Nothing names it, so modelling it would be the speculation strategy §1 gives as the reason for building vertical slices instead of a horizontal graph |
| `document_owned_by` | no | Excluded on **evidence semantics** (§A9), independently of any consumer. A named consumer would not reinstate it |

Both excluded carrier fields remain in Layer 1, and either edge is a one-line addition once a
slice acquires a consumer — subject, for `document_owned_by`, to the rule above that it may never
be composed into a customer.

**`Document` is an isolated node in M2.** After the removal above, no M2 edge has a `Document` as
either source or target. `Document` remains in the node list because `policy_documents()` returns
document **nodes**, but in M2's graph it has degree zero: there is no path of any length from a
`Document` to a `Customer`, so no composition, join or traversal can manufacture one. Question A
of the §A9.2 review — *can I derive Document → Customer from any M2 edge?* — is answered **no by
construction**, not by policy. M4 connects the node.

**Exactly three public relationship queries. No generic traversal API in VS-01.**

1. `neighbourhood(customer)` → tickets, deals, projects, account owner
2. `escalation_path(customer)` → account owner → manager, plus each open ticket's assignee → manager
3. `policy_documents()` → `document_type = 'policy'`

**Derived document links are not a fourth relationship query.** `documents_for(customer)` →
derived links with basis, matched token and offsets, returned as `tuple[LinkedDocument, ...]`
(§0.3.10.2) — is an **M4 evidence interface** exported
from `app/evidence/`, outside the M2 relationship API (§A11).

The dependency runs one way: `app/evidence` reads `app/relationships`, never the reverse. That
is what makes §A11's rule — *no VS-01 signal is derived from any document link* — **structural
rather than advisory**. The M3 signal engine is built against the relationship API, so it cannot
reach a derived link at all; enforcement does not rest on a reviewer remembering the rule. It
also keeps the two kinds of knowledge from being confused at the call site: a `CANONICAL_FK`
edge is a provenance-backed fact, whereas a `DERIVED_TEXT_MATCH` link is an inference carrying
`linker_version`, its matched token and the evidence a reviewer checks it against.

#### A9.2 M2 scope boundary — what the relationship package may and may not do

Stated as rules because M2's invariants **B1–B10** assert exactly these, and because an
implementer reading only this section must not be able to arrive at document linking.

**M2 owns**

- `app/relationships/{edges,queries,model}.py`, read-only, caller-owned session
- edges over the **3 resolved canonical FKs** and the **4 modelled source-key joins** (§A9.1
  row 6), carrying exactly two bases: `CANONICAL_FK` and `SOURCE_KEY_JOIN`. One of the four,
  `deal_owned_by`, is **substrate no VS-01 query consumes** (§A9.1) and is proved by B10
- the three public queries, each with an explicit deterministic ordering

**M2 must not**

- derive a document→customer relationship by any rule, including `ID_TOKEN`, `EXACT_NAME` and
  `TOPIC`
- construct a `DerivedLink`, or invent a `linker_version`, `matched_token` or match offsets
- create, migrate or write any table — M2 adds **no** persistence and **no** Alembic revision
- import `app/evidence/`, or read `documents.body_text` for matching purposes
- expose `documents_for()` under any name
- **emit any edge whose source or target is a `Document`, other than the document *nodes*
  `policy_documents()` returns.** `document_owned_by` is excluded from the model (§A9), so M2
  has no document edge to compose from
- **retrofit a query, return field or analyst context to consume `deal_owned_by`.** It is modelled
  as substrate (§A9.1); manufacturing a VS-01 consumer for it — including to satisfy the coverage
  gate — is the specific failure the v2.2 decision forbids. B10 is how it is exercised instead

**The `policy_documents()` trap.** M2 touches the `documents` table, through
`policy_documents()`. That is deliberate — M3's band rules cite DOC-003, and M3 precedes M4 — and
it is **not** a licence to link documents to customers. `policy_documents()` takes no customer
argument, filters only on `document_type = 'policy'`, and returns the same set for every caller.
Touching a table is not the same as relating it to a customer; invariants B1 and B5 pin the
difference. This is the single most likely route by which an implementer would talk themselves
into document linking inside M2, which is why it is named here rather than left implicit.

**The ownership-composition hazard — closed by construction, then guarded anyway.** An earlier
draft modelled `document_owned_by` (Document → **Employee**) alongside `customer_owned_by`
(Customer → **Employee**). Composing them yields a Document → Employee → Customer path needing
**no text matching at all**, built only from edges M2 was allowed to emit. It is not a derived
link, so §A11 did not govern it; it is never a single Document–Customer edge, so **invariant B1
could not see it**. Measured consequence on the demo dataset: **Deltaforge's MSA (DOC-007) inside
Meridian's brief**, and Meridian's MSA inside fifteen other customers' — a breach of §A22's
customer-scope-leakage control, and worse than the substring trap §A11 guards, because no fuzzy
matching is involved.

`document_owned_by` was therefore **removed from the model** (§A9). The hazard is now closed
structurally: M2 emits no document edge, so the composition has no first hop and cannot be
written, correctly or otherwise.

**Rule (retained, and broader than the removed edge).** Shared ownership is **not** evidence of a
relationship between the owned things. An employee owns many customers, many deals and many
documents; those sets are unrelated. No M2 query may compose an ownership edge with another
ownership edge to reach a customer. **M4's derived link, which cites the text asserting the
relationship, is the sole mechanism for any Document → Customer association in VS-01.**

Invariant **B9** is kept as **defence in depth**. It no longer compensates for an intentionally
exposed edge — there is none — so its job is to fail the build if a future change reintroduces a
document edge or composes ownership into a customer. An invariant that only holds because the
dangerous edge is currently absent is exactly the one worth keeping when someone later adds it
back for a plausible-sounding reason.

**Decided — `deal_owned_by` is in M2's scope (§A9.1, rows 6 vs 7).** It is the one modelled edge
no VS-01 query returns, and it stays, as part of the reusable relationship substrate: deal
ownership is a Layer 1 commercial fact that VS-02's per-owner aggregation and VS-03's people map
already name. **No VS-01 consumer is claimed for it, and none may be invented.** Two things make
this safe. The B9 rule above forbids composing any ownership edge into a customer, so the edge
cannot become an association by another route; and a deal already carries a resolved canonical FK
to its customer, so nothing needs the ownership path to relate the two. The 100%-coverage gate is
satisfied by **B10**, which proves the edge directly rather than through a query — coverage is
earned by testing the edge, never by giving it a consumer it does not have.

**M2 has no remaining open scope question.** Its edge inventory, its three queries and its
boundary are all decided; what remains is implementation.

**"Traversal" — a word to avoid.** The relationship model *traverses* in the ordinary sense: it
follows FKs and joins source keys. It does **not** offer a generic, caller-directed traversal —
no `traverse()`, no path expression, no variable-length hop. That was v2's defect 12, and the M2
test asserting no public `traverse()` exists is what keeps it closed. When a document says M2
does traversal, it means the three fixed queries and nothing else.

### A10. Signals (deterministic, computed at `as_of`)

| # | Signal | Band input? | CUST-007 @ 2026-09-18 |
|---|---|---|---|
| S1 | `open_ticket_count` | yes | **4** |
| S2 | `open_high_priority_count` | yes | **3** (TKT-075, 076, 080) |
| S2b | `high_priority_total` | context | **4** (S2 + resolved TKT-073) |
| S3 | `tickets_in_lookback` | yes | 5 |
| S4 | `max_tickets_in_14d_window` | yes | 5 (2026-08-18 → 08-31) |
| S5 | `policy_escalation_state` | yes | **true** |
| S6 | `days_since_last_ticket` | yes | 22 |
| S7 | `sla_breach_count` | context | 5 |
| S8 | `open_sla_breach_high_count` | yes | 3 |
| S9 | `stale_open_ticket_count` | **no** — chronic backlog | 0 |
| S10 | `dominant_ticket_category` | context | `performance` (3/5) |
| S11 | `active_deal_count` + stages + probabilities | worthiness | 1 — negotiation, 90% |
| S12 | `exposure_by_currency` | **no** | `{USD: [DEAL-001, 5361.44, 90%]}` |
| S13 | `active_project_count` | worthiness | **0** |
| S14 | `contract_documents` | evidence only | DOC-006 (M4's function, M5's call — §0.3.6) |
| S15 | `deal_under_pressure` | conflict input | true — an active `negotiation` deal exists while S5 is true |

**S14 is empty until M4.** `contract_documents` requires a Document→Customer association, and
§A11 makes M4 the sole mechanism for one. M3's signal engine cannot name a document — it imports
neither `app.evidence` nor the `Document` model — so it states `contract_document_ids = ()` for
every customer, and it is filled later by the function §0.3.6 assigns to M4. The DOC-006 value
above is the specification's expectation for the completed slice, not M3's output.

**Who fills it, decided 2026-09-21 (§0.3.6) — two responsibilities, two milestones.** Earlier
drafts of this paragraph said only *"M4 populates it"*, which conflated them; they are separate.

**M4 owns the composition function.** `SignalSet` is an **M1** type, not an M3 one, and it is
frozen, so a populated copy is produced by replacement. M4 exports from `app/evidence/` the
**pure** function `with_contract_documents(signals: SignalSet, links: tuple[LinkedDocument, ...])
-> SignalSet`, which returns a **new** `SignalSet` with every other field unchanged.
`LinkedDocument` is a **new M4-owned wrapper** holding a frozen `DerivedLink` by composition
plus the document's nullable `document_type`; it does **not** extend or modify `DerivedLink`
(§0.3.6 A). The function imports `SignalSet` from `app.intelligence.contract` and **imports
nothing from M3**; `app/intelligence/signals.py` is not edited and keeps its
`contract_document_ids=()` literal.

**Selection rule:** a document is a contract document when its `document_type` is **exactly
equal** to `CONTRACT_DOCUMENT_TYPE = "contract"` — case-sensitive, no normalization, no substring
or prefix matching, no fallback. **`None` is not a contract document and contributes nothing.**
This is M2's frozen `POLICY_DOCUMENT_TYPE` pattern applied to contracts.

The function then **projects evidence grain onto document grain**: a document reached by two
evidence links contributes **one** id, deduplicated by `document_id` and never by preferring one
basis over another, and the surviving ids are ordered **lexicographically ascending by
`document_id`**. Only `document_type` and `link.source.source_id` are read; no other link
attribute is consulted. Zero contract links yield `()`. The underlying evidence links are
untouched (§0.3.6 A).

**M5 owns invoking it in production**, when it builds §A14's `CommercialContext`, which is where a
populated S14 is consumed. **M4 never calls the function** — not in the linker, not in
`documents_for()`, not in the citation builder, not in the repository, not in the migration. M5's
invocation design is deferred to M5's specification and is **not** an M4 requirement.

### A11. Derived document links

**Owned by M4, not M2 — exclusively.** M4 owns, and is the only milestone that may introduce:
document→customer derivation; the `ID_TOKEN` and `EXACT_NAME` rules; `LinkBasis` and
`LinkConfidence` in use; `linker_version`; matched tokens and offsets; the
`document_customer_links` table and its migration; and citation/evidence retrieval over documents.
They are produced by `app/evidence/linker.py`, read through `documents_for(customer)` which
`app/evidence/` exports, and they are **not** edges of the M2 relationship API (§A9, §A9.2).
Layer 1's `documents` table gains no customer reference to hold them.

**Mirror invariant (M4).** Where M2's B6 asserts `documents_for` does **not** exist in
`app/relationships/`, M4 asserts it **does** exist in `app/evidence/` and that
`app/relationships/` still does not export it. M4 additionally re-runs M2's **B9(a)**: after
`app/evidence/` exists, `app/relationships/` must *still* model no `Document` edge — so M4 cannot
satisfy its own linking requirement by quietly adding one to M2's package. The tests together
make the boundary falsifiable from both sides, so neither package can absorb the other's
responsibility.

**Sole ownership, stated without qualification.** With `document_owned_by` removed from M2 (§A9),
M4's derived link is **the only** mechanism in VS-01 by which a `Document` and a `Customer` are
ever related — there is no canonical FK, no source key, no composable ownership path, and no
other query. Every customer–document association in a brief therefore carries a basis, a matched
token and a citation into the text, or it does not exist.

| Basis | Rule | Confidence | May derive signals? | CUST-007 (measured) |
|---|---|---|---|---|
| `ID_TOKEN` | Canonical `source_id` appears as a whole token in title or body | `HIGH` | Yes | DOC-005, DOC-006, DOC-009 |
| `EXACT_NAME` | Full customer name, case-insensitive, at token boundaries | `HIGH` | Yes | **DOC-005, DOC-006, DOC-009** |
| ~~`TOPIC`~~ | — | — | — | **not implemented in VS-01 (§0.3.1)** |

**VS-01 derives links by these two mechanisms and no other.** `TOPIC` was removed on 2026-09-21:
`documents` carries no topic field, `document_type` and ticket `category` are disjoint
vocabularies, a topical overlap cites no span and so cannot satisfy strategy §7.4's grounding
guarantee, and `DerivedLink` cannot represent a non-canonical target. `LinkBasis.TOPIC` stays in
M1's frozen contract as reserved vocabulary and is never constructed. DOC-010 is linked to no
customer, which is what the data says: it names none. The full reasoning and its evidence are in
§0.3.1.

**`EXACT_NAME` includes DOC-005** — corrected 2026-09-21 (§0.3.2). DOC-005's body contains
"Meridian Textiles" at offset 174, at token boundaries. The earlier DOC-006/009 value was wrong
and is contradicted by `M0_BASELINE_REPORT.md` §12.2 and `M0_CLOSURE_REPORT.md` F7, both of which
measured DOC-005 as matching on both mechanisms.

**Grain: one link per (document, customer, basis)** — decided 2026-09-21 (§0.3.3). A pair
matching on both mechanisms produces **two** links, each with its own `matched_token`, span and
evidence. **There is no precedence between the mechanisms and none may be introduced**: they do
not compete, both results are recorded, and a consumer needing one answer per pair states its own
rule at the point of consumption rather than discarding evidence at derivation time. A single
row cannot hold both tokens — `CUST-007` and `Meridian Textiles` are different strings — so
collapsing the pair would destroy a `matched_token` this section requires every link to carry.

Substring matching is **forbidden** and pinned by a test: the dataset holds "Meridian Textiles",
"Westbrook Textiles", "Northstar Textiles" and "Evergrid Textiles" (CUST-039). §0.3.8 records the
measured collision surface in full — 26 name-token groups, including "Meridian Foods" and
"Deltaforge Health" — which is wider than this sentence's four names suggest.

**In VS-01 no signal is derived from any document link.** Every signal S1–S15 is computed
deterministically from canonical `support_tickets`, `deals` and `projects` rows; S14
(`contract_documents`) is evidence only: it is filled from `document_type = 'contract'` links by
M4's composition function, called by M5, and no signal becomes document-derived (§A10, §0.3.6).
The "may derive signals" column above is a property
reserved for later slices. This matters because DOC-005 is an `ID_TOKEN` match for CUST-007 and
states the escalation conclusion in prose, so §A25 test 4 must keep asserting exact equality of
**every signal value** — that test is what stops a later slice from quietly making the conclusion
document-derived.

The same reasoning fixes the boundary in §A9: because `documents_for()` sits outside the
relationship API that M3 is built against, "no signal is derived from a document link" is enforced
by what the signal engine can import, not only by §A25 test 4. The test remains the second line of
defence, not the first.

### A12. Money

`MoneyValue(amount: Decimal, currency: str)`. Rendering is always currency-qualified. **Summing
across currencies raises.** No total pipeline figure exists in VS-01. This type is the seam
VS-02's FX normalization plugs into without touching VS-01's call sites.

### A13. ML and retrieval

No model. No embeddings. No vector store. No prompt. Evidence selection is deterministic; policy
citations are structural, because the rule configuration names its source document (DOC-003).

### A14. Analyst contract — data in, position out

Each analyst is constructed with a **pre-built, typed context object and is never given a
database session**. Scope is therefore enforced by construction, not by convention.

| Analyst | Context contains | Context cannot contain | Emits |
|---|---|---|---|
| `SupportRiskAnalyst` | `TicketFact` rows, SLA rules, policy documents, **`SupportSignals`** (S1–S10), band and satisfied rules, `has_active_deal`, `contested_deal` (identity only) | Any `SignalSet`; any deal or project **attribute**; any monetary field; **S11–S15**, S14 included | `tuple[Position, ...]`, `function=SUPPORT` |
| `CommercialAnalyst` | Deals, projects, contract documents, S11–S15 | Any ticket record | `tuple[Position, ...]`, `function=SALES` + per-currency exposure + contract terms |

A test asserts each context dataclass has no field of a forbidden type, and that neither analyst
module imports `Session` or any ORM model.

**Amended 2026-09-22 by §0.4, which is authoritative where this table is coarser.** Three points
an implementer needs and this section did not carry:

- **Each analyst returns `tuple[Position, ...]`, not one `Position`** — one per satisfied §A16
  entry, each naming that entry's contested object. §0.4.1 fixes the objects, the stances and the
  ordering, and shows the six positions CUST-007 produces.
- **"Any deal, project or monetary field" is too coarse to implement, and §0.4.6 replaces it with
  an explicit list.** `SupportContext` carries no `DealSignal`, `MoneyValue` or `Decimal`, no deal
  or project attribute, no deal or project count and no `exposure_by_currency` — but it **does**
  carry `has_active_deal: bool` and `contested_deal: EntityRef | None`. Without an object
  identity, §A15's conflict over `DEAL-001` is structurally inexpressible, because
  `Position.object_ref` is a required field of M1's frozen contract.
- **"S1–S10" is not a `SignalSet`.** Frozen `SignalSet` carries all sixteen signal fields in one
  dataclass, so "S1–S10" named no implementable shape. **§0.4.9 D-M5-B7 settles it**:
  `SupportContext` holds `SupportSignals`, an M5-owned projection of exactly the eleven S1–S10
  fields, and **never a `SignalSet`**. `CommercialContext` holds the full populated `SignalSet`;
  the asymmetry and its three grounds are in D-M5-B7.
- **S14 is *not* in `SupportContext`** (§0.4.9 D-M5-B8). It is consumed only in
  `CommercialContext`, and `SupportSignals` has no field for it, so the exclusion is structural.
  Support's document evidence is DOC-003, reached as a **policy** document through
  `escalation.because_documents` and M2's `policy_documents()`.
- **"Tickets" means `TicketFact`**, the five-field M5-owned shape of §0.4.2, derived in the
  context factory from Layer 1 under M3's stated open-ness and breach rules and pinned to M3's
  signals by an equivalence test. M3 is neither modified nor consulted for it.

**`CommercialContext` is where S14 is consumed, so M5 owns the production call** that populates
it. M4 owns, exports and proves the composition function and never calls it; M5's context factory
invokes it. The invocation design was deferred by §0.3.6 and is **settled in §0.4.7**:
`build_contexts()` in `app/analysts/context.py` calls `documents_for()` and then
`with_contract_documents()`, receives a caller-owned session, and writes nothing. The links it
reads are derived by the assessment run, which §0.4.3 assigns to **M7**.

### A15. Conflict detection and reconciliation — the core of the slice

**Detection.** Two positions conflict when they propose actions declared incompatible in
`config/intelligence/conflict_policy.yaml` over the same object identity (here `DEAL-001`).

**Resolution.** A versioned policy entry — the committed one, in the schema §0.5.12 freezes:

```yaml
version: 1
policy_version: 1
conflicts:
  - id: CONF-001
    between: [ACCELERATE_DEAL_CLOSE, PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED]
    resolve_to: PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
    when:
      support_band_at_least: ELEVATED
      open_sla_breach_high_count_at_least: 1
    because_documents: [DOC-003, DOC-009]
    rationale: >
      An active support-policy escalation outranks deal acceleration on the same
      account, and the customer has explicitly linked the deal decision to
      resolution of the open tickets.
```

**Dissent is preserved.** The losing position is carried into the brief with its own citations
and is never averaged away or deleted. An executive can see exactly what Sales wanted and why it
did not prevail.

**Worthiness.** Band ≥ `ELEVATED` **and** (`S11 > 0` or `S13 > 0`). Derived document links never
gate worthiness.

**Ordering.** band desc → `S8` desc → `S4` desc → `source_id` asc. **Money is never a sort key.**

**Amended 2026-09-24 by §0.5, which is authoritative where this section is coarser.** The example
above was corrected in two places: it gained **`policy_version`**, the one decision-configuration
version (§0.5.6 D-M6-B6; `version` is the file format), and lost **`scope: same_deal`**, which
D-M6-B10 makes structural — both `between` actions must contest one catalogue object type
(§0.5.12). **M6 owns detection, reconciliation, worthiness and both orders** (§0.5.1 D-M6-B1);
M7 persists them. A detected conflict whose rule's `when` fails **raises** rather than resolving
(§0.5.5 D-M6-B5). The resolution cites its documents by id (§0.5.4 D-M6-B4), and the M6 result
type is §0.5.7 D-M6-B7.

### A16. Action catalogue (versioned config)

| Action | Preconditions | `object_ref` | Stance | Proposed by |
|---|---|---|---|---|
| `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA` | `S5` | customer | NEUTRAL | Support |
| `SCHEDULE_EXECUTIVE_SPONSOR_CALL` | `S5` and `S11 > 0`, read as `has_active_deal` | customer | NEUTRAL | Support |
| `ASSIGN_DEDICATED_SUPPORT_OWNER` | `S8 >= 2` | customer | NEUTRAL | Support |
| `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` | `S8 >= 1` and `contested_deal is not None` | **deal** | RESTRAIN | Support |
| `REVIEW_INVOICE_DISPUTE` | an open `billing` ticket | **ticket** | NEUTRAL | Support |
| `ACCELERATE_DEAL_CLOSE` | active deal, stage `negotiation`, probability ≥ 80 | **deal** | ADVANCE | Sales |
| `NO_ACTION` | band `NONE` | customer | NEUTRAL | — |

At the pinned `as_of`, CUST-007 triggers all six non-`NO_ACTION` entries, and the last two
conflict.

**The `object_ref` and `Stance` columns were added 2026-09-22 by §0.4.1**, which also fixes
multiplicity — one position per qualifying ticket or deal, at most one per customer-object entry
— and the order analysts return them in. They are what make §A15's conflict "over the same object
identity" expressible: `Position.object_ref` is a required field of M1's frozen contract, and
until these columns existed no rule said what to put in it.

**Two preconditions are restated, and neither is changed.** `SCHEDULE_EXECUTIVE_SPONSOR_CALL`
reads `S11 > 0` and `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` reads "an active `negotiation` deal"
— both facts §A14 forbids `SupportContext` from holding. §0.4.6 and §0.4.9 D-M5-B9 supply the two
scalars that carry them without carrying any deal attribute: `has_active_deal` (`S11 > 0`, **any
stage**) and `contested_deal` (the active `negotiation` deal, identity only). Support therefore
evaluates both original rules **literally**, with no proxy and no divergence for any customer.

> **Correction, 2026-09-22.** The first §0.4 pass rewrote `SCHEDULE_EXECUTIVE_SPONSOR_CALL` as
> `S5 and contested_deal is not None`, which silently narrowed it from *any* active deal to
> `negotiation`-stage only. That was a defect, invisible on the demo dataset because `S5` is true
> for CUST-007 alone. **§0.4.9 D-M5-B9 restores the frozen precondition.**

**`NO_ACTION` is emitted by neither analyst** — its *Proposed by* column is empty. A function with
no satisfied entry emits no position at all (§0.4.1).

**What "versioned config" means, settled 2026-09-24 by §0.5.2 D-M6-B2.**
`config/intelligence/action_catalogue.yaml` holds the `Proposed by`, `object_ref` and `Stance`
columns — the vocabulary — and **not** the *Preconditions* column. The preconditions, and the three
thresholds in them, stay M5 code with each number a named constant in `app/analysts/base.py`;
they are neither moved nor copied. The catalogue is versioned by `policy_version` (§0.5.6).

### A17. Brief — payload and view, separated

- **Decision payload (hashed, binding):** customer identity, band, satisfied rule ids, signal
  values, both positions, the detected conflict, the resolution and its policy id, the resolved
  action set, and every citation. Excludes all timestamps and `template_version`.
- **Rendered narrative (a view, not hashed):** sections for identity · risk state and why ·
  evidence · commercial context (per currency) · **conflict and how it was resolved** ·
  **recorded dissent** · policy and contract context · chronic backlog · recommended actions ·
  escalation path · limitations.

**Evidence contract:** every asserted fact carries `{kind: "record", entity, id, field}` or
`{kind: "document", document_id, start, end}`. An unresolvable citation makes the brief invalid
and the generator raises.

**Absence is stated, never omitted.** CUST-007 has no active project; the brief says so.

### A18. Persistence — new tables only, additive revision from `8bfd73b6af60`

| Table | Key columns |
|---|---|
| `document_customer_links` | `document_id` FK, `customer_id` FK, `basis`, `matched_token`, `match_start`, `match_end`, `linker_version`, `layer1_fingerprint`; **unique** `(document_id, customer_id, basis, linker_version, layer1_fingerprint)` |
| `risk_assessments` | `customer_id` FK, `as_of`, `source_system`, `layer1_fingerprint`, `rules_version`, `band`, `satisfied_rules` JSONB, `signals` JSONB, `executive_worthy`; **unique** `(customer_id, as_of, source_system, layer1_fingerprint, rules_version)` |
| `risk_positions` | `assessment_id` FK, `function`, `stance`, `proposed_action`, `rationale`, `citations` JSONB |
| `risk_briefs` | `assessment_id` FK, `policy_version`, `template_version`, `decision_payload` JSONB, `payload_hash`, `narrative` TEXT, `status` `DRAFT`; **unique** `(assessment_id, payload_hash)` |
| `brief_decisions` | `brief_id` FK, `payload_hash`, `actor`, `decision`, `note`, `decided_at`, `supersedes_id` nullable. **Append-only** |

Canonical tables are untouched; downgrade drops only these five.

**`document_customer_links` identity and re-derivation, decided 2026-09-21 (§0.3.4).** The key
holds exactly the inputs that can change a link: `basis` (the grain, §0.3.3), plus the two stamps
§0 defect 9 added. `as_of`, `rules_version` and `policy_version` are deliberately **absent** — no
link depends on the evaluation date, the band table or the conflict policy, so including them
would mint duplicate rows for identical content. Re-deriving with identical inputs is a **no-op**:
the constraint refuses the second insert and it is read instead, which is how §A27.8's "re-run
inserts nothing" is satisfied. A changed `layer1_fingerprint` or `linker_version` **appends**,
leaving earlier rows attributable to the snapshot and linker that produced them — the same
behaviour `risk_assessments` gets from its own constraint. Nothing is updated in place, nothing
is deleted by a re-derivation, and **no `computed_at`, `superseded_by`, validity interval or
history table is introduced**: the two stamps are sufficient to identify the rows any given
assessment used.

**The full column, nullability, FK, index and repository contract for
`document_customer_links` is §0.3.10.3**, grounded in Layer 1's conventions: caller-owned session,
caller-owned transaction, `on_conflict_do_nothing` against the named constraint, all columns NOT
NULL, both FKs `ondelete='CASCADE'`, no `source_system` column and no `ProvenanceMixin`.

**`linker_version` lives in `config/intelligence/risk_rules.yaml`** beside `rules_version`, as a
non-empty **string** (initial value `"1"`), because `DerivedLink` requires a string where
`rules_version` is an int. It is bumped whenever a linker change can alter which links are
derived, which token is matched, or where a span falls. A bump appends under the key above and
carries no migration or backfill. §0.3.5 records the reasoning and marks the literal value as an
authored choice.

### A19. API (additive; F1/F2 conventions reused unchanged)

| Route | Method | Notes |
|---|---|---|
| `/api/v1/risk/assessments` | POST | `201` for a new fingerprint; `200` returning the existing assessment for a repeat |
| `/api/v1/risk/assessments` | GET | filter by `as_of`, band, `executive_worthy`; limit/offset |
| `/api/v1/risk/assessments/{id}` | GET | signals, satisfied rules, positions |
| `/api/v1/risk/briefs/{id}` | GET | payload + narrative + citations |
| `/api/v1/risk/briefs/{id}/decision` | POST | body carries `actor`, `decision`, `note`, `payload_hash`; mismatch → conflict error |
| `/api/v1/risk/briefs/{id}/decisions` | GET | decision history |

### A20. UI

None. OpenAPI `/docs` only, as in Layer 1.

### A21. Observability

`log_event` + existing counters. Events: `vs01.scope_resolved` (as_of, fingerprint, resolution
path) · `vs01.signals_computed` · `vs01.band_assigned` · `vs01.links_derived` ·
`vs01.conflict_detected` (policy id) · `vs01.conflict_resolved` (winning action) ·
`vs01.brief_generated` (payload hash, citation count) · `vs01.decision_recorded`. No document
text, customer email or monetary value in any log line.

`vs01.conflict_detected` and `vs01.conflict_resolved` are emitted by the assessment run (M7) from
the `Reconciliation` M6 returns, not by M6, whose modules are pure (§0.5.1 D-M6-B1) — the same
deferral M3 made for its two events.

### A22. Security

| Concern | Control |
|---|---|
| Prompt injection | **Structurally impossible** — no model, no prompt. A named reason for the templated design |
| Document text as instruction | Rendered only as quoted, length-capped, escaped evidence with id and span. The linker never treats body text as configuration |
| Customer-scope leakage | A brief for X contains no other customer's identifiers — tested |
| Analyst scope | Enforced by construction (§A14), not by convention |
| No executor | Static test over the **transitive** import graph of `app/intelligence`, `app/relationships`, `app/evidence`, `app/analysts`, `app/decisions`: no outbound HTTP/SMTP/source-write path. The same test pins the §A9 dependency direction — `app/relationships` must not import `app/evidence`. Named exemptions use the I1 mechanism, each justified, and a test removes an exemption that is no longer needed |
| Approver identity | Recorded but **asserted, not verified** — there is no authentication. A documented prerequisite for any future executor |

### A23. Failure modes

Ticketless customer → band `NONE`, not an error (15 such customers — 11 active, plus all 4 inactive ones, which are a subset).
NULL `customer_id` FK → excluded from signals **and** reported as a `data_quality` note, never
silently dropped. Empty database → empty result. `as_of` before all data → all `NONE`, scope
reported empty. `as_of` in the future → permitted, recency decays. Invalid rules or policy config
→ refuse at load naming the broken rule; no partial assessment. NULL `body_text` → linker skips.
Stale `payload_hash` on a decision → conflict error. Concurrent identical assessments → unique
constraint makes the second a read.

**Three source-key states, two of which produce a note, and the two never collapse.** A NULL carrier key
is a *missing* relationship: the source named no customer. A non-NULL key that E1 could not
resolve within the scope is an *unresolved* one: the source named a customer Layer 1 could not
find, which is a different fault, in a different system, needing a different fix. A resolved key
is neither and produces no note. A key naming a customer of another `source_system` is
*unresolved*, not missing.

**Open: NULL `created_at` is outside this section.** A support ticket with no `created_at`
cannot be placed in time, so M3 excludes it from every signal and emits **no** note for it —
this section governs source keys, not attributes. Recorded as a specification gap in §0.2.2
rather than resolved by inventing a third state.

### A24. Determinism and idempotency

- An assessment is a pure function of (`as_of`, `source_system`, `layer1_fingerprint`,
  `rules_version`, `policy_version`, `linker_version`).
- **Date rule:** bucket by `created_at.astimezone(UTC).date()`; every window is a closed interval
  of UTC dates. Business-day arithmetic uses a fixed weekday rule with **no holiday calendar** —
  a stated limitation.
- `payload_hash` uses the same serialisation discipline as `record_hash` (sorted keys, compact
  separators, normalised `Decimal`, UTC ISO-8601) over the decision payload with timestamps and
  `template_version` excluded.
- No `now()`, no randomness, no dict-ordering or locale dependence.

### A25. Evaluation

| Layer | Proves |
|---|---|
| Unit | Every signal against hand-computed values; band table; catalogue preconditions; conflict detection and resolution; link bases; business-day and UTC-window arithmetic; hash stability |
| Contract | Analyst context purity; evidence-contract validity; API shapes from OpenAPI |
| Integration | Migration up/down; uniqueness incl. fingerprint; append-only decisions; hash conflict; idempotent re-run |
| End-to-end | assess → brief → approve over HTTP; reject path |
| Acceptance | `make verify-vs01` — named checks, each with a pass condition and a line of observed evidence, in the `verify_layer1.py` style |

**Named tests**

1. **Single-escalation.** At the pinned `as_of`, CUST-007 is the only customer with `S5` true and the only `CRITICAL` one.
2. **Conflict.** Both positions are produced; the conflict is detected; `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` wins; `ACCELERATE_DEAL_CLOSE` is preserved as dissent with its citations.
3. **Conflict-policy liveness.** Flipping `resolve_to` flips the outcome — the policy is load-bearing, not decorative.
4. **DOC-005 leave-out.** With DOC-005 removed, band, every signal, the escalation state and the resolution are byte-identical. Runs **in-process against a dedicated test database**, not the deployed stack.
5. **Amount invariance.** Multiply every deal amount by 1000 — the ranking does not change.
6. **Chronic backlog.** CUST-048 and CUST-009 do not outrank CUST-007; their stale tickets appear as backlog observations, not escalation drivers.
7. **Substring safety.** Westbrook, Northstar and Evergrid Textiles acquire no Meridian link.
8. **Citation resolution.** Every citation in every assessment and every generated brief resolves.
9. **Scope leakage.** No brief contains another customer's `source_id`, name or email.
10. **Negative cases.** The 15 ticketless customers, which include all 4 inactive ones, yield `NONE`, not worthy.
11. **Rule liveness.** Escalation threshold 3 → 6 makes CUST-007 non-escalated.
12. **Determinism.** Two runs in separate processes give identical `payload_hash`; re-run inserts nothing.
13. **Fingerprint sensitivity — content and count.** Ingesting one extra ticket changes the fingerprint and produces a **new** assessment rather than returning the stale one.
13b. **Fingerprint sensitivity — identity.** Re-ingest one record under a changed `source_id` whose sort position is unchanged (e.g. `CUST-007` → `CUST-007Z`) with byte-identical business content. The fingerprint **must** change. Test 13 alone cannot catch this, because `record_hash` excludes `source_id` (§A5.1).
14. **Multi-currency.** A customer with USD and INR deals renders both, and any attempt to sum them raises.

Mutation testing uses the project's existing ad-hoc textual harness over the signal engine, the
band table, the conflict policy and the linker.

### A26. Fixtures

No change to `data/demo/`. New fixtures only: corpus without DOC-005; deals with scaled amounts;
documents with a customer name embedded as a substring of another; a ticket with an unresolved
`customer_source_id`; a customer holding deals in two currencies; a document containing
instruction-like text, asserted to be quoted and never interpreted.

**M4 needs four more, because the committed corpus exercises none of them** (measured, §0.3.8):
a document with NULL `body_text` (all 12 have one); a document naming **two** customers (none
does); a document and a customer in a **second `source_system`**, to prove a link never crosses
one, following M2's `other_demo` precedent; and a document naming a customer id that exists in no
`customers` row.

### A27. Acceptance criteria (binary)

1. `make verify-vs01` exits 0 against a running stack whose database was built by the **clean full-dataset path** (§A28): all 233 canonical rows across all 7 entity types, evaluated at `ACCEPTANCE_AS_OF = 2026-09-18`.
1b. The computed `layer1_fingerprint` equals the value pinned in `config/intelligence/risk_rules.yaml`. A mismatch fails the run with a named message rather than producing an assessment. This is what stops a `make verify-layer1` residue — which ingests only 5 of 7 entity types and injects malformed-fixture rows into the `csv_demo` scope — from silently yielding a citation-free brief.
2. Exactly one customer is `CRITICAL` and executive-worthy: CUST-007.
3. Its brief cites, each resolvably: 5 tickets in a 9-day span; 4 open; **3 open high-priority**; 4 high-priority in total; 3 open high-priority SLA breaches; dominant category `performance`; DEAL-001 `negotiation` at 90% for **USD** 5,361.44; DOC-003's escalation rule; DOC-006's 36-month term and 90-day notice; DOC-009's linkage of the deal to ticket resolution.
4. The brief states that CUST-007 has no active project.
5. The brief contains a detected conflict, a named resolution policy, the winning action and the recorded dissent.
6. Every citation across all assessments and briefs resolves.
7. Tests 1–14 of §A25 pass.
8. Two runs give an identical `payload_hash` and insert no rows; changing the Layer 1 snapshot produces a new assessment.
9. Approval writes one decision row; a second on the same hash is refused without `supersedes_id`; rejection is recorded; nothing is executable.
10. Regression: full Layer 1 suite passes unchanged; `app/` coverage stays 100%; ruff 69; mypy 9; secret scan 0.

### A28. Demo (~5 minutes, no network, no key, no model)

> **Evaluation-state prerequisite.** The database must come from the clean full-dataset path:
> an empty database → `make migrate` → `make ingest-demo` with **no `--entities` filter** →
> 233 rows over 7 entity types, 0 rejected, `SUCCESS`; a repeat run is `NOOP`.
> **Do not use `make verify-layer1` to prepare a VS-01 evaluation database**: by design it
> ingests only the five entity types of spec Section 20 step E (no `organizations`, no
> `documents`) and then ingests the malformed fixture through the `csv_demo` connector, so its
> residue has no documents and four extra rows inside the default scope. It remains the correct,
> unchanged **Layer 1** acceptance command.

`make docker-up && make migrate && make ingest-demo` → `POST /risk/assessments {"as_of":"2026-09-18"}` →
`GET /risk/assessments?executive_worthy=true` (one row) → `GET /risk/briefs/{id}` (read the
conflict and the dissent) → open DOC-003 and DOC-009 at the cited spans and verify two citations
by hand → `POST .../decision {"decision":"REJECTED"}` → `GET .../decisions` → re-run the
assessment (identical hash, no new rows) → `pytest -k doc005_leave_out`.

### A29. Known limitations

Single source system; no cross-source entity resolution; document links derived, not
provenance-backed; **topical evidence is not modelled — a document that concerns a customer
without naming it, such as DOC-010, is linked to no customer at all (§0.3.1)**; no FX, so no
cross-currency total;
business days have no holiday calendar; **a customer with two or more active `negotiation` deals
contests only the lexicographically smallest, because `SupportContext` carries a single
`contested_deal` (§0.4.6) — no such customer exists in the demo dataset, so the tiebreak is
exercised only by a fixture**; **a detected conflict whose CONF-001 `when` fails — `S8 ≥ 1`
without `S5` bands `WATCH`, yet still draws the pause/accelerate pair on a `negotiation` deal at
≥ 80% — raises and aborts the run rather than resolving by default (§0.5.5); no such customer
exists in the demo dataset**; the band is a policy artefact, not a probability;
approver identity is asserted, not authenticated; the dataset is synthetic, 233 rows;
`employees.organization_id` remains NULL; **document stewardship is not modelled** —
`documents.owner_source_id` exists in Layer 1 but VS-01 exposes no `document_owned_by` edge
(§A9), so "which employee owns this document" is not answerable through the relationship model.

### A30. Reusable foundations this slice establishes

| Foundation | First consumer after VS-01 |
|---|---|
| `Scope` (`as_of`, `source_system`, `layer1_fingerprint`) | every slice |
| Relationship model with per-edge basis | VS-02, VS-03, VS-04, VS-05 |
| `Evidence` / `Citation` contract | every slice |
| `AnalystContext` → `Position` (data in, no session) | VS-04, VS-05 |
| `ConflictPolicy` + reconciler | VS-04 |
| `ActionCatalogue` | VS-03, VS-04 |
| `DecisionRecord` bound to a payload hash | VS-03, VS-04 |
| `MoneyValue` (currency-qualified, never summed) | VS-02 (FX plugs in here) |

### A31. Out of scope

Churn probability; forecasting; Neo4j; embeddings; any language model; multi-source aggregation;
cross-currency totals; scheduling; notification; authentication; any executor; a frontend;
changes to `data/demo/`; changes to any Layer 1 module's behaviour.

---

## Part B — Milestones M1–M9

One commit per milestone, verified before the next begins. **Frozen throughout:** D1/D2
semantics, E1 persistence and status semantics, F1/F2 route contracts, G1 logging and metric
semantics, G2 security behaviour, the H test layers, the I acceptance command, and `data/demo/`.

M0 remains a pre-flight step, not a milestone: record the baselines (suite count, coverage, ruff,
mypy, secret scan) and establish the clean evaluation database via §A28's prerequisite —
an empty database, `make migrate`, then `make ingest-demo` with no `--entities` filter.
**Completed 2026-09-19**; see `CONTEXT/M0_BASELINE_REPORT.md` and `CONTEXT/M0_CLOSURE_REPORT.md`.

---

### M1 — Foundations and contracts

**Objective.** Create the vocabulary and the invariants every later milestone depends on, so that
no later milestone can violate them by accident.

**Before.** Only Layer 1 exists. There is no notion of `as_of`, evidence or money.

**Change.**
- `app/intelligence/contract.py` — `RiskBand`, `EdgeBasis`, `LinkBasis`, `Function`, `Stance`,
  `ActionId`, `SignalSet`, `Citation`, `Evidence`, `Position`, `ConflictResolution`.
- `app/intelligence/scope.py` — `Scope(as_of, source_system, layer1_fingerprint)` and
  `resolve_scope()`, which records which path produced `as_of` and computes the fingerprint
  exactly as §A5.1 defines it: over the scoped canonical `(source_id, record_hash)` pairs and
  per-entity counts, each list read with an explicit `ORDER BY source_id`, excluding
  `ingested_at`, `ingestion_run_id` and `source_updated_at`.
- `app/intelligence/money.py` — `MoneyValue`, whose `__add__` raises across currencies.
- `app/intelligence/timeutil.py` — UTC bucketing and business-day arithmetic.
- `config/intelligence/risk_rules.yaml` — skeleton with `rules_version` and `ACCEPTANCE_AS_OF`.

**Tests.** `as_of` resolution order and the empty-database fallback; fingerprint changes when a
record's business content changes, changes when a `source_id` is renamed **without** changing its
sort position, changes on a `source_id` addition or removal, and is stable when nothing changes;
`MoneyValue` addition raises across currencies; business-day arithmetic across weekends; UTC bucketing at a 23:30 UTC timestamp;
**boundary test** that no module under `app/intelligence/` references `datetime.now`,
`date.today` or `utcnow`.

**After.** `as_of`, money and evidence exist as types, and `now()` is mechanically impossible.

**Acceptance.** Scope resolves against the demo database; the boundary test fails if `now()` is
introduced; the fingerprint is stable across two processes and byte-identical across two
independent clean rebuilds. For the committed demo dataset at `source_system='csv_demo'` it is
`1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00`, which M1 pins in
`config/intelligence/risk_rules.yaml` (§A27.1b).

**Rollback.** Delete the package — nothing depends on it yet.

**Non-goals.** Signals, persistence, API, anything that reads a ticket.

---

### M2 — Relationship model

**Objective.** One uniform way to ask what a customer is connected to, where every edge states
*how it is known*.

**Before.** Relationships exist as **3 resolved canonical FKs** and **6 unresolved source-key
joins**, of which VS-01 models 4 (§A9.1 fixes the counting convention). Documents are related to
employees in Layer 1 and to **no customer at all**, in any form.

**Change.** `app/relationships/edges.py` (edge types and basis), `app/relationships/queries.py`
(the **three** relationship queries of §A9 — `neighbourhood`, `escalation_path`,
`policy_documents`), `app/relationships/model.py` (assembly). Read-only; the caller owns
the session, matching the existing repository convention. The package produces `CANONICAL_FK` and
`SOURCE_KEY_JOIN` edges only; it constructs no `DerivedLink`, imports nothing from
`app/evidence/`, and **models no edge touching a `Document`** — `document_owned_by` is excluded
(§A9), so the package has no document edge from which a customer association could be composed.
One of the four source-key edges, **`deal_owned_by`, is substrate for later slices and is consumed
by no VS-01 query** (§A9.1): it is built and proved like any other edge, but no query returns it
and none may be added to make it look consumed.

**Tests — behaviour.** Each edge type resolves on the demo dataset; a `SOURCE_KEY_JOIN` never
crosses `source_system`; a NULL FK yields no edge rather than an error;
`escalation_path(CUST-007)` returns EMP-007 → EMP-002 plus **all four** open-ticket assignees EMP-017/018/020/021 → EMP-004 (§A9 says *each open ticket's* assignee, so EMP-017 is included for the open `medium` billing ticket TKT-079; it must not be filtered to high priority);
`neighbourhood(CUST-007)` returns 5 tickets, 1 deal, **0 projects**; a test asserts **no public
`traverse()`** exists.

**Tests — the M2/M4 boundary (§A9.2).** These are not implementation-detail tests. Each one fails
the build if a future change moves document linking into M2, or reaches a customer–document
association by another route, so they are written **before** the queries and never relaxed:

| # | Invariant | How it is asserted |
|---|---|---|
| B1 | **M2 emits zero document→customer edges.** | Run all three queries over **every** customer in the demo dataset — not just CUST-007 — and assert that no returned edge has a `Document` source or target paired with a `Customer`. The assertion is over the edge set, so it holds for customers added later |
| B2 | **M2 emits only the two canonical bases.** | Every edge returned by every query carries `EdgeBasis.CANONICAL_FK` or `EdgeBasis.SOURCE_KEY_JOIN`. `DERIVED_TEXT_MATCH` and `DERIVED_TOPIC_MATCH` never appear |
| B3 | **M2 constructs no `DerivedLink`.** | AST scan of `app/relationships/`: the name `DerivedLink` is never called, and no module binds `linker_version`, `matched_token`, `match_start` or `match_end` |
| B4 | **M2 cannot reach the linker.** | AST scan over the **transitive** import graph of `app/relationships/`: no import of `app/evidence`, and no module defines a function whose name matches `link`/`match`/`mention`. Pairs with §A22 |
| B5 | **`policy_documents()` carries no customer scope.** | Its signature takes no customer argument, and its result is customer-independent: called twice it returns the identical set regardless of any customer context. It is the only document-touching query in M2, and B1 already forbids it returning a customer edge |
| B6 | **`documents_for` does not exist in M2.** | `app/relationships/` exports no name matching `documents_for`, and `hasattr` over the package's public surface is empty for it. Deleted when M4 adds it to `app/evidence/`, where a mirrored test asserts it *does* exist |
| B7 | **Determinism and row-order independence.** | Every query is run twice in one session and once after `VACUUM`/reinsertion in a different physical order; results are compared for exact ordered equality. Each query carries an explicit `ORDER BY` over source identity, as §A5.1 requires of the fingerprint |
| B8 | **Layer 1 is untouched.** | The M1 fingerprint recomputes to the pinned `1d891b0b…` after the M2 suite runs, and no `app/relationships/` module calls a session write method (the M1 `FORBIDDEN_WRITES` scan, extended to this package) |
| B9 | **No document edge exists, and no ownership composition reaches a customer.** | Two parts, both defence in depth (§A9.2). **(a)** The edge vocabulary in `edges.py` contains no edge whose source or target is a `Document`; `document_owned_by` is absent by name, and no query returns a `Document` except as a bare node from `policy_documents()`. **(b)** The *would-be* composition is written out in the test as a negative control — join `documents.owner_source_id` to `customers.owner_source_id` directly in SQL, assert it yields the DOC-007 → CUST-007 pairing, then assert **no M2 query produces that pairing**. The control is what stops the test passing vacuously if the join silently stops returning rows |
| B10 | **`deal_owned_by` is correct, deterministic, provenance-preserving and Layer-1-derived — without a query consumer.** | Asserted against the edge builder directly, not through a public query, because no VS-01 query returns it (§A9.1). Four parts. **(a)** *Correct and Layer-1-derived:* every emitted edge reproduces a `deals.owner_source_id` → `employees.source_id` pair that exists in Layer 1, and every such pair within one `source_system` yields exactly one edge — no fabricated edge, no dropped one, counted over the whole demo dataset. **(b)** *Scoped:* the join never crosses `source_system`, and a NULL or unmatched `owner_source_id` yields no edge rather than an error, matching the behaviour tested for the other three source-key edges. **(c)** *Provenance-preserving:* every edge carries `EdgeBasis.SOURCE_KEY_JOIN` and names the carrier field it was derived from, so a reader can tell how it is known without consulting this plan. **(d)** *Deterministic:* repeated builds over rows in different physical orders are exactly equal, under B7's ordering rule. **This is how the 100% coverage gate is satisfied for the edge** — by testing the edge itself, never by adding a query that consumes it |

B1 is the load-bearing one: it is the executable form of *"M2 should explicitly be unable to
produce a document→customer edge."* B3, B4 and B6 make that structural rather than incidental —
B1 alone would still pass if someone wrote a linker that happened to return nothing on this
dataset. **B9 covers the blind spot B1 has by construction**: a two-hop ownership composition
never forms a Document–Customer edge, so B1 cannot see it, yet it produces exactly the false
association the boundary exists to prevent. Since `document_owned_by` was removed from the model
(§A9), B9(a) is what keeps it removed, and B9(b) documents — in executable form — the specific
false association that removal prevents.

**After.** Every later milestone reads relationships through one interface instead of ad-hoc
joins.

**Acceptance.** The three queries return the measured neighbourhoods; every returned edge carries
a basis; **B1–B10 all pass**. M2 is not complete while any boundary invariant is unasserted, nor
while `deal_owned_by` is unproved by B10 or consumed by any query.

**Non-goals.** Derived document links and `documents_for()` — both M4 (§A9, §A11); **any
Document edge, including `document_owned_by`** (§A9); any graph database; generic traversal;
`project_owned_by` (§A9); **any VS-01 consumer of `deal_owned_by` — no query return field, no
analyst context, no brief section** (§A9.1, §A9.2).

---

### M3 — Signal engine and risk band

**Objective.** Turn the neighbourhood into S1–S15 and an explainable band.

**Before.** Relationships are queryable but nothing is measured.

**Change.** `app/intelligence/signals.py` (S1–S15), `app/intelligence/windows.py` (the 14-day
sliding window and the lookback constraint), `app/intelligence/bands.py` (decision table
evaluation returning band **plus the satisfied rule ids**), and the populated
`config/intelligence/risk_rules.yaml`.

**Tests.** Every signal hand-computed for CUST-007, CUST-009, CUST-048, a ticketless customer and
an inactive one; **S2 = 3 and S2b = 4** pinned explicitly, because v1 got this wrong; sliding
window at 13/14/15-day boundaries; `as_of` sensitivity documented by a test at both 2026-08-27
and 2026-09-18; every row of the band table; rule liveness (threshold 3 → 6); amount invariance;
chronic backlog separation.

**After.** Risk is measured and every band assignment carries its reasons.

**Acceptance.** CUST-007 is the only escalated and only `CRITICAL` customer at
`ACCEPTANCE_AS_OF`; CUST-048 and CUST-009 rank below it with their stale tickets reported as
backlog.

**Non-goals.** Documents, persistence, positions, briefs.

**CLOSED — commit `34486eb`, 2026-09-21.** Measured against the clean full-dataset path at
`ACCEPTANCE_AS_OF`: CUST-007 is the only escalated and the only `CRITICAL` customer; CUST-025
and CUST-036 are `WATCH`; the remaining 47, including all 15 ticketless customers, are `NONE`;
CUST-009 and CUST-048 report TKT-010 and TKT-005 as chronic backlog and rank below CUST-007.
Every signal of §A10 is asserted at both 2026-09-18 and the 2026-08-27 fallback, where the
breach counts differ as §0 defect 3 records. `S2 = 3` and `S2b = 4` are pinned separately.
Baselines: suite 4731, `app/` coverage 100%, ruff 69, mypy 9, secret scan 0, fingerprint
`1d891b0b…`, `app/relationships/` byte-identical to `bc0525d`.

Four things a reader must carry forward, all in §0.2: the **band table rows are authored, not
specified** (§0.2.1, with the provenance of every rule); **NULL `created_at` is an open
specification gap** and deliberately produces no note (§0.2.2); M3 **consumes M2's public
queries and resolves nothing itself**, and `app/intelligence/__init__.py` must not import the M3
modules (§0.2.3); the single mutation survivor is **verified semantically equivalent** (§0.2.4).

S14 is empty: the composition that fills it is M4's and the production call is M5's
(§A10, §0.3.6 — decided after this block was written). `executive_worthy` is not implemented
here — §A15 defines it, but M3's acceptance does not name it, so it belongs to the milestone
that persists an
assessment. *(Corrected 2026-09-24 by §0.5.1 D-M6-B1: **M6 computes** worthiness and M7
persists the value; "the milestone that persists" named the wrong owner for the computation.)*
The §A21 events `vs01.signals_computed` and `vs01.band_assigned` are likewise
deferred: `app.core.logging` is outside the import surface M1's boundary test allows
`app/intelligence/`, and M3's *Change* list names no logging.

---

### M4 — Evidence and citations

**Objective.** Make every future claim checkable, and link documents to customers without
touching Layer 1.

**Before.** Documents are unreachable from a customer.

**Change.** `app/evidence/linker.py` (**`ID_TOKEN` and `EXACT_NAME` only** — `TOPIC` is not
implemented in VS-01, §0.3.1), `app/evidence/documents.py` exporting
**`documents_for(session, scope, customer_source_id) -> tuple[LinkedDocument, ...]`** — the
evidence interface §A9 keeps out of the M2 relationship API, composed in the repository read
(§0.3.10.2) —
plus **`with_contract_documents`**, the **`LinkedDocument`** representation it consumes and the
`contract` document-type constant, all of which M4 owns, exports and proves but **never calls** —
M5 invokes the function when it builds the executive context (§0.3.6);
`app/evidence/citations.py` (build and resolve);
`app/persistence/models/document_customer_link.py`,
`app/persistence/repositories/document_links.py` (§0.3.10.3), and the **first additive
Alembic revision** (`document_customer_links`) chained after `8bfd73b6af60` — *chained*, not
branched: the history must keep exactly one head. `linker_version` is added to
`config/intelligence/risk_rules.yaml` and to the key whitelist in `app/intelligence/config.py`
(§0.3.5). Links are derived inside an assessment run and stamped with `linker_version` and
`layer1_fingerprint`.

**Decisions this milestone is built on.** **D-1 through D-6 have architectural resolutions** in
§0.3: `TOPIC` removed (§0.3.1), `EXACT_NAME` corrected to DOC-005/006/009 (§0.3.2), grain
`(document, customer, basis)` with no precedence (§0.3.3), the uniqueness key and append
semantics (§0.3.4), `linker_version` (§0.3.5), and S14 split into **M4's composition function**
and **M5's production invocation** (§0.3.6). §0.3.7 lists what is still deliberately open, and
**an implementer must not settle any of it in passing**. §0.3.9 **specifies, but does not
authorise**, the five test/README changes M4 will require; performing any of them before M4 is
explicitly approved is out of scope.

`app/evidence/` may read `app/relationships/`; the reverse import is forbidden and §A22's boundary
test pins the direction. M4 therefore **adds a package** rather than reopening M2's, and M2's
"rollback = delete the package" property survives M4.

**No circular dependency is possible.** The import graph is a DAG:
`app/intelligence` (M1) ← `app/relationships` (M2) ← `app/evidence` (M4), with M3's signal engine
depending on M1 and M2 only. M4 consumes M2 by importing it; M2 never names M4. Invariant B4
fails the build on the reverse edge, so the DAG is enforced rather than merely intended.

**Tests.** `documents_for(CUST-007)` returns exactly six links and nothing else: DOC-005,
DOC-006 and DOC-009, each on **both** `ID_TOKEN` and `EXACT_NAME` (§0.3.3's grain, §0.3.2's
correction). **DOC-010 is returned for no customer** — it carries neither the `CUST-007` token
nor the name, and VS-01 models no topical link at all (§0.3.1). Id-token matching finds
DOC-005/006/009 for CUST-007; **exact-name finds DOC-005/006/009** — asserting DOC-006/009 is the
corrected defect and must fail. The corpus-wide expectation of §0.3.8 holds: CUST-015 → DOC-004
and DOC-008 by name only, CUST-021 → DOC-007 by both and DOC-011 by name only, the other 47
customers → nothing, 11 rows in all.

Substring safety across the three non-Meridian "… Textiles" customers, **and across "Meridian
Foods" (CUST-038) and "Deltaforge Health" (CUST-027)**, which share a name token with a customer
that does have links (§0.3.8). NULL `body_text` skipped; NULL `title` contributes the empty
string. A link never crosses a `source_system`. Record citations resolve to a real field; an
adversarial document is quoted, never interpreted.

**Matching and spans (§0.3.10.4).** Offsets index **citable text**, `(title or "") + "\n" +
(body_text or "")`, and the invariant `citable_text[match_start:match_end] == matched_token`
holds for **every** persisted row. `ID_TOKEN` is case-sensitive and bounded by `[^A-Za-z0-9_-]`:
`CUST-007` matches inside `(CUST-007)` and **not** inside `CUST-007Z`, `CUST-0071` or
`XCUST-007` — the last of which also pins §A25 test 13b's rename case. `EXACT_NAME` is
case-insensitive and bounded by `[^A-Za-z0-9]`, and `matched_token` records the text **as the
document writes it**, so a document saying "meridian textiles" yields that string, not the
canonical name. **DOC-009 is the adversarial fixture**: it holds `Meridian Textiles` three times
and `CUST-007` once, and under the first-occurrence rule it persists exactly two rows for
CUST-007 — `(EXACT_NAME, "Meridian Textiles", 23, 40)` and `(ID_TOKEN, "CUST-007", 76, 84)`.
Those literal offsets are asserted.

**Evidence kind (§0.3.10.1).** Every link's evidence carries
`EvidenceKind.DERIVED_RELATIONSHIP` with a `DocumentCitation` whose span equals the link's own
`(match_start, match_end)`, matching the payload shape M1's committed contract test already pins.

**Persistence (§0.3.10.3).** No module under `app/evidence/` or
`app/persistence/repositories/document_links.py` calls `commit`, `rollback`, `begin` or `close` —
the M1 `FORBIDDEN_WRITES` scan extended to both. The conflict is resolved by the database: a
second identical derivation inserts **0** rows and raises nothing. Every column is NOT NULL, both
foreign keys cascade, and the unique constraint and both indexes exist in the migrated schema.

Persistence: re-deriving with identical inputs inserts nothing; a changed `layer1_fingerprint`
appends rather than replacing; `linker_version` is stamped on every row; downgrade drops only the
new table and the history keeps one head.

S14, `with_contract_documents` (§0.3.6): composing an M3 signal set with M4's links yields
exactly `("DOC-006",)` for CUST-007 — **the decisive case, because CUST-007's DOC-006 arrives on
two evidence links and must project to one id**; every other `SignalSet` field is byte-identical
between input and output; the returned object is a new `SignalSet`, never a mutated one; the
function is pure and total — same inputs give the same output, and a customer with no `contract`
link yields `()` rather than an error; **the result is unchanged when the two evidence links are
supplied in either order or when one basis is dropped**, which is what pins the absence of any
evidence-priority rule; `documents_for()` still returns **both** DOC-006 links, so the evidence
layer is not collapsed by the projection; **no module under `app/evidence/` calls the function**,
so it cannot creep into the linking or persistence pipeline; and no module under `app/evidence/`
imports M3.

Four more S14 assertions, one per decision frozen on 2026-09-21. **The constant** is named
`CONTRACT_DOCUMENT_TYPE` and equals `"contract"`. **Matching is exact and case-sensitive**: a
link whose `document_type` is `"Contract"`, `"CONTRACT"`, `" contract"` or
`"contract_amendment"` contributes nothing, and neither does one whose `document_type` is
**`None`** — asserted with a fixture, since the committed corpus has no NULL `document_type`.
**Ordering** is lexicographic ascending by `document_id`: a fixture giving one customer contract
links to DOC-006 and DOC-002 yields `("DOC-002", "DOC-006")` in that order, whatever order the
links arrive in. **`LinkedDocument` wraps and does not extend**: `app/intelligence/contract.py`
is byte-identical to `29776e0`, `DerivedLink` has no `document_type` attribute, and
`LinkedDocument` is not a subclass of it.

Boundary, mirrored from M2 (§A11): `documents_for` **does** exist in `app/evidence/` and still
does not exist in `app/relationships/`; B9(a) is re-run so `app/relationships/` still models no
`Document` edge once `app/evidence/` exists; M2's transitive scan still never reaches
`app.evidence`; the Layer 1 fingerprint still recomputes to `1d891b0b…`.

**Negative controls for the M2 architectural invariant, now that `app/evidence/` may import both
models.** *Employee ownership of a document is not evidence that the document belongs to,
concerns or supports a customer* (§A9, §A9.2) — and B9 scans `app/relationships/`, which cannot
see `app/evidence/`. M4 therefore asserts on its own side: no module under `app/evidence/` reads
`documents.owner_source_id` or `customers.owner_source_id`; and B9(b)'s composition is written
out again as a live negative control — it yields **61** pairs on the demo dataset, including
DOC-007 → CUST-007 — with the assertion that no `documents_for()` result contains any of them.
Note that `owner_source_id` is a *citable* business field, so `RecordCitation('documents', …,
'owner_source_id')` is accepted by M1's frozen contract: nothing but this test stops ownership
becoming link evidence.

**After.** Any claim can cite a record field or a document span, and the citation is verifiable.

**Acceptance.** `documents_for()` reproduces §0.3.8's measured expectation exactly — 11 rows,
six of them CUST-007's — and every citation resolves. Composing an M3 signal set with M4's links
yields `("DOC-006",)` for CUST-007 **in a test** — M4 ships the function, not a call to it.
A re-run inserts nothing. `app/relationships/` is
byte-identical to `bc0525d` and `app/intelligence/` to `34486eb` — including
`signals.py`'s `contract_document_ids=()`. The Layer 1 fingerprint is
`1d891b0b…`. Regression per §A27.10, with README's quoted test counts updated in the same commit
(§0.3.9).

**An implementer who measures a link set different from §0.3.8 must report it rather than adjust
the expectation.** That table is the acceptance criterion, and it was corrected once already
(§0.3.2).

**The normal tooling gate is restored for the implementation pass.** The specification work of
§0.3 was verified by static reading and read-only SQL because no project virtualenv was present;
that was acceptable for documentation and is **not** acceptable for implementation. M4 does not
close until `pytest`, `ruff` and `mypy` have actually been **run** and their results reported —
suite green, `app/` coverage 100%, ruff 69, mypy 9, secret scan 0 (§A27.10). **A static argument
that the suite would pass is not evidence that it passed, and may not be recorded as one.** The
sequence is: specification freeze → implementation → tests → mutation and adversarial audit →
closure documentation.

**Non-goals.** Embeddings, similarity, keyword expansion or any other semantic inference —
`TOPIC` is not implemented and **no replacement mechanism may be introduced for it** (§0.3.1);
introducing a topic entity, column or vocabulary; forcing DOC-010 into a customer association;
a precedence rule between mechanisms (§0.3.3); any history, validity-interval or
`superseded_by` machinery on the link table (§0.3.4); importing M3 from `app/evidence/`
(§0.3.6); **calling `with_contract_documents` anywhere in M4's own linking or persistence
pipeline, or building any part of M5's executive context** — M5 owns the production invocation
(§0.3.6); **any evidence-priority rule** — no basis outranks another, S14's projection never
reads `basis`, and no link is deleted, superseded or hidden by it (§0.3.6); assembling or
persisting an assessment — `risk_assessments` is M7's; exposing
`documents_for()` through `app/relationships/` (§A9); adding any customer reference to Layer 1's
`documents` table; editing `app/intelligence/signals.py` or any other M1/M2/M3 module; settling
any item of §0.3.7.

---

### M5 — Analysts and positions

**Objective.** Split the enterprise view into two disjoint functional views that cannot see each
other's data, and have each state a position.

**Before.** All facts sit in one undifferentiated bag.

**Change.** `app/analysts/context.py` (`SupportContext`, `CommercialContext`, `TicketFact`,
`AnalystContexts`, `BILLING_CATEGORY`, and `build_contexts()` — the **one** module in the package
permitted a `Session` or an ORM model, §0.4.7), `app/analysts/base.py`,
`app/analysts/support_risk.py`, `app/analysts/commercial.py`. Each analyst emits
**`tuple[Position, ...]`** — one position per satisfied §A16 entry, each naming that entry's
contested object, with citations for every claim (§0.4.1).

**Decisions this milestone is built on.** **§0.4 resolves six blockers** found by the
pre-implementation audit of 2026-09-22, and an implementer must not settle any of them again in
passing: action representation (§0.4.1), the ticket derivation and its equivalence test
(§0.4.2), production ownership of `derive_and_persist` (§0.4.3), the authorised test and README
evolution T-M5-1…T-M5-4 (§0.4.4), the dependency boundary (§0.4.5), and Support's visibility of
the contested object (§0.4.6). §0.4.7 fixes the context factory's session and purity contract;
§0.4.8 fixes scope and the sixteen acceptance criteria. **M1, M2, M3 and M4 stay frozen**: M5
adds a package, reads their public APIs, and edits none of them.

**Tests.** The sixteen criteria of §0.4.8. In particular: a context-purity test written against
§0.4.6's explicit field list, not the phrase "any deal field"; an import test asserting neither
analyst module imports `Session` or an ORM model; the §0.4.2 equivalence table binding M5's
`TicketFact` derivation to M3's S1, S2, S2b, S7 and S8 for **every** customer at both `as_of`
dates; every `Position` validates, carries citations, and every citation resolves; exposure is
per currency and summing raises; `CommercialContext` carries `contract_document_ids ==
("DOC-006",)` while `documents_for()` still returns both DOC-006 links; AST scans asserting no
`app/analysts/` module writes, reads a clock, or calls `derive_and_persist`; and CUST-007's
**six** positions match §0.4.1's table row for row.

**After.** Two functions reason independently, their isolation is structural, and every action
either function wants is on the record with the object it contests.

**Acceptance.** §0.4.8's sixteen criteria. CUST-007 yields exactly six positions — five SUPPORT,
one SALES — of which exactly one SUPPORT and one SALES carry `object_ref = "DEAL-001"`, so M6
will detect exactly one conflict; nothing is dropped, ranked or merged; scope violations are
impossible to express, not merely discouraged; `app/intelligence/`, `app/relationships/` and
`app/evidence/` are byte-identical to `65eb462`; the Layer 1 fingerprint is `1d891b0b…`.

**Non-goals.** Reconciliation, conflict detection and the conflict policy (M6); **any
persistence, table, migration or configuration key** — including the production call to
`derive_and_persist`, which §0.4.3 assigns to M7; `executive_worthy` and §A15's worthiness and
ordering (**M6** computes both and M7 persists them — corrected 2026-09-24 by §0.5.1 D-M6-B1;
this line first read "(M7)"); any model; any change to M1, M2, M3, M4 or Layer 1; any test evolution beyond
T-M5-1…T-M5-4 (§0.4.4).

---

### M6 — Conflict detection and reconciliation

**Objective.** **The heart of the slice.** Detect that two functions want incompatible things,
resolve it by a stated policy, and keep the losing argument.

**Before.** Two positions exist side by side with nothing deciding between them.

**Change.** `app/decisions/__init__.py`; `app/decisions/policy.py` (load and validate
`action_catalogue.yaml` and `conflict_policy.yaml`, and evaluate a rule's `when`);
`app/decisions/conflicts.py` (detection over proposed actions and object identity, and the
runtime catalogue agreement check); `app/decisions/reconciler.py` (policy matching, the winning
action, dissent, the resolved position set, worthiness, both orders, and the `Reconciliation`
result); `config/intelligence/action_catalogue.yaml`; `config/intelligence/conflict_policy.yaml`.
**Exactly those four modules and two files** — no M7 module, no persistence, no migration.

**Decisions this milestone is built on.** **§0.5 closes the eight gaps** a readiness audit found
against `6158f81`, and an implementer must not settle any of them again in passing: ownership
(D-M6-B1 — M6 owns worthiness and ordering, M7 persists them); the catalogue as a declarative
vocabulary with M5's thresholds left where they are (D-M6-B2); the authorised test and README
evolution T-M6-1…T-M6-4 (D-M6-B3); resolution evidence cited by document id (D-M6-B4); an
unresolvable conflict raises (D-M6-B5); `policy_version` (D-M6-B6); the `Reconciliation` result
(D-M6-B7); worthiness (D-M6-B8); both orders (D-M6-B9); one-object scope (D-M6-B10); and the
frozen contracts, verified sufficient (D-M6-B11). §0.5.12 freezes the policy schema, §0.5.13 the
dependency boundary, §0.5.14 scope and the twenty-one acceptance criteria. **M1–M5 stay frozen.**

**Tests.** The twenty-one criteria of §0.5.14. In particular: conflict detected for CUST-007 over
DEAL-001 and exactly one across the corpus; `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` wins under
CONF-001; the resolution cites DOC-003 and DOC-009; **dissent is preserved with its own
citations**; policy liveness — flipping `resolve_to` flips the outcome; a customer with no shared
object produces no conflict and no dissent; worthiness truth table; ordering truth table, and
ordering unchanged when amounts are perturbed; an unresolvable conflict — its rule's `when` fails
— raises rather than silently picking one; every policy and catalogue refusal names what it
refuses; and the §0.5.13 boundary, each scan with a companion.

**After.** The system performs executive reconciliation, deterministically and explainably. This
is the milestone that makes the slice a proof of the AI CEO concept rather than a report.

**Acceptance.** §0.5.14's twenty-one criteria. For CUST-007 the conflict, the winning action, the
named policy id and the recorded dissent are all present and correct; its `Reconciliation`
matches §0.5.7's table; `app/intelligence/`, `app/relationships/`, `app/evidence/` and
`app/persistence/` are byte-identical to `65eb462` and `app/analysts/` to `d48c970`.

**Non-goals.** More than two functions, three-way or cyclic conflicts (VS-04); model-generated
rationale; any persistence, payload hash, narrative, route or approval (M7, M8); the production
call to `derive_and_persist` (M7); §A21's log events (the run's, §0.5.1); moving or copying
§A16's thresholds (§0.5.2); any change to M1–M5 or Layer 1; any test evolution beyond
T-M6-1…T-M6-4.

**CLOSED — commit `fd3a7e0`, 2026-09-24** (specification `1d1ee59`). Every §0.5 expectation was
met as stated, with nothing adjusted after measurement: CUST-007 reconciles to §0.5.7's table
exactly; the corpus holds **one** conflict and raises for no customer; **15** positions across ten
customers, **14** resolved; **only CUST-007** is executive-worthy; the order of all fifty is
§0.5.9's measured order. Baselines: suite **5533** (unit 4518, contract 185, integration 750,
e2e 80), `app/` coverage **100%** (6347 statements, `app/decisions/` 410), ruff **69**, mypy
**9**, secret scan **0** over 292 files, one head, no migration — so M6 added no finding. The
ordered reconciliations of all fifty customers hash identically in two processes with different
hash seeds over independently rebuilt databases.

Five things a reader must carry forward:

1. **The repeated-key check composes, it does not load.** §0.5.12 row 10 is implemented by
   walking `yaml.compose(text, Loader=yaml.SafeLoader)` nodes before `yaml.safe_load`, because
   G2's `test_no_code_executes_or_unsafely_deserializes_content` forbids any `yaml.load(...)`
   call in `app/` — including one with a `SafeLoader` subclass. Do not "simplify" it into a
   custom loader.
2. **§0.5.5 is demonstrated on real rows, not only on fixtures.** Promoting CUST-036's
   `qualification` deal DEAL-037 to `negotiation` at 90% makes Support pause and Sales accelerate
   one deal at band `WATCH`, and `reconcile()` raises naming CONF-001's failing band condition
   (`test_a_real_conflict_conf_001_does_not_apply_to_raises`). That is the exact shape §A29
   records, one data edit away from the committed dataset.
3. **Targeted mutation check over `app/decisions/`: 33 of 35 killed**, stable over two runs, run
   with the ad-hoc harness convention of §0.2.4 (not committed). The first run found one real gap —
   no test separated S8 from S4 as the `when` input — closed by
   `test_the_breach_condition_reads_s8_and_nothing_else`. The two survivors are **proved
   equivalent** and kept as explicit statements of D-M6-B10 and D-M6-B9: dropping the
   different-function test in `detect_conflicts` (a declared pair always spans two catalogue
   functions, and every position is checked against its catalogue function first), and iterating
   objects in dict insertion order rather than `sorted()` (positions arrive `SALES` before
   `SUPPORT`, and every conflicted object carries a `SALES` position, so insertion order happens to
   be ascending — which D-M6-B9 forbids relying on). The first would stop being equivalent if a
   catalogue let one function propose both actions of a pair; the second if a third `Function`
   were added.
4. **The public surface is exactly §0.5.7's list**, pinned by
   `test_the_public_surface_is_exactly_the_declared_one`. `checked_positions`,
   `position_identity` and `resolution_evidence` are module-level helpers, importable from their
   modules and deliberately not re-exported.
5. **The M1/M5 write scan counts any `.add()` call**, so `app/decisions/` collects with lists,
   never `set.add`. The scan was kept strict rather than taught an exception.

**Still M7's, recorded not hidden:** persisting `executive_worthy` and `policy_version`; emitting
§A21's `vs01.conflict_detected` and `vs01.conflict_resolved` from the `Reconciliation`; the
production `derive_and_persist()` call (§0.4.3); rendering the quoted spans of DOC-003 and DOC-009
under §A22's cap.

---

### M7 — Brief assembly, hashing and persistence

**Objective.** Freeze a decision into something that can be shown to a human and bound to an
approval.

**Before.** A reconciled result exists only in memory.

**Change.** `app/decisions/assessment.py` (**the assessment run** — §0.4.3 assigns it the
production call to `derive_and_persist()`, once per run per scope, before any context is built,
inside the caller's transaction), `app/decisions/payload.py` (the hashed decision payload),
`app/decisions/brief.py` (narrative rendering), `app/decisions/templates/`, models for
`risk_assessments`, `risk_positions` and `risk_briefs`, their repositories, and the **second
additive migration**. `risk_positions` takes **one row per `Position`**, so several rows per
function per assessment are normal (§0.4.1) — the table already carries no unique constraint
(§A18). **M7 consumes M6's `Reconciliation` (§0.5.7) and computes neither worthiness nor
ordering**: `risk_assessments.executive_worthy` is `Reconciliation.worthiness.executive_worthy`,
`risk_briefs.policy_version` is `Reconciliation.policy_version`, and assessments are listed in
`order_reconciliations()` order (§0.5.1). The run also emits §A21's `vs01.conflict_detected` and
`vs01.conflict_resolved` from that result.

**Tests.** Payload hash excludes timestamps and `template_version` — changing a template does
**not** change the hash, changing a fact **does**; hash identical across two processes;
uniqueness including `layer1_fingerprint`; **fingerprint sensitivity** — one extra ingested
ticket yields a new assessment rather than the stale one; re-run inserts nothing; absence stated
(CUST-007 has no project); citation resolution across every generated brief; the **DOC-005
leave-out test** in-process against a dedicated test database; a golden file for the CUST-007
brief at `ACCEPTANCE_AS_OF`.

**After.** A brief is reproducible, diffable and approvable.

**Acceptance.** The CUST-007 brief matches the golden file byte-for-byte and contains every item
of §A27.3 and §A27.5.

**Non-goals.** Approval; API; UI; computing worthiness or ordering, or re-deciding any conflict
(M6, §0.5.1).

---

### M8 — API and the human approval boundary

**Objective.** Expose the slice over the existing API contract, and make the governance boundary
real and unbypassable.

**Before.** The slice is reachable only from Python.

**Change.** `app/decisions/approval.py` (append-only decisions bound to `payload_hash`), the
`brief_decisions` model and **third additive migration**, `app/api/v1/risk.py` (six routes),
additions to `app/api/v1/schemas.py`, router registration.

**Tests.** Append-only — an update attempt fails; a stale `payload_hash` is refused; a second
decision requires `supersedes_id`; rejection is recorded; OpenAPI-discovered contract tests in
the H4 style; `POST` re-run returns `200` with the existing assessment; error bodies leak no
document text or email; **the transitive no-executor boundary test** over all four packages,
with named, justified exemptions; existing F1/F2 contract tests still pass unchanged.

**After.** A human can approve or reject, the record is permanent, and the system provably cannot
act on it.

**Acceptance.** A rejected brief is recorded and nothing is executable; the boundary test fails
if an outbound client is introduced anywhere in the transitive graph.

**Non-goals.** Authentication (documented as a prerequisite for any future executor); execution;
a frontend.

---

### M9 — Acceptance, evaluation and hardening

**Objective.** Make the whole slice a single reproducible command, and prove the claims rather
than asserting them.

**Before.** The pieces work; the scenario is not executable end to end.

**Change.** `scripts/vs01_acceptance.py` and `make verify-vs01` (named checks, each with a pass
condition and one line of observed evidence, in the `verify_layer1.py` style);
`tests/e2e/test_vs01_scenario.py`; the fixtures of §A26; a README section; a VS-01 phase record
appended to `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`; a mutation audit over the signal engine, band
table, conflict policy and linker.

**Tests.** The full §A28 flow over HTTP; all fourteen named tests of §A25; the Layer 1 regression
groups; baseline checks for ruff, mypy, coverage and secret scan.

**After.** VS-01 is demonstrable, reproducible by a reviewer, and its foundations (§A30) are ready
for VS-02.

**Acceptance.** All ten criteria of §A27.

**Non-goals.** Starting VS-02; generalising any slice-local component before its second consumer
exists.

---

### Dependency order

`M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9`

M2 and M3 may overlap; M4 may start once M1 is done — it adds `app/evidence/` rather than
reopening `app/relationships/`, which is why it does not depend on M2 (§A9, §0.1 defect 17).
Every other edge is a hard dependency.
M6 is the milestone that must not be cut — without it the slice is a report, not a proof.
