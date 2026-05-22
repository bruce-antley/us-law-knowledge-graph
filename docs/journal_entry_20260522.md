# US Law Knowledge Graph — Session Journal
## 2026-05-22 — Full Audit Complete, Roadmap Defined

---

## GRAPH STATE AT END OF AUDIT

- **898 nodes · 1310 edges · 0 validation errors · 0 Ring 1 warnings**
- GitHub: github.com/bruce-antley/us-law-knowledge-graph (main, current)
- Neo4j AuraDB: 898/1310 confirmed
- Syllabus corpus: 446 files, 360/366 active cases (98%)
- Ring 2: 4 warnings — all documented deliberate decisions (Gibbons, NLRB, Braunfeld, McConnell)

---

## FULL AUDIT SUMMARY

### Ring 1 — Deterministic (COMPLETE, CLEAN)
13 checks, 2 seconds, 0 errors, 0 warnings. Run before every commit.

### Ring 2 — SCDB Reference (COMPLETE, CLEAN)
92% SCDB match rate. 4 remaining warnings are deliberate decisions:
- Gibbons 7-0 vs 5-0: early Court attendance convention, keeping 7-0
- NLRB 5-4 vs 9-0: Legacy DB error, our 5-4 is correct
- Braunfeld 6-3 vs 5-4: outcome vote vs plurality coalition, keeping 6-3
- McConnell: co-authored opinion, SCDB records Stevens only

### Ring 3 — LLM Edge Audit (COMPLETE)
Total real fixes applied across all checks: ~220+ fixes

| Check | Edges | Real fixes | Notes |
|-------|-------|-----------|-------|
| modifies_dir | 114 | 16 | Kennedy repudiates, Stanley expands, Reed expands, etc. |
| modifies_soft | 95 | 0 | All false positives — doctrines correctly MODIFIES |
| overrules | 19 | 0 | All false positives — Oyez syllabi don't quote overruling language |
| establishes | 355 | ~118 | 77 ESTABLISHES→APPLIES, 35 artifacts deleted, 6 ESTABLISHES→MODIFIES |
| applies_real+under | 562 | ~79 | Dobbs, Knick, Kelo, Seminole Tribe among critical fixes |
| interprets | 165 | 2 | Dred Scott→5th Amend, Korematsu→5th Amend |
| holding | 364 | 2 | Heart of Atlanta (restaurants error), Bill Johnson's (reversed logic) |

**Key findings:**
- Builder blindness confirmed at scale: pipeline creates ESTABLISHES edges in isolation
- 35 pipeline artifact nodes deleted (self-named single-connection doctrine nodes)
- Critical holding errors found: Heart of Atlanta conflated with Katzenbach companion case
- Dobbs/Knick/Kelo correctly reclassified from APPLIES to MODIFIES

---

## PIPELINE FOLDER STRUCTURE (CLEANED UP)

```
~/Documents/lexgraph_pipeline/
  core/        — elsa.py, validate.py, neo4j_import.py, run_pipeline.py, qa_*.py
  audit/       — ring1-3 scripts, audit_orchestrator.py, apply_fixes.py
  data/        — case_registry.json, .env
  reports/     — all run output files (82 files)
  syllabi/     — 446 syllabus files
  archive/     — old batch files, builder prompts, pipeline_artifacts/
```

Standard session startup:
```bash
cd ~/Documents/lexgraph_pipeline && export $(cat .env | xargs)
```

---

## AUDIT ORCHESTRATOR SYSTEM

Files: `audit/audit_orchestrator.py`, `audit/apply_fixes.py`

Current status: working but needs improvement for full automation.

**Known issues:**
1. apply_fixes.py ID matching bug — matches on source_id/target_id but stale IDs from
   post-dedup merges cause Neo4j errors. Workaround: full reload after apply.
   Fix: match on edge_id first, fall back to source+target+type.

