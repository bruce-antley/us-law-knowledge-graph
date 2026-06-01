# US Law Knowledge Graph — Current State
*Last updated: 2026-05-24*

---

## What This Project Is

**LexGraph** is a proprietary knowledge graph of U.S. law — ultimately all of U.S. law, and potentially beyond — with a proprietary legal research tool built on top. The graph models law as a navigable, machine-readable network of doctrines, cases, and relationships — not a searchable corpus of documents.

**The commercial thesis:** Accuracy and hallucination-reduction are critical to lawyers. The graph's value is producing verifiable, structurally-constrained output. The failure mode is categorically different from a raw LLM — it cannot confabulate cases or fabricate holdings because every answer is grounded in explicit graph relationships.

**Business model:** Surface graph results filtered through a legal reasoning layer (Kingsfield) via MCP first, then eventually a user interface.

**Competitive position:** Not replicating Westlaw or Lexis. Offering something they structurally cannot: a traversable, machine-readable model of how law is organized, not just a searchable corpus of documents.

**Stack:** Neo4j AuraDB (graph database) · Python (pipeline) · Claude Haiku (builder) · NVIDIA free tier (audit judges) · Claude Sonnet (orchestrator) · D3.js (visualization)

**GitHub:** github.com/bruce-antley/us-law-knowledge-graph (all rights reserved)

---

## Graph State

```
Nodes:  898     Cases: 415 · Doctrines: 334 · DoctrinalTests: 102 · Areas: 20 · ConstitutionalProvisions: 4
Edges:  1298    APPLIES: 315 · ESTABLISHES: 257 · CHILD_OF: 242 · INTERPRETS: 165 · MODIFIES: 125
                GOVERNED_BY: 62 · INTELLECTUALLY_PRECEDES: 32 · DISTINGUISHES: 20 · OVERRULES: 19
                GROUNDED_IN: 17 · INCORPORATES: 2 · PRECONDITION_TO: 1

Validation:     0 errors · 10 warnings (all documented deliberate decisions)
Ring 1:         13/14 checks passing · C14 wrong-syllabus check added · 1 pre-existing C12 warning
Ring 2:         92% SCDB match · 4 documented deliberate decisions
Ring 3:         Full audit complete (2026-05-22) · ~220 fixes applied
Ring 4:         Prong quality audit complete (2026-05-23) · 50 fixes applied
```

---

## Doctrinal Coverage

```
Constitutional Law
├── Individual Rights
│   ├── First Amendment
│   │   ├── Commercial Speech           ✅ Full treatise depth
│   │   ├── Core Political Speech       ✅ Full treatise depth
│   │   ├── Prior Restraint             ✅ Full treatise depth
│   │   ├── Freedom of the Press        ✅ Full treatise depth
│   │   ├── Free Exercise of Religion   ✅ Full treatise depth
│   │   ├── Establishment Clause        ✅ Full treatise depth
│   │   ├── Freedom of Association      ✅ Full treatise depth
│   │   └── Freedom of Petition         ✅ Full treatise depth
│   ├── Equal Protection                ✅ Substantial coverage
│   ├── Substantive Due Process         ✅ Substantial coverage
│   ├── Procedural Due Process          ✅ Substantial coverage
│   ├── Takings Clause                  ✅ Substantial coverage
│   └── Criminal Procedure              ✅ Substantial coverage
├── Federalism
│   └── Dormant Commerce Clause         ✅ Substantial coverage
└── Separation of Powers                ✅ Substantial coverage
```

**415 SCOTUS cases** spanning 1803–2024. 446 Oyez syllabi in corpus (98% coverage of active cases).

**Coverage validation methodology:**
- Seidman Constitutional Law casebook: 91/91 cases present (100%, verified 2026-05-19)
- Rotunda Constitutional Law treatise: Full gap analysis run across all doctrinal areas (2026-05-19); gaps filled via pipeline batches 6-8. Areas covered: First Amendment (all 8 sub-areas), Equal Protection, Substantive Due Process, Procedural Due Process, Criminal Procedure, Federalism, Separation of Powers, Takings, Dormant Commerce Clause.
- This is not an estimate — it is a verified result from systematic gap analysis.

---

## Schema — Node Types

