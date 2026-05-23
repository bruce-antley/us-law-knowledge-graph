# US Law Knowledge Graph — Current State
*Last updated: 2026-05-23 (end of day)*

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

## Roadmap

### Immediate next

**Viability gaps: COMPLETE** ✅
- C14 wrong-syllabus check: integrated into Ring 1, runs automatically
- Cross-area consistency: 12 redundant APPLIES edges removed
- Ring 4 prong quality: 50 fixes (30 scrutiny_level, 15 burden, structural fixes)
- Wrong-syllabus spot-check: 6 cases verified clean

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