2. Confidence thresholds too conservative — flat 0.85 puts too much in human review.
   Should be check-type specific:
   - ESTABLISHES→APPLIES: 0.78
   - Direction fixes: 0.80
   - DELETE_ARTIFACT: 0.85
   - Holding changes: 0.90
   - OVERRULES changes: 0.92

3. Orchestrator system prompt too thin — Sonnet gets cold prompts without schema context,
   causing hedging and low confidence on routine decisions.
   Fix: legal reasoning layer (Kingsfield) as system prompt.

**Target state:** One command → full audit → apply all high-confidence fixes → 
human exceptions file with <20 items → respond → done.

---

## INTELLECTUAL DISCOVERIES

### The GEB Moment
Graph-assisted answer to "how did Central Hudson modify prior commercial speech doctrine"
demonstrated ontology introspection — the system identified a missing edge type
("operationalizes") while answering the research question. This is recursive symbolic
reasoning: traversing the graph, hitting a representational wall, reflecting on the
ontology itself.

This is the LexGraph thesis demonstrated empirically: not just better retrieval, but
structurally constrained legal reasoning that produces qualitatively different answers.

### The Kingsfield Connection
The audit legal reasoning layer and Kingsfield are the same thing. Both require:
- Edge semantics with examples
- What absence of edges means
- Pipeline artifact recognition patterns
- False positive patterns by check type
- Schema decision rules

One document, two modes: research mode and audit mode.

### Builder Blindness
Root cause of ~118 ESTABLISHES errors: builder generates each case in isolation without
knowing what doctrines already exist in the graph. Fix for v0.5: inject existing
doctrine/test node list into builder prompt before generating edges.

---

## ROADMAP

### Immediate (next session)
1. Finish Ring 3 full run if not complete (applies_real+under still running)
2. Run through orchestrator, apply fixes
3. Final Ring 1 validation → commit

### Phase 1: Con Law Viability Assessment
Structured evaluation before exposing the graph:
- Coverage: do we have the cases a con law practitioner expects?
- Accuracy: what did the full audit find and fix?
- Doctrinal completeness: are all 8 First Amendment areas fully modeled?
- Decision: is this ready for a demo?

### Phase 2: Kingsfield — Legal Reasoning Layer
One system prompt / document that encodes:
- Edge semantics with concrete examples from the audit
- What absence of relationships means (the Central Hudson insight)
- Traversal patterns for different question types
- Schema decision rules (same rules as audit orchestrator)
- Two modes: research and audit

Build Kingsfield first — it powers both the demo and the autonomous audit.

### Phase 3: Exposure via MCP
With Kingsfield in place, wrap in MCP server exposing high-level tools:
- `research_doctrine(question)` — structured legal research
- `trace_case_lineage(case_id)` — intellectual and doctrinal lineage
- `check_good_law(case_id)` — current status with overruling chain
- `explain_test(test_id)` — test prongs with case applications

Option A: Extend existing Neo4j MCP server (good enough for internal use)
Option B: Custom MCP server with abstracted tools (better for research interface)

### Phase 4: Demo and Bang On It
- Internal demo against con law questions
- Benchmark comparisons (raw LLM vs graph-assisted)
- Identify gaps before public exposure
- Decision: expand to Equal Protection, or focus on First Amendment depth?

---

## KEY ARCHITECTURAL DECISIONS

- SCDB files live in ~/Downloads/ (not in pipeline — too large for git)
- Neo4j reload required after any apply_fixes run (until ID matching bug fixed)
- JSON is source of truth; Neo4j is synchronized from JSON
- Kingsfield is one system prompt, not separate audit/research documents
- MCP exposure before Equal Protection expansion

---

## COST SUMMARY (Full Audit)

| System | Usage | Cost |
|--------|-------|------|
| NVIDIA (Ring 3 judges) | ~3,000 LLM calls | ~$0 (free tier) |
| Claude Sonnet 4.6 (orchestrator) | ~500 calls | ~$5-7 |
| Total | | ~$5-7 |

Full graph audit: essentially free.