| Type | Count | What it represents |
|------|-------|-------------------|
| `Case` | 415 | SCOTUS decisions. The authoritative record of what a court held. |
| `Doctrine` | 334 | Legal principles/frameworks. What courts apply to facts. |
| `DoctrinalTest` | 102 | Formalized multi-prong tests (e.g., Central Hudson). Sub-type of Doctrine. |
| `Area` | 20 | Doctrinal hierarchy — the taxonomy spine. |
| `ConstitutionalProvision` | 4 | Articles, amendments, clauses. |

---

## Schema — Edge Types and Semantics

This is the heart of the graph. Edge types have precise meanings:

| Edge | Count | Meaning | Key attribute |
|------|-------|---------|---------------|
| `APPLIES` | 328 | Case used this doctrine without changing it | — |
| `ESTABLISHES` | 257 | Case originated this doctrine for the first time | — |
| `CHILD_OF` | 242 | Doctrinal hierarchy (Area taxonomy) | — |
| `INTERPRETS` | 165 | Case directly construed a constitutional provision | — |
| `MODIFIES` | 122 | Case changed this doctrine | `direction`: narrows/expands/clarifies/complicates/repudiates |
| `GOVERNED_BY` | 62 | Area/Doctrine is governed by this test | `valid_from`, `valid_until` |
| `INTELLECTUALLY_PRECEDES` | 32 | Non-binding opinion that shaped later doctrine | `opinion_ref` |
| `DISTINGUISHES` | 20 | Case distinguished itself from prior case | — |
| `OVERRULES` | 19 | Case killed a prior case as precedent | `overrule_type`: explicit/implicit/effective |
| `GROUNDED_IN` | 17 | Doctrine grounded in constitutional provision | — |
| `INCORPORATES` | 2 | 14th Amendment incorporating Bill of Rights | — |
| `PRECONDITION_TO` | 1 | Doctrine is a precondition to another | — |

**Absence of edges is informative.** No MODIFIES edge means the case applied but didn't change the doctrine. No OVERRULES edge means the prior case is still good law. This is a design feature, not a gap.

---

## Where Things Live

### Repositories

```
~/Downloads/us-law-knowledge-graph/    ← Git repo (GitHub)
  data/conlaw_graph_v02.json           ← SOURCE OF TRUTH (JSON)
  docs/                                ← Journal entries, STATE.md
  visualization/conlaw_graph_v02.html  ← D3.js interactive visualization
```

### Pipeline

```
~/Documents/lexgraph_pipeline/
  run_audit_cycle.py                   ← MAIN ENTRY POINT — one command for full audit
  core/
    elsa.py                            ← Case builder (calls Claude Haiku)
    validate.py                        ← JSON schema validator
    neo4j_import.py                    ← Neo4j wipe-and-reload (reads .env automatically)
    run_pipeline.py                    ← Full pipeline runner
    qa_legal.py / qa_factual.py / qa_structural.py / qa_doctrinal.py
    qa_legal_precheck.py
  audit/
    ring1_health_check.py              ← Deterministic checks (2 seconds)
    ring2_scdb_check.py                ← SCDB cross-reference
    ring2_wikipedia_check.py           ← Wikipedia cross-reference
    ring3_edge_audit.py                ← LLM binary edge audit (NVIDIA judges)
    audit_orchestrator.py              ← Sonnet evaluation of Ring 3 flags
    apply_fixes.py                     ← Applies fixes to JSON + Neo4j
    audit_panel.py                     ← Legacy (superseded by ring3_edge_audit)
    fetch_missing_syllabi.py           ← Fetches missing Oyez syllabi
  data/
    case_registry.json                 ← Master case list
    .env                               ← API keys (NEO4J_*, ANTHROPIC_API_KEY, NVIDIA_API_KEY)
  syllabi/                             ← 446 Oyez syllabus files (case_id_syllabus.txt)
  reports/                             ← All run output files (ring1/2/3 reports, decision logs)
  archive/
    pipeline_artifacts/                ← Per-case drafts, QA reports, raw outputs
```

### External

```
~/Downloads/
  SCDB_2025_01_caseCentered_Citation.csv    ← SCDB modern (1946–2024, UTF-8)
  SCDB_Legacy_07_caseCentered_Citation.csv  ← SCDB legacy (1791–1945, Latin-1)
  [Too large for git — not in repo]
```

