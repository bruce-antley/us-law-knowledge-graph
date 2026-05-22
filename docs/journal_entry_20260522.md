# US Law Knowledge Graph — Session Journal
## 2026-05-22 — Full Audit Complete, Orchestrator Built, Folder Cleaned

---

## GRAPH STATE AT END OF SESSION

- **898 nodes · 1310 edges · 0 validation errors · 0 Ring 1 errors · 1 warning (C12)**
- GitHub: committed 0006d68 — "Full Ring 3 audit complete"
- Neo4j AuraDB: 898/1310 confirmed
- Ring 2: 4 warnings — all documented deliberate decisions
- Ring 1 C12 warning: 6 good-law cases with zero outgoing edges (pre-existing, deferred)

---

## FULL AUDIT SUMMARY

### Ring 1 — Deterministic (COMPLETE, CLEAN)
13 checks, 2 seconds, 0 errors, 0 warnings (except C12 pre-existing).

### Ring 2 — SCDB Reference (COMPLETE, CLEAN)
92% match rate. 4 deliberate decisions retained:
- Gibbons 7-0 vs 5-0: early Court attendance convention
- NLRB 5-4 vs 9-0: Legacy DB error, 5-4 is correct
- Braunfeld 6-3 vs 5-4: outcome vote vs plurality coalition
- McConnell: co-authored opinion, keeping "Stevens and O'Connor"

### Ring 3 — LLM Edge Audit (COMPLETE)
~220 real fixes across all check types.

| Check | Edges | Real fixes | Key findings |
|-------|-------|-----------|--------------|
| modifies_dir | 114 | 16 | Kennedy repudiates, Stanley/Reed expand, etc. |
| modifies_soft | 95 | 0 | All false positives — doctrines correctly typed |
| overrules | 19 | 0 | Oyez syllabi don't quote overruling language |
| establishes | 355 | ~118 | 77 ESTABLISHES→APPLIES, 35 artifacts deleted |
| applies_real+under | 562 | ~79 | Dobbs, Knick, Kelo, Seminole Tribe fixed |
| interprets | 165 | 2 | Dred Scott→5th Amend, Korematsu→5th Amend |
| holding | 364 | 2 | Heart of Atlanta (restaurants error), Bill Johnson's (reversed logic) |

---

## PIPELINE FOLDER STRUCTURE (CLEANED)

```
~/Documents/lexgraph_pipeline/
  core/        — elsa.py, validate.py, neo4j_import.py, run_pipeline.py, qa_*.py
  audit/       — ring1-3 scripts, audit_orchestrator.py, apply_fixes.py (patched)
  data/        — case_registry.json, .env
  reports/     — all run output files
  syllabi/     — 446 files
  archive/     — pipeline_artifacts/ (drafts, needs_attention, review_queue, old batches)
```

Standard session startup:
```bash
cd ~/Documents/lexgraph_pipeline && export $(cat .env | xargs)
```

Neo4j reload (no --password needed after patch):
```bash
echo "yes" | caffeinate -i /Users/bruceantley/anaconda3/envs/fastai310/bin/python \
  core/neo4j_import.py \
  --file ~/Downloads/us-law-knowledge-graph/data/conlaw_graph_v02.json --wipe
```

---

## AUDIT ORCHESTRATOR SYSTEM

Files: `audit/audit_orchestrator.py`, `audit/apply_fixes.py`

### apply_fixes.py — 4 bugs fixed this session:
1. **ID matching bug** — now matches on edge_id alone in Neo4j (not source+target ID)
   This was the root cause of ~32 errors per apply run and all post-run cleanup work
2. **Duplicate prevention** — tracks applied_edge_ids to skip duplicates in same run
3. **Pre-write deduplication** — deduplicates edges in JSON before writing
4. **actual_src/actual_tgt** — uses actual IDs from Neo4j query, not stale apply queue IDs

### Remaining orchestrator issues to address in automation session:
- Check-type specific confidence thresholds (currently flat 0.85 — too conservative)
  Target: 0.78 ESTABLISHES→APPLIES, 0.80 direction, 0.85 DELETE_ARTIFACT, 0.90 holding
- run_audit_cycle.py — single command for full audit cycle
- Orchestrator system prompt needs Kingsfield context to raise confidence on clear decisions

---

## INTELLECTUAL DEVELOPMENTS

### The GEB Moment (central insight of this session)
Graph-assisted answer to Central Hudson query demonstrated ontology introspection:
the system identified a missing "operationalizes" edge type while answering a
research question. This is the LexGraph thesis demonstrated empirically.

ChatGPT analysis: "This may be the first example where I'd say I can clearly see the
distinctive reasoning contribution of the graph. Not retrieval enhancement or citation
enrichment, but semantic role enforcement, doctrinal topology awareness, and
ontology-sensitive reasoning."

The graph answer was not merely more detailed. It was structurally constrained by
explicit doctrinal relationships — exactly the LexGraph thesis.

### Kingsfield = Audit Layer
The audit legal reasoning layer and Kingsfield research interface are the same document
in two modes. Both require identical knowledge: edge semantics, absence-of-edge meaning,
pipeline artifact patterns, false positive patterns, schema decision rules.
Build once, use in two modes.

### Builder Blindness
Root cause of ~118 ESTABLISHES errors confirmed at scale. Fix for v0.5 builder:
inject existing doctrine/test node list into builder prompt before generating edges.

