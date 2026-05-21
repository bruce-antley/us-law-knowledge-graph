# US Law Knowledge Graph — Session Journal
## 2026-05-21 (Part 2) — Ring 3 Edge Audit + Orchestrator

---

## GRAPH STATE AT END OF SESSION

- **898 nodes · 1310 edges · 0 validation errors · 0 Ring 1 warnings**
- GitHub: github.com/bruce-antley/us-law-knowledge-graph (main, current)
- Neo4j AuraDB: 898/1310 confirmed (full reload completed)

---

## SESSION WORK COMPLETED

### Ring 3 Edge Audit — modifies_dir (COMPLETE)
- 114 edges checked, 19 flagged, 3 false positives (thin syllabi), 16 real fixes
- Direction fixes: kennedy repudiates, stanley expands, reed expands, lemon expands,
  counterman expands, bonta narrows, alameda_books expands, texas_monthly narrows,
  madsen complicates, turner complicates, 44_liquormart clarifies, arizona_v_hicks narrows
- MODIFIES→APPLIES: Lukumi (should APPLY Smith test), Alexander (should APPLY prior restraint)

### Ring 3 Edge Audit — modifies_soft (COMPLETE)
- 95 edges checked, 3 flagged — all false positives
- Garcia/SFFA/Agostini: judges saw "overruled" in syllabus and flagged MODIFIES/repudiates
  but each already has a correct OVERRULES edge to the case; MODIFIES to doctrine is correct
- Fix: updated prompt to inject already_overrules context so judges don't conflate case vs doctrine

### Ring 3 Edge Audit — establishes (COMPLETE)
- 355 edges checked, 159 flagged, 5 no syllabus
- Root cause confirmed: builder blindness — pipeline creates ESTABLISHES edges in isolation
  without knowing what doctrines already exist in the graph

### Audit Orchestrator (BUILT)
- `audit_orchestrator.py` — reads Ring 3 JSON, calls Claude Sonnet 4.6 with full graph context,
  routes high-confidence decisions to apply_queue.json, ambiguous to human_review.txt
- `apply_fixes.py` — reads apply_queue.json, applies fixes to Neo4j + JSON, validates, logs
- Auto-apply threshold: 0.85 · Human review threshold: 0.60
- Test run (10 flags): 9/10 correct decisions, $0.10 cost
- Full establishes run (159 flags): 80% automation rate, ~$1.50 cost

### Establishes fixes applied:
- 77 ESTABLISHES → APPLIES (cases that applied existing doctrine)
- 35 pipeline artifact nodes deleted (self-named nodes like mcdonald_incorporation_test,
  lorillard_tobacco_narrowly_tailored_test, clark_symbolic_conduct_test, etc.)
- 6 ESTABLISHES → MODIFIES (city_of_boerne, connick, manson, milkovich, obergefell, seminole_tribe)
- 7 KEEP_ESTABLISHES (miranda ×2, gideon, illinois_v_gates, strickland, wade, gall)
- 1 manual override: hosanna_tabor kept as ESTABLISHES (genuine SCOTUS first recognition)
- Penn Central added as true ESTABLISHES for takings_multifactor_test (replacing Arkansas Game & Fish)
- Duncan selective_incorporation: ESTABLISHES → APPLIES (Palko is earlier establisher)
- Orphan nodes cleaned: clark, miller_v_johnson, symbolic_conduct_doctrine,
  racial_gerrymandering_doctrine, clark_symbolic_conduct_test, miller_racial_gerrymandering_test