### Neo4j AuraDB

```
Instance:   779dfe5d
URI:        neo4j+s://779dfe5d.databases.neo4j.io
User:       779dfe5d  (same as instance ID)
Database:   779dfe5d  (same as instance ID)
Query API:  https://779dfe5d.databases.neo4j.io/db/779dfe5d/query/v2
```

---

## How to Run Things

### Session startup (always first)

```bash
cd ~/Documents/lexgraph_pipeline && export $(cat .env | xargs)
```

### Full hands-free audit cycle

```bash
caffeinate -i /Users/bruceantley/anaconda3/envs/fastai310/bin/python \
  run_audit_cycle.py
```

Runs Ring 1 → Ring 2 → Ring 3 (all checks) → Orchestrator → Apply → Validate → Neo4j reload → Git commit.
Produces `reports/exceptions_TIMESTAMP.txt` if anything needs human review (target: <20 items).

**After reviewing exceptions:**
```bash
/Users/bruceantley/anaconda3/envs/fastai310/bin/python \
  run_audit_cycle.py \
  --apply-decisions reports/exceptions_TIMESTAMP.json
```

**Options:**
```bash
--checks modifies_dir,establishes   # Run specific checks only
--skip-ring2                         # Skip SCDB check
--dry-run                            # Show what would happen, apply nothing
--limit 10                           # Limit edges per check (testing)
```

### Individual rings

```bash
# Ring 1 — deterministic (2 seconds)
python3 audit/ring1_health_check.py

# Ring 2 — SCDB reference
python3 audit/ring2_scdb_check.py \
  --scdb ~/Downloads/SCDB_2025_01_caseCentered_Citation.csv \
  --scdb-legacy ~/Downloads/SCDB_Legacy_07_caseCentered_Citation.csv

# Ring 3 — single check
caffeinate -i python3 audit/ring3_edge_audit.py --check modifies_dir --output reports/test.txt

# Orchestrate a Ring 3 output
caffeinate -i python3 audit/audit_orchestrator.py \
  --input reports/ring3_modifies_dir_*.json \
  --output-queue reports/apply_queue.json \
  --output-review reports/human_review.txt
```

### Neo4j reload (from JSON)

```bash
echo "yes" | caffeinate -i /Users/bruceantley/anaconda3/envs/fastai310/bin/python \
  core/neo4j_import.py \
  --file ~/Downloads/us-law-knowledge-graph/data/conlaw_graph_v02.json \
  --wipe
```

### Validate JSON

```bash
/Users/bruceantley/anaconda3/envs/fastai310/bin/python3 core/validate.py \
  --file ~/Downloads/us-law-knowledge-graph/data/conlaw_graph_v02.json
```

### Git commit

```bash
cd ~/Downloads/us-law-knowledge-graph
git commit -a -m "Description of changes"
git push
```

---

## Audit System

### Architecture

```
Ring 1  Deterministic health checks       13 checks, 2 seconds, 0 errors = must pass
Ring 2  SCDB cross-reference              Citation-based, instant lookup
Ring 3  LLM binary edge audit             3 NVIDIA judges per edge, binary yes/no per question
        ↓ flagged edges
        Orchestrator (Claude Sonnet)       Evaluates flags with graph context + Kingsfield
        ↓ apply queue + exceptions file
        apply_fixes.py                     Applies fixes to JSON + Neo4j (matches on edge_id)
        ↓
        Validate + self-heal               Auto-fixes common post-apply errors
        ↓
        Neo4j reload + git commit
```

### Ring 3 checks

| Check | Edges | Question |
|-------|-------|---------|
| `overrules` | 19 | Is overrule_type (explicit/implicit/effective) correct? |
| `modifies_dir` | 114 | Is the MODIFIES direction attribute correct? |
| `modifies_soft` | 95 | Should a MODIFIES/repudiates edge be OVERRULES instead? |
| `establishes` | 355 | Did this case actually originate this doctrine? |
| `applies_real` | 281 | Does this case actually apply this doctrine? |
| `applies_under` | 281 | Should this APPLIES edge be MODIFIES instead? |
| `interprets` | 165 | Does this case actually interpret this provision? |
| `holding` | 364 | Is the holding text accurate per the syllabus? |

### Confidence thresholds (check-type specific)