---

## VIABILITY ASSESSMENT FRAMEWORK

### Graph-only viability (before Kingsfield)

| Dimension | Status | Notes |
|-----------|--------|-------|
| Structural integrity | ✅ Pass | Ring 1 clean |
| Edge type accuracy | ✅ Pass | 220+ fixes applied, ~5% residual |
| Holding text accuracy | ✅ Pass | 0.5% error rate (2/364) |
| Prong quality | ❓ Not audited | Ring 4 needed |
| Coverage (1A areas) | ✅ Pass | Treatise depth |
| Wrong-syllabus cases | ❓ ~15 unaudited | C14 + spot-check needed |
| Cross-area consistency | ❓ Not checked | Cypher audit needed |

### Four remaining viability gaps:
1. **C14 check** — add wrong-syllabus detection to Ring 1 (deterministic)
2. **Cross-area consistency** — Cypher queries, one-time audit
3. **Prong quality** — Ring 4 LLM binary (~$2, 30 min, runs on DoctrinalTest additions)
4. **Wrong-syllabus spot-check** — manual review of ~15 cases

---

## ROADMAP

### Next session (Priority 1): Audit automation
Build `run_audit_cycle.py` — single command for full audit:
Ring 1 → Ring 2 → Ring 3 → orchestrate → apply → validate → reload → commit
Human touchpoint: exceptions file only (target <20 items)

### Session after (Priority 2): Viability gaps
C14 + cross-area consistency + prong Ring 4 + wrong-syllabus spot-check
Closes all foundation gaps before building on top

### Priority 3: Kingsfield
One document (~500-800 lines), two modes:

Section 1: Graph identity and purpose
Section 2: Node types with semantics
Section 3: Edge semantics with examples — the intellectual core
  - ESTABLISHES vs APPLIES vs MODIFIES distinction with concrete examples
  - What absence of each edge type means
  - OVERRULES explicit vs implicit vs effective
  - INTELLECTUALLY_PRECEDES for non-binding influence
Section 4: What absence means (the Central Hudson insight formalized)
Section 5: Traversal patterns by question type
Section 6: Schema limitations to disclose
Section 7: Audit mode rules (same knowledge, different output)

Build order: Sections 1-4 first (semantics, requires careful drafting).
Test: rerun Central Hudson query with Kingsfield as system prompt.
Success criterion: answer is more precise, more confident, correctly reasons
about absence of MODIFIES edge.

### Priority 4: MCP exposure
With Kingsfield in place, wrap in MCP server.
Tools: research_doctrine, trace_case_lineage, check_good_law, explain_test
Option A: extend existing Neo4j MCP (good enough internally)
Option B: custom MCP with abstracted tools (better for research interface)
Decision: defer until Kingsfield is proven

### Priority 5: Demo
Internal first. Benchmark questions:
- Lineage: "Trace the clear and present danger test from Schenck to Brandenburg"
- Current law: "What is the governing standard for commercial speech restrictions?"
- Modification history: "How has Kennedy v. Bremerton changed Establishment Clause doctrine?"
- Good law: "Is Lemon v. Kurtzman still good law?"
- Failure mode test: ask about cases not in the graph — does it correctly say so?

---

## COST SUMMARY (Full Audit)

| System | Usage | Cost |
|--------|-------|------|
| NVIDIA (Ring 3 judges, 3 models) | ~3,200 LLM calls | ~$0 (free tier) |
| Claude Sonnet 4.6 (orchestrator) | ~600 calls | ~$7 |
| Total | Full audit of 898 nodes / 1310 edges | ~$7 |

---

## KEY COMMANDS REFERENCE

```bash
# Full session startup
cd ~/Documents/lexgraph_pipeline && export $(cat .env | xargs)

# Ring 1 (deterministic, 2 seconds)
python3 audit/ring1_health_check.py

# Ring 2 (SCDB reference)
caffeinate -i python3 audit/ring2_scdb_check.py \
  --scdb ~/Downloads/SCDB_2025_01_caseCentered_Citation.csv \
  --scdb-legacy ~/Downloads/SCDB_Legacy_07_caseCentered_Citation.csv \
  --output reports/ring2_$(date +%Y%m%d).txt

# Ring 3 (all checks, ~45 min)
caffeinate -i python3 audit/ring3_edge_audit.py --check all \
  --output reports/ring3_full_$(date +%Y%m%d).txt

# Orchestrator
caffeinate -i python3 audit/audit_orchestrator.py \
  --input reports/ring3_full_$(date +%Y%m%d).json \
  --output-queue reports/apply_queue.json \
  --output-review reports/human_review.txt

# Apply fixes (dry run first)
python3 audit/apply_fixes.py \
  --queue reports/apply_queue.json \
  --json ~/Downloads/us-law-knowledge-graph/data/conlaw_graph_v02.json \
  --dry-run

# Neo4j reload
echo "yes" | caffeinate -i /Users/bruceantley/anaconda3/envs/fastai310/bin/python \
  core/neo4j_import.py \
  --file ~/Downloads/us-law-knowledge-graph/data/conlaw_graph_v02.json --wipe

# Git commit
cd ~/Downloads/us-law-knowledge-graph
git commit -a -m "Audit cycle: [date] — [summary]"
git push
```