### Known issue in apply_fixes.py:
- 32 Neo4j errors due to stale case IDs (post-dedup IDs in apply queue didn't match graph)
- Workaround: full Neo4j reload from JSON after apply — JSON is source of truth
- Fix needed: apply_fixes.py should match on edge_id not just source/target ID

---

## PIPELINE FILES

| File | Path |
|------|------|
| Audit orchestrator | `~/Documents/lexgraph_pipeline/audit_orchestrator.py` |
| Apply fixes | `~/Documents/lexgraph_pipeline/apply_fixes.py` |
| Ring 3 edge audit | `~/Documents/lexgraph_pipeline/ring3_edge_audit.py` |
| Ring 1 health check | `~/Documents/lexgraph_pipeline/ring1_health_check.py` |
| Ring 2 SCDB check | `~/Documents/lexgraph_pipeline/ring2_scdb_check.py` |

Standard run sequence:
```bash
cd ~/Documents/lexgraph_pipeline && export $(cat .env | xargs)

# Ring 3 check (one check at a time)
caffeinate -i python3 ring3_edge_audit.py --check applies_real --output ring3_applies_real.txt

# Orchestrator
caffeinate -i python3 audit_orchestrator.py \
  --input ring3_applies_real.json \
  --output-queue apply_queue.json \
  --output-review human_review.txt

# Review human_review.txt, edit apply_queue.json if needed, then:
caffeinate -i python3 apply_fixes.py \
  --queue apply_queue.json \
  --json ~/Downloads/us-law-knowledge-graph/data/conlaw_graph_v02.json \
  --log decision_log.txt

# After apply, always:
python3 ring1_health_check.py
# Then full Neo4j reload if apply had errors
```

---

## AUDIT SYSTEM STATUS

| Ring | Status | Script | Notes |
|------|--------|--------|-------|
| Ring 1 — Deterministic | ✅ COMPLETE | `ring1_health_check.py` | 13 checks, 2s, 0/0 |
| Ring 2 — SCDB reference | ✅ COMPLETE | `ring2_scdb_check.py` | Citation-based |
| Ring 3 — modifies_dir | ✅ COMPLETE | `ring3_edge_audit.py` | 16 fixes applied |
| Ring 3 — modifies_soft | ✅ COMPLETE | `ring3_edge_audit.py` | 0 real findings |
| Ring 3 — establishes | ✅ COMPLETE | `ring3_edge_audit.py` | 118 fixes applied |
| Ring 3 — overrules | ⚠ PARTIAL | `ring3_edge_audit.py` | 4 false positives, syllabus quality issue |
| Ring 3 — applies_real | 🔲 NOT RUN | `ring3_edge_audit.py` | 281 edges |
| Ring 3 — applies_under | 🔲 NOT RUN | `ring3_edge_audit.py` | 281 edges |
| Ring 3 — interprets | 🔲 NOT RUN | `ring3_edge_audit.py` | 165 edges |
| Ring 3 — holding | 🔲 NOT RUN | `ring3_edge_audit.py` | 360 cases |

---

## KEY FINDINGS FROM ESTABLISHES AUDIT

**Builder blindness confirmed at scale:** Pipeline creates ESTABLISHES edges in isolation
without graph context. When a case addresses Topic X, builder defaults to ESTABLISHES
because it doesn't know 15 earlier cases already connect to that doctrine.

**Fix for v0.5 builder:** Before generating edges for a new case batch, inject list of
existing doctrine/test nodes and their establishing cases into builder prompt.
Prompt: "Connect to existing nodes, don't create new ones unless genuinely novel."

**Pipeline artifact pattern:** Self-named doctrine nodes (e.g., `miller_racial_gerrymandering_test`,
`lorillard_tobacco_narrowly_tailored_test`) are reliable signals of pipeline artifacts.
Orchestrator correctly identifies these as DELETE_ARTIFACT with high confidence.

---

## COST SUMMARY (Ring 3 so far)

- Claude Sonnet 4.6: $3/MTok input, $15/MTok output
- Orchestrator (159 flags): ~$1.50
- Total Ring 3 so far: ~$3-4
- Projected full audit (all checks): ~$8-10

---

## IMMEDIATE NEXT STEPS

1. Run `applies_real` check (281 edges) — does case actually apply this doctrine?
2. Run `applies_under` check (281 edges) — should APPLIES be MODIFIES?
3. Run `interprets` check (165 edges)
4. Run `holding` check (360 cases) — most important, highest legal risk
5. Fix apply_fixes.py ID matching bug
6. Folder cleanup (pipeline dir getting messy)
7. Build run_audit_cycle.py — one-command full audit cycle

---

## KNOWN ISSUES TO FIX

1. **apply_fixes.py ID matching bug** — uses source_id/target_id for Neo4j lookup but
   some IDs differ between JSON and Neo4j after dedup merges. Should match on edge_id.
   Workaround: full Neo4j reload after any apply run.

2. **Overrules check syllabus limitation** — Oyez syllabi don't include explicit overruling
   language even when opinions do. Consider using CourtListener full opinion text for
   overrule_type verification instead.

3. **Missing syllabi for ~30 post-2020 cases** — CourtListener/Oyez gaps for recent cases.
   These get skipped in Ring 3 checks.