```python
THRESHOLDS = {
    "establishes":    0.78,   # Systematic builder error, low risk
    "modifies_dir":   0.80,   # Bounded vocabulary, clear criteria
    "modifies_soft":  0.85,   # Moderate risk
    "applies_real":   0.82,   # Low risk
    "applies_under":  0.80,   # Low risk
    "interprets":     0.82,   # Moderate risk
    "overrules":      0.92,   # High schema stakes
    "holding":        0.90,   # Highest legal stakes
    "delete_artifact":0.85,   # Irreversible
}
```

### Ring 4 design decisions

Ring 4 has a split automation strategy — not all fix types are equally safe to automate:

**Auto-applied (bounded vocabulary, safe):**
- `SET_SCRUTINY_LEVEL` — updates `scrutiny_level` field on DoctrinalTest node
- `SET_BURDEN` — updates `burden` field on DoctrinalTest node
- `SET_TEST_FORM` — sets `test_form` to disjunctive or conjunctive

**Human review only (open-ended text, not safe to automate):**
- `FIX_PRONG_TEXT` — prong description or burden_note corrections
- `ADD_PRONG` — adding missing prongs
- `REMOVE_PRONG` — removing spurious prongs

**Rationale:** Prong text corrections require generating legal text that could be legally wrong
if Sonnet makes an error. Scrutiny level and burden are drawn from a fixed vocabulary and
can be validated against the schema enum. Text fixes go to the Ring 4 human review report
for manual application.

**Thresholds:** Ring 4 uses 0.85 for SET_SCRUTINY_LEVEL/SET_BURDEN (same as Ring 3 moderate
risk), but routes all FIX_PRONG_TEXT/ADD_PRONG/REMOVE_PRONG to human review regardless
of confidence.

**When to run Ring 4:** Only when DoctrinalTest nodes are added or modified. Not on every
commit. Trigger: `python3 run_audit_cycle.py --ring4 --checks none --skip-ring2`

### Known issues

- **C12 warning:** 6 good-law cases with zero outgoing edges (Florida v. J.L., Salinas v. Texas, Clingman v. Beaver, Masterpiece Cakeshop, Carson v. Makin + 1). Need APPLIES or ESTABLISHES edges added.
- **Prong truncation false positives:** Ring 4 flagged ~40 "truncated" prongs but inspection showed text is complete. Sonnet was seeing mid-display truncation in context window. Not real errors.
- **Spending Power test:** Updated to 4 prongs (added unambiguous conditions prong per South Dakota v. Dole).
- **Escobedo test:** Corrected to 4 prongs (removed Miranda-era prong 5 — right to silence warning).

---

## Kingsfield — Legal Reasoning Layer

`kingsfield.md` — the system prompt that makes the graph useful for legal research.

**Status:** First version exists in project knowledge. Needs to be saved as `~/Documents/lexgraph_pipeline/kingsfield.md` so `run_audit_cycle.py` loads it automatically as the orchestrator system prompt.

**Two modes:**
- **Research mode:** Answers legal questions by traversing the graph, reasoning about structural relationships, identifying schema gaps
- **Audit mode:** Evaluates flagged edges, classifies them, recommends fixes with confidence

**The Central Hudson insight:** Graph-assisted answers are structurally constrained by explicit doctrinal relationships — qualitatively different from raw LLM answers. The system can identify missing edge types ("operationalizes") while answering research questions. This is the LexGraph thesis demonstrated empirically.

---


### Prompt Architecture — Current State

| Layer | Content | Location |
|---|---|---|
| Project instructions | Kingsfield-Lite (~6,100 chars) | Claude.ai project settings |
| Project knowledge | Full Kingsfield v2, schema docs | Claude.ai project knowledge |
| Pipeline (local) | kingsfield_v2.md, kingsfield_lite.md | ~/Documents/lexgraph_pipeline/kingsfield/ |
| Shipped product (Phase 3) | Full Kingsfield in API system param with prompt caching | TBD |

**Key lessons from prompt architecture testing:**
- Full Kingsfield (126K chars / ~30K tokens) too large for project instructions — consumes ~15% of context window
- Model behavior differs significantly by version: Opus 4.7 follows Kingsfield well; Opus 4.8 less consistent
- Web search must be enabled for out-of-scope questions — without it models hallucinate while citing approved sources
- Critical instruction: "Do not attribute training data to an external source" — prevents citing CourtListener/LII for answers drawn from training data

## Roadmap

### Immediate next

**Viability gaps: COMPLETE** ✅
- C14 wrong-syllabus check: integrated into Ring 1, runs automatically
- Cross-area consistency: 12 redundant APPLIES edges removed
- Ring 4 prong quality: 50 fixes (30 scrutiny_level, 15 burden, structural fixes)
- Wrong-syllabus spot-check: 6 cases verified clean


### Kingsfield-Lite

**Location:** `~/Documents/lexgraph_pipeline/kingsfield/kingsfield_lite.md`
**Size:** ~6,100 characters — fits in project instructions
**Purpose:** Operative governance for working sessions; full Kingsfield in project knowledge for reference

**Key lessons from testing:**
- Full Kingsfield (126K chars / ~30K tokens) is too large for project instructions — consumes 15% of context window
- Kingsfield-Lite contains all load-bearing directives: Standing Instructions, Five Commitments, Foundational Commitments, Out-of-Scope protocol, CRAC structure, Writing Discipline
- Critical addition: "Do not attribute training data to an external source" — prevents models from citing CourtListener/LII while actually pattern-matching from training data
- Opus 4.7 follows Kingsfield-Lite well; Opus 4.8 behavior is less consistent
- Web search must be enabled for out-of-scope questions to work correctly

**Prompt architecture decisions:**
- Project instructions: Kingsfield-Lite
- Project knowledge: Full Kingsfield v2 for section-specific reference
- Shipped product: Full Kingsfield in API system parameter with prompt caching (Phase 3)

### Round 2 A/B/C Test Results

**What was tested:** C (Sections 1-2 only) vs C (full Kingsfield, Sections 1-8)
**Finding:** Full Kingsfield produces structurally richer answers — better CRAC structure, clearer conclusions, stronger treatment of unsettled doctrine, more professional register. Quantitative scores unchanged (ceiling effect — all 5s in Round 1) but qualitative improvement is material.
**Key insight:** The improvement is architectural, not just cosmetic. Full Kingsfield changes the answer posture; it doesn't just polish prose.

### Kingsfield — Current Status

**Location:** `~/Documents/lexgraph_pipeline/kingsfield/`
- `kingsfield_v2.md` — COMPLETE, all 8 sections locked
- `kingsfield_lite.md` — COMPLETE, operative version for project instructions (~6,100 chars)

**Sections locked:**
1. Identity and Purpose ✅
2. The Nature of Legal Reasoning ✅
3. Node Type Semantics ✅
4. Edge Semantics ✅
5. Limits of Representation ✅
6. Traversal Patterns ✅ (includes 6.15 Cypher appendix, validated against live schema)
7. Predictive Humility ✅
8. Legal Writing Style ✅ (includes CRAC, threshold issues, structure-follows-confidence, Bluebook citations)

**Section 9 (Audit Mode):** Deliberately excluded — admin-only function, documented separately
**GitHub:** Kingsfield removed from public repo (proprietary IP). .gitignore updated.

**Intellectual foundation:**
- Edward Levi, *An Introduction to Legal Reasoning* (1948) — legal reasoning is reasoning by example; rules emerge from case comparison, not before it
- Frederick Schauer, *Thinking Like a Lawyer* (2009) — doctrine constrains without fully determining; rules narrow the space of defensible positions
- These two sources ground the document's register: jurisprudential framework, not prompt engineering

**Key design decisions (document these or you'll forget):**
- Kingsfield is private IP — lives in `lexgraph_pipeline/`, NOT in the public GitHub repo
- Written as prose first, to be modularized into YAML later (Phase 2)
- Register: declarative reasoning constitution, not assistant instruction manual
- "The graph doesn't replace lawyerly judgment — it grounds it"
- Sections written to be modular so Phase 2 extraction is easy

**Planned sections:**
1. Identity and Purpose ✅
2. The Nature of Legal Reasoning ✅
3. Node Type Semantics
4. Edge Semantics — the heart
5. Schema Introspection
6. Traversal Patterns
7. Predictive Humility
8. Legal Writing Style
9. Audit Mode

### A/B/C Test Results (2026-05-24)

**Test design:** Four questions, three conditions
- A = Raw Claude (no graph, no Kingsfield)
- B = Claude + Graph (no Kingsfield)
- C = Claude + Graph + Kingsfield (Sections 1-2 only)

**Questions:**
1. Trace the clear and present danger test from origins to Brandenburg
2. What is the governing standard for commercial speech, and is it settled?
3. Is Lemon v. Kurtzman still good law?
4. What was the outcome of M&K Employee Solutions v. Trustees of IAM Nat. Pension? (decided 3 days prior — failure mode test)

**Scores (1-5 scale):**

| | A | B | C | B-A | C-B | C-A |
|---|---|---|---|---|---|---|
| Q1 | 4 | 4 | 5 | 0 | +1 | +1 |
| Q2 | 4 | 5 | 5 | +1 | 0 | +1 |
| Q3 | 5 | 5 | 5 | 0 | 0 | 0 |
| Q4 | 3 | 4 | 5 | +1 | +1 | +2 |
| **Total** | **16** | **18** | **20** | **+2** | **+2** | **+4** |

**Key findings:**
- Core hypothesis confirmed: B > A (+2), C > B (+2), C > A (+4)
- The graph adds value where structural information matters (MODIFIES(complicates) edge note on Sorrell, explicit OVERRULES on Lemon)
- Kingsfield adds value where analytical framing matters (three-question decomposition on Q3, source attribution on Q4)
- B uniquely caught a data quality bug (duplicate lemon_test_applied node still marked active)
- Q4 (failure mode) is where the categorical difference is clearest: A pattern-matched a guess, B checked and searched, C checked, explained the gap structurally, and attributed sources before answering
- A's baseline is impressively high on well-documented doctrine — the value proposition is most visible on recent/obscure/structurally complex questions

**The commercial hypothesis (untested):**
Whether lawyers will value provenance-aware, governed legal reasoning enough to prefer it over raw frontier-model interaction. This requires a different test: real lawyers, real research tasks, asking "did you trust the output and why?" The A/B/C test validates the product. The commercial hypothesis requires validating the market.

**Test files:** `~/Documents/lexgraph_pipeline/kingsfield/CARLA_ABC_Test_Matrix_Scored.xlsx`

### Phase 1: Kingsfield

Finalize and deploy `kingsfield.md` as system prompt for both:
- Research interface (answers legal questions with graph grounding)
- Audit orchestrator (replaces thin cold prompts, raises confidence, reduces exceptions)

### Phase 3: MCP exposure

Wrap graph + Kingsfield in MCP server with high-level tools:
- `research_doctrine(question)` — structured legal research
- `trace_case_lineage(case_id)` — intellectual and doctrinal lineage
- `check_good_law(case_id)` — current status with overruling chain
- `explain_test(test_id)` — test prongs with case applications

### Phase 4: Demo

Internal first. Benchmark questions across all reasoning modes. Decision: expand to Equal Protection depth or additional doctrinal areas?

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Source of truth | JSON file | Neo4j is synchronized from JSON, not vice versa |
| Builder isolation problem | Inject existing doctrine list into builder prompt | Prevents ESTABLISHES errors on non-originating cases |
| Kingsfield | One document, two modes | Audit and research require identical schema knowledge |
| MCP exposure | After Kingsfield | Reasoning layer makes exposure meaningful |
| Geographic expansion | U.S. law first, potentially beyond | Con law is the validated MVP, not the ceiling |
| SCDB files | ~/Downloads/ (not in repo) | Too large for git |
| Python environment | fastai310 | Has all dependencies including neo4j package |

---

## Costs (Reference)

| Task | System | Cost |
|------|--------|------|
| Full graph audit (Ring 3, all checks) | NVIDIA free tier | ~$0 |
| Orchestrator (Ring 3 flags → Sonnet) | Claude Sonnet 4.6 | ~$7 per full cycle |
| Builder (per case batch) | Claude Haiku | ~$0.01-0.05 per case |
| Ring 4 prong quality audit | Claude Sonnet 4.6 | ~$2 one-time |

---

*This document is updated at the end of each working session.*
*For narrative history, see docs/journal_entry_*.md*
*For schema specification, see docs/uslawkg_ontology_v04.docx*
*For reasoning layer, see kingsfield.md*
