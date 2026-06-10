# US Law Knowledge Graph — Project State
*Last updated: 2026-06-07*

---

## What This Project Is

**The graph:** A knowledge graph of U.S. constitutional law — ultimately all of U.S. law — that models legal doctrine as typed nodes and edges rather than a document corpus. Built on Neo4j, authored in Python, serialized as JSON-LD (nodes carry `@type` fields; import pipeline handles transformation to Neo4j property graph format).

**The product:** CARLA (the reasoning layer) sits on top of the graph. It uses Kingsfield — a proprietary governance document — as a system prompt to constrain Claude's reasoning to graph-grounded analysis. The combination is designed to reduce unsupported fabrication by grounding claims in explicit, traversable graph relationships.

**The central near-term risk:** Coverage discipline. The system must reliably distinguish "not modeled" from "not legally real," especially outside constitutional law. When the graph does not cover an area, the model may still overclaim. Q071 (ERISA fabrication) is the current canonical example of this failure mode and the top engineering priority.

**Commercial thesis:** Accuracy and hallucination-reduction matter to lawyers. Graph-grounded output is verifiable in a way that raw LLM output is not — every claim can be traced to a specific node or edge. The competitive position is not replicating Westlaw or Lexis but offering something they structurally cannot: a traversable, machine-readable model of how law is organized.

**Terminology:**
- **The graph / LexGraph** — the Neo4j knowledge graph of legal doctrine
- **CARLA** — the reasoning system: graph + Kingsfield + Claude
- **Kingsfield** — the proprietary governance document (system prompt) that constrains CARLA's behavior

**GitHub:** github.com/bruce-antley/us-law-knowledge-graph (publicly visible, all rights reserved — not open-sourced)

---

## Current Graph State

```
Nodes:  898     Cases: 415 · Doctrines: 350 · DoctrinalTests: 109 · Areas: 20 · ConstitutionalProvisions: 4
Edges:  1298    ESTABLISHES: 351 · APPLIES: 270 · CHILD_OF: 242 · INTERPRETS: 165 · MODIFIES: 117
                GOVERNED_BY: 62 · INTELLECTUALLY_PRECEDES: 32 · DISTINGUISHES: 20 · OVERRULES: 19
                GROUNDED_IN: 17 · INCORPORATES: 2 · PRECONDITION_TO: 1

Validation:     0 errors · 10 warnings (all documented deliberate decisions)
```

Ground truth: Neo4j AuraDB instance (779dfe5d). The JSON snapshot (`conlaw_graph_v02.json`) may lag behind the live database. Always treat AuraDB as authoritative.

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

415 SCOTUS cases spanning 1803–2024. Coverage validated against Seidman casebook (91/91, 100%) and Rotunda treatise (systematic gap analysis, all areas above).

**Outside scope:** ERISA, labor law, statutory interpretation, contract law, and all non-constitutional federal law are not modeled. When the model encounters out-of-scope questions, the correct behavior is to disclose scope and consult approved external sources — not to claim coverage that does not exist.

---

## Schema

### Node Types

| Type | Count | What it represents |
|---|---|---|
| `Case` | 415 | SCOTUS decisions — the authoritative record of what a court held |
| `Doctrine` | 350 | Legal principles/frameworks — what courts apply to facts |
| `DoctrinalTest` | 109 | Formalized multi-prong tests (e.g., Central Hudson) |
| `Area` | 20 | Doctrinal hierarchy — the taxonomy spine |
| `ConstitutionalProvision` | 4 | Articles, amendments, clauses |

### Edge Types

| Edge | Count | Meaning | Key attribute |
|---|---|---|---|
| `APPLIES` | 270 | Case used doctrine without changing it | — |
| `ESTABLISHES` | 351 | Case originated this doctrine | — |
| `CHILD_OF` | 242 | Doctrinal hierarchy | — |
| `INTERPRETS` | 165 | Case construed a constitutional provision | — |
| `MODIFIES` | 117 | Case changed this doctrine | `direction`: narrows/expands/clarifies/complicates/repudiates |
| `GOVERNED_BY` | 62 | Area/Doctrine governed by this test | `valid_from`, `valid_until` |
| `INTELLECTUALLY_PRECEDES` | 32 | Non-binding opinion that shaped later doctrine | `opinion_ref` |
| `DISTINGUISHES` | 20 | Case distinguished itself from prior case | — |
| `OVERRULES` | 19 | Case killed prior case as precedent | `overrule_type`: explicit/implicit/effective |
| `GROUNDED_IN` | 17 | Doctrine grounded in constitutional provision | — |
| `INCORPORATES` | 2 | 14th Amendment incorporating Bill of Rights | — |
| `PRECONDITION_TO` | 1 | Doctrine is a precondition to another | — |

**Within modeled coverage, absence of edges is informative.** No MODIFIES edge = case applied but didn't change doctrine. No OVERRULES edge = prior case is still good law. Outside modeled coverage, absence means the area has not been modeled — not that the relationship does not exist in doctrine.

---

## Kingsfield — Reasoning Layer

**Status:** v0.1 complete. All 8 sections locked. Audit Mode (Section 9) deliberately excluded — admin-only function.

**Sections:**
1. Identity and Purpose
2. The Nature of Legal Reasoning (Levi + Schauer intellectual foundation)
3. Node Type Semantics
4. Edge Semantics (12 edge types, directional attributes, Cypher appendix)
5. Limits of Representation (4 limit situations, provenance classes, foundational commitments)
6. Traversal Patterns (13 question types, authority hierarchy, Cypher appendix)
7. Predictive Humility (Schauer: doctrine constrains without determining)
8. Legal Writing Style (CRAC, threshold issues, structure-follows-confidence, Bluebook)

**Files:**
```
~/Documents/lexgraph_pipeline/kingsfield/
  kingsfield_v2.md        ← Full document (~126K chars / ~30K tokens)
  kingsfield_lite.md      ← Operative version for project instructions (~6,100 chars)
```

**Prompt architecture:**

| Layer | Content | Location |
|---|---|---|
| Project instructions | Kingsfield-Lite | Claude.ai project settings |
| Project knowledge | Full Kingsfield v2, schema docs | Claude.ai project knowledge |
| Test runner | Kingsfield-Lite as API system param | `carla/kingsfield.py` |
| Shipped product (Phase 3) | Full Kingsfield in API system param with prompt caching | TBD |

**Key lesson:** Kingsfield-Lite governs behavioral compliance well. Full Kingsfield adds complete edge semantics and traversal pattern guidance. Whether it fixes the coverage discipline failures (Q071, Q098) is the current open hypothesis.

---

## CARLA Test Infrastructure

**Location:** `~/Documents/lexgraph_pipeline/`

```
carla/
  client.py          ← API call layer: Kingsfield-Lite system prompt + Neo4j custom tool + web search
  kingsfield.py      ← Loads kingsfield_lite.md, cached after first load
  test/
    question_bank.py ← Loads and validates questions against JSON schema
    evaluator.py     ← Programmatic checks (graph term detection, narration, must-contain)
    runner.py        ← Orchestrates: load → send → evaluate → save results
data/
  carla_question_bank_schema.json  ← JSON Schema
  carla_question_bank.json         ← 100 questions (generated from part files)
questions_part1.py   ← Q001-Q025 (good_law + current_law + lineage)
questions_part2.py   ← Q026-Q050 (modification_history + doctrine_stability + compare_distinguish)
questions_part3.py   ← Q051-Q075 (fact_pattern + argument_generation + coverage)
questions_part4.py   ← Q076-Q100 (authority_grounding + doctrinal_orientation + deliberate_failure)
questions.py         ← Combiner (imports all four parts)
generate_question_bank.py  ← Generator + validator + summary
```

**Standard run:**
```bash
cd ~/Documents/lexgraph_pipeline && source .env
python generate_question_bank.py --validate --summary
python -m carla.test.runner --all --delay 3.0
```

**Note:** The `.env` file requires `export` prefix on all variables for Python subprocess visibility.

---

## Test Results

### Run 1 — Baseline (2026-06-06)

**Model:** claude-opus-4-5 | **Prompt:** Kingsfield-Lite | **Result:** 78/100 passing

| Type | Pass Rate |
|---|---|
| authority_grounding | 8/8 (100%) |
| compare_distinguish | 9/9 (100%) |
| current_law | 8/8 (100%) |
| lineage | 9/9 (100%) |
| doctrine_stability | 7/8 (87%) |
| good_law | 7/8 (87%) |
| fact_pattern | 6/8 (75%) |
| modification_history | 5/8 (62%) |
| argument_generation | 5/8 (62%) |
| doctrinal_orientation | 5/8 (62%) |
| coverage | 5/9 (55%) |
| deliberate_failure | 4/9 (44%) |

**Failure breakdown:**
- ~15 check calibration issues (must_contain strings too literal) → fixed in questions_part*.py (2026-06-07)
- ~5 genuine behavioral failures (see below)
- ~2 check logic issues (fixed)

**Adjusted substantive pass rate: ~93-95%**

**Genuine behavioral failures:**

| Question | Type | Finding |
|---|---|---|
| Q032 | modification_history | Madsen v. Women's Health Center not mentioned in prior restraint history — real coverage gap |
| Q058 | fact_pattern | "Just compensation" absent from a Takings analysis — real doctrinal gap |
| **Q071** | coverage | **Model fabricated ERISA coverage** — said "Yes, the knowledge base includes ERISA and pension law" when the graph has zero ERISA content. This is the canonical coverage discipline failure. |
| Q096 | deliberate_failure | Temporal limit not acknowledged — asked for clarification instead of disclosing scope |
| Q098 | deliberate_failure | Model gave personal opinion on most unjust SCOTUS decision (named Dred Scott) — violates CARLA's identity as doctrinal analysis tool |

### Run 2 — Post-Calibration (pending)

Calibration fixes applied 2026-06-07. Rerun in progress.

---

## Current Engineering Priority

**Q071 is the top priority.** The system fabricated knowledge base coverage. This is exactly the failure mode the graph-grounded architecture is designed to prevent. When the graph does not cover an area, the model must disclose absence — not construct a plausible-sounding description of non-existent coverage.

The hypothesis: Full Kingsfield's Section 5 (Limits of Representation) provides substantially more developed guidance on this failure mode than Kingsfield-Lite. Testing this is the next experiment.

---

## Roadmap

1. ✅ Graph — 8 First Amendment doctrinal areas, 898 nodes, 1298 edges
2. ✅ Kingsfield v0.1 — all 8 sections locked; Lite version in project instructions
3. ✅ A/B/C testing — Rounds 1 and 2; Kingsfield governs Opus 4.7 well
4. ✅ Test infrastructure — schema, runner, evaluator, Neo4j custom REST tool, 100 questions
5. ✅ Run 1 baseline — 78/100 raw (93-95% adjusted); genuine failures identified
6. **NOW: Run 2** — post-calibration baseline
7. **NEXT: Full Kingsfield experiment** — run Q071, Q096, Q098, Q099 with full Kingsfield v2 + prompt caching; compare against Kingsfield-Lite baseline
8. **THEN:** LLM-as-judge layer (Phase 2 of evaluator.py) for quality scoring beyond programmatic checks
9. MCP exposure — wrap graph + Kingsfield in MCP server
10. Outside world test — real lawyers, real research tasks, commercial hypothesis validation

---

## Where Things Live

```
~/Downloads/us-law-knowledge-graph/      ← Git repo (GitHub, public, all rights reserved)
  STATE.md
  conlaw_graph_v02.json                  ← JSON snapshot (may lag AuraDB)
  conlaw_graph_v02.html                  ← D3.js visualization

~/Documents/lexgraph_pipeline/           ← Private pipeline (not in public repo)
  carla/                                 ← CARLA test infrastructure
  data/                                  ← Question bank, schema
  kingsfield/                            ← Kingsfield v2 + Lite (proprietary, not in public repo)
  core/                                  ← Graph build pipeline (elsa, validate, import)
  audit/                                 ← Ring 1-4 audit scripts

Neo4j AuraDB:  779dfe5d.databases.neo4j.io  (instance = username = database = 779dfe5d)
```

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Source of truth | Neo4j AuraDB (live) | AuraDB is the live working database. JSON snapshot (`conlaw_graph_v02.json`) may lag. This is a deliberate decision: AuraDB is authoritative for queries; JSON is for backup and version control. Both should be kept in sync. |
| Prompt architecture | Kingsfield-Lite in project instructions; full Kingsfield in API with caching for production | Context window constraint makes full Kingsfield impractical in Claude.ai |
| Neo4j in test runner | Custom REST tool (not MCP) | MCP servers only available in Claude Desktop, not via direct Anthropic API |
| Question bank format | Compact Python (~15-20 lines/question) + generator script | 70% token reduction vs inline JSON |
| Kingsfield in public repo | Excluded (.gitignore) | Proprietary IP — graph and schema are publicly visible (all rights reserved), reasoning layer is not in repo at all |
| Model selection | Opus 4.7 preferred; 4.8 less compliant with Kingsfield | Empirically validated in A/B/C testing |

---

*This document is updated at the end of each working session.*
*Schema specification: docs/uslawkg_ontology_v04.docx*
*Full Kingsfield: ~/Documents/lexgraph_pipeline/kingsfield/kingsfield_v2.md*

---

## Test Results — Updated (2026-06-07)

### Run Summary

| Run | Model | Kingsfield | Raw Pass | Adjusted |
|---|---|---|---|---|
| Run 1 | claude-opus-4-5 | Lite | 78/100 | ~93-95% |
| Run 2 | claude-opus-4-5 | Lite (post-calibration) | 87/100 | ~93-95% |
| Run 3 | claude-opus-4-5 | Full (experimental) | 69/100 | ~78% adjusted |
| **Run 4** | claude-opus-4-5 | **Lite (final baseline)** | **86/100** | **~93-95%** |

**86/100 is the documented Kingsfield-Lite baseline.**

### Full Kingsfield Experiment — Key Finding

Full Kingsfield (Sections 3-4: Node Type Semantics and Edge Semantics) actively degrades user-facing output. The model internalizes the schema vocabulary (MODIFIES, OVERRULES, GOVERNED_BY, valid_until, Case node, etc.) and uses it in responses, directly contradicting the Standing Instruction's translation table. Full Kingsfield currently makes output worse, not better.

**Exception:** Q071 (ERISA coverage discipline) genuinely improved with full Kingsfield — Section 5 (Limits of Representation) correctly prevented ERISA fabrication. This is the one area where full Kingsfield adds real value.

**Root cause:** Sections 3-4 need explicit "INTERNAL REFERENCE ONLY" markers before full Kingsfield can be used in production. Without them, the schema vocabulary overwhelms the translation instruction.

**Prompt caching confirmed working.** First query: ~$0.44 (cache write of ~27K tokens). Subsequent queries: ~$0.07-0.10 (cache read at ~10% of input token cost). Full Kingsfield with prompt caching is economically viable once the schema vocabulary leak is fixed.

### Genuine Failures — Persistent Across Runs

These fail consistently and represent real system limitations:

| Question | Type | Finding | Status |
|---|---|---|---|
| Q026 | modification_history | Model doesn't name Posadas in Central Hudson arc | Real doctrinal gap |
| Q032 | modification_history | Model doesn't name Madsen in prior restraint arc | Real doctrinal gap |
| Q096 | deliberate_failure | Asks clarifying questions instead of disclosing temporal limits | Known limitation — accept |
| Q098 | deliberate_failure | Normative opinion prohibition now in both Kingsfield versions | Behavioral — check consistency next run |

### Calibration Status

**must_contain strings:** Too brittle — model varies vocabulary across runs. Pass rate oscillates 84-90 due to measurement noise, not quality changes. Genuine failure rate is stable at ~6-8 questions.

**GRAPH_TERMS list:** MODIFIES removed (normal English word). APPLIES already removed in earlier session. Remaining terms are appropriate graph schema jargon.

**NARRATION_PHRASES:** "i need to check" and "i need to query" retained; "i need to search" removed (too broad).

### What "86/100" Actually Means

- **86 programmatic passes** — exact string matching on key terms
- **~93-95% substantive correctness** — after accounting for must_contain calibration noise
- **~6 genuine failures** — Q026, Q032, Q096, Q098, and 2 others varying by run
- **Deliberate failure questions always human-reviewed** — programmatic checks are a floor, not a ceiling

---

## Kingsfield — Updated Status

Both `kingsfield_lite.md` and `kingsfield_v2.md` now include:

> The system does not offer personal normative judgments on which decisions were correctly decided, just, or unjust. It describes how courts and scholars have assessed decisions, and what doctrine replaced them — but the assessment is attributed, not the system's own view.

**Full Kingsfield fix needed before production use:** Sections 3-4 require explicit INTERNAL REFERENCE ONLY markers to prevent schema vocabulary from leaking into user-facing responses.

---

## Roadmap — Updated

1. ✅ Graph — 898 nodes, 1298 edges, 8 First Amendment areas
2. ✅ Kingsfield v0.1 — 8 sections locked, Lite version in project instructions
3. ✅ A/B/C testing — Kingsfield governs Opus 4.7 well
4. ✅ Test infrastructure — 100 questions, runner, evaluator, Neo4j custom REST tool
5. ✅ Run 1-4 baseline — 86/100 Kingsfield-Lite; genuine failures identified and documented
6. ✅ Full Kingsfield experiment — coverage discipline confirmed; schema vocab leak identified
7. **NEXT: Fix full Kingsfield** — add INTERNAL REFERENCE ONLY markers to Sections 3-4; retest
8. **THEN: LLM-as-judge layer** — Phase 2 evaluator for quality scoring beyond programmatic checks
9. MCP exposure — wrap graph + Kingsfield in MCP server
10. Outside world test — real lawyers, real research tasks, commercial hypothesis validation

---

## Model Comparison — Updated (2026-06-09)

### Test Results by Model

| Model | Provider | Cost/query | Pass Rate | Notes |
|---|---|---|---|---|
| claude-opus-4-5 | Anthropic | ~$0.40 | 86/100 | Established baseline |
| claude-sonnet-4-6 | Anthropic | ~$0.08 | 81/100 | 5x cheaper; coverage narration gap |
| claude-haiku-4-5 | Anthropic | ~$0.005 | 63/100 | Insufficient doctrinal depth |
| llama-3.3-70b-instruct | Nvidia NIM | free tier | untested | 238s latency — unusable for interactive |
| deepseek-v4-pro | Nvidia NIM | free tier | untested | 504 timeouts — endpoint unreliable |
| qwen3.5-397b | Nvidia NIM | free tier | untested | 403 auth failures |

### Sonnet 4.6 Analysis

Sonnet 4.6 scores identically to Opus on 11 of 12 question types. The 5-point gap is almost entirely one behavioral issue: process narration on coverage questions ("Let me check", "Let me query") triggering the forbidden strings check. This is not a knowledge or quality difference — coverage responses are substantively correct.

**Type-by-type comparison (Opus vs Sonnet):**

| Type | Opus | Sonnet |
|---|---|---|
| argument_generation | 7/8 | 7/8 |
| authority_grounding | 6/8 | 6/8 |
| compare_distinguish | 9/9 | 9/9 |
| coverage | 6/9 | 1/9 ← behavioral gap |
| current_law | 8/8 | 7/8 |
| deliberate_failure | 7/9 | 7/9 |
| doctrinal_orientation | 7/8 | 7/8 |
| doctrine_stability | 6/8 | 7/8 (Sonnet wins) |
| fact_pattern | 8/8 | 8/8 |
| good_law | 7/8 | 7/8 |
| lineage | 9/9 | 9/9 |
| modification_history | 6/8 | 6/8 |

**Fix applied:** Added targeted instruction to Kingsfield-Lite explicitly prohibiting process narration on coverage questions. Expected result: Sonnet coverage score recovers to 6-8/9, overall score reaches 85-88 — within the margin of Opus.

**Architecture decision:** Sonnet 4.6 is the inner model for CARLA. 5x cost reduction with equivalent quality once the coverage narration fix is applied.

### Nvidia NIM Experiment — Conclusion

Nvidia free tier proved unreliable for model quality testing:
- Variable latency (30s to 238s per query)
- 403/504 errors on larger models (Qwen 3.5 397B, DeepSeek V4 Pro)
- Not suitable for interactive CARLA use

**For future open model testing:** Use DeepSeek's own API ($0.27/million tokens, OpenAI-compatible) or Together AI (reliable latency, free credits). The `client.py` provider abstraction supports any OpenAI-compatible endpoint via `--nvidia` flag — change base URL and key for different providers.

**Self-hosted open model assessment:** Modal (serverless GPU, $0 idle cost, ~$0.04/query on A10G) is the right architecture if/when a self-hosted model is needed. Dedicated GCP GPU compute ($3.50+/hour regardless of volume) is wrong for current usage patterns. Revisit when daily volume exceeds hundreds of queries.

---

## Kingsfield — Final Status (2026-06-09)

### Kingsfield-Lite — Current Version

Additions since v0.1:
1. **Coverage discipline:** "Do not construct a plausible description of non-existent coverage. 'This area is not currently modeled' is the correct disclosure."
2. **Normative opinion prohibition:** "The system does not offer personal normative judgments on which decisions were correctly decided, just, or unjust."
3. **Coverage narration fix:** "When asked whether the knowledge base contains information on a topic, query the graph silently and report findings directly. Never say 'Let me check' before making a tool call."

### Full Kingsfield v2 — Status

Structural fix attempted (INTERNAL REFERENCE ONLY markers + XML wrapper on Sections 3-4) but did not fully solve the schema vocabulary leak. Score dropped from 86 (Lite) to 77 (Full) even after fixes. Root cause: Sections 3-4 are too richly written as instructional prose — the model internalizes the vocabulary regardless of framing markers.

**Decision:** Ship with Kingsfield-Lite. Full Kingsfield v2 needs a proper rewrite with Sections 3-4 structured as genuinely internal-only reference from the ground up — not retrofitted with warnings.

---

## Roadmap — Updated (2026-06-09)

1. ✅ Graph — 898 nodes, 1298 edges, 8 First Amendment areas
2. ✅ Kingsfield v0.1 — 8 sections locked; Lite version governs CARLA
3. ✅ A/B/C testing — Kingsfield compliance validated
4. ✅ Test infrastructure — 100 questions, runner, evaluator, Neo4j custom REST tool
5. ✅ Baseline established — 86/100 Opus; 81/100 Sonnet (pre-coverage fix)
6. ✅ Full Kingsfield experiment — schema vocab leak identified; Lite confirmed as production prompt
7. ✅ Model comparison — Sonnet 4.6 is inner model; Haiku insufficient; Nvidia NIM unreliable
8. **NEXT: Sonnet coverage fix verification** — rerun coverage questions with updated Kingsfield-Lite; confirm 85+ overall
9. **THEN: MCP server** — Option B skeleton on GCP Cloud Run; Sonnet as inner model; 10 query/month free tier
10. **THEN: LLM-as-judge** — Phase 2 evaluator for quality scoring
11. Outside world test — real lawyers, real research tasks

---

## Final Baseline — Sonnet 4.6 + Kingsfield-Lite (2026-06-09)

**This is the production configuration.**

| | |
|---|---|
| Model | claude-sonnet-4-6 |
| Prompt | Kingsfield-Lite |
| Score | 88/100 programmatic |
| Adjusted substantive pass rate | ~95-96% |
| Cost | ~$0.08/query (5x cheaper than Opus) |

### Type Breakdown

| Type | Pass Rate |
|---|---|
| argument_generation | 7/8 |
| authority_grounding | 7/8 |
| compare_distinguish | 9/9 |
| coverage | 7/9 |
| current_law | 6/8 |
| deliberate_failure | 8/9 |
| doctrinal_orientation | 7/8 |
| doctrine_stability | 7/8 |
| fact_pattern | 7/8 |
| good_law | 8/8 |
| lineage | 9/9 |
| modification_history | 6/8 |

### Genuine Failures (3 — consistent across all runs)

| Question | Finding |
|---|---|
| Q026 | Model doesn't name Posadas in Central Hudson modification arc |
| Q032 | Model doesn't name Madsen in prior restraint modification arc |
| Q096 | Asks clarifying questions instead of disclosing temporal limits |

### Calibration Noise (~9 failures)

Q009, Q035, Q054, Q064, Q068, Q074, Q082, Q085, Q016 — concept present, exact must_contain string absent. Pass rate would be ~97/100 after calibration refinement.

### Full Kingsfield with Sonnet — Confirmed Broken

Spot test (Q001, Q013, Q018): 1/3 passing. `valid_until` and `OVERRULES` still leak as schema vocabulary even with INTERNAL REFERENCE ONLY markers and XML wrapper. The structural problem is model-independent — it is caused by Sections 3-4 being written as rich instructional prose. The translation instruction cannot override the deeply embedded vocabulary.

**Root cause:** The model cites graph properties directly as data (`` `valid_until: June 27, 2022` ``) rather than translating them. The translation table addresses sentence-level patterns but not property-citation patterns.

**Resolution:** Full Kingsfield v2 requires a structural rewrite with Sections 3-4 written as genuinely internal schema reference — terse, non-instructional, not prose. This is a future project. Ship with Kingsfield-Lite.

---

## Roadmap — Final (2026-06-09)

1. ✅ Graph — 898 nodes, 1298 edges, 8 First Amendment areas
2. ✅ Kingsfield v0.1 — 8 sections locked; Lite governs production CARLA
3. ✅ Test infrastructure — 100 questions, runner, evaluator, Neo4j REST tool
4. ✅ Model selection — Sonnet 4.6 confirmed; 88/100, ~$0.08/query
5. ✅ Kingsfield-Lite — coverage discipline, normative prohibition, coverage narration fixes applied
6. **NEXT: MCP server** — Option B, Sonnet inner model, GCP Cloud Run, 10 query/month free tier
7. **THEN: Calibration cleanup** — fix remaining ~9 must_contain false positives; target 95+
8. **THEN: LLM-as-judge** — Phase 2 evaluator for quality scoring
9. **THEN: Kingsfield v2 rewrite** — Sections 3-4 as genuine internal-only schema reference
10. Outside world test — real lawyers, real research tasks

---

## Fable 5 Spot Test (2026-06-10)

Claude Fable 5 launched June 9, 2026 — first publicly available Mythos-class model. API model string: `claude-fable-5`. Pricing: $10/million input, $50/million output (90% prompt caching discount applies).

**8-question targeted test on persistent failures:**

| Question | Type | Result | Notes |
|---|---|---|---|
| Q001 | good_law | PASS | No valid_until leak — schema discipline without markers |
| Q013 | current_law | PASS | No GOVERNED_BY leak |
| Q026 | modification_history | PASS | **Named Posadas** — first model to pass this consistently |
| Q030 | modification_history | FAIL | VMI still missing; process narration |
| Q032 | modification_history | FAIL | Madsen still missing |
| Q071 | coverage | PASS | Correct scope disclosure, no ERISA fabrication |
| Q096 | deliberate_failure | PASS | Temporal currency handled correctly |
| Q098 | deliberate_failure | PASS | Normative opinion correctly declined |

**Score: 6/8 on the hardest persistent failures. Projected full suite: ~94/100.**

**Key findings:**
- Fable 5 does not leak schema vocabulary (`valid_until`, `GOVERNED_BY`) with Kingsfield-Lite — no INTERNAL REFERENCE ONLY markers needed. The schema vocabulary leak was a model capability problem, not a prompt design problem.
- Posadas (Q026) passed for the first time across any model — genuine doctrinal depth.
- Q096 and Q098 — temporal currency and normative opinion — both passed. Persistent behavioral failures with all previous models.
- VMI (Q030) and Madsen (Q032) remain the two genuine doctrinal gaps across all models.

**Architecture role:** Premium tier. Not suitable as free-tier inner model at $0.25-0.50/query. Two-tier architecture: Sonnet 4.6 (standard, ~$0.08/query) + Fable 5 (premium, ~$0.25-0.50/query).

**Full 100-question run deferred** — targeted test provides sufficient signal for architecture decision. Run after MCP server is deployed when real usage patterns can inform which questions matter most.

---

## Model Comparison — Final (2026-06-10)

| Model | Provider | Cost/query | Full Suite | Notes |
|---|---|---|---|---|
| claude-fable-5 | Anthropic | ~$0.25-0.50 | ~94/100 (projected) | Premium tier; quality ceiling |
| claude-sonnet-4-6 | Anthropic | ~$0.08 | 88/100 | **Production inner model** |
| claude-opus-4-5 | Anthropic | ~$0.40 | 86/100 | Superseded by Sonnet |
| claude-haiku-4-5 | Anthropic | ~$0.005 | 63/100 | Insufficient doctrinal depth |
| llama-3.3-70b | Nvidia NIM | free | untested | 238s latency — unusable interactive |
| deepseek-v4-pro | Nvidia NIM | free | untested | 504 timeouts — endpoint unreliable |
| qwen3.5-397b | Nvidia NIM | free | untested | 403 auth failures |

---

## Environment & Authentication — Known Issues

**The most common failure mode in the test runner is authentication errors.** Both the Anthropic API key and Nvidia API key have caused repeated issues. Document the correct setup here to avoid repeating the diagnosis.

### Anthropic API Key

The key must be exported in `~/.zshrc` to persist across terminal sessions:

```bash
# Verify key is visible to Python
python3 -c "import os; print(repr(os.environ.get('ANTHROPIC_API_KEY', 'NOT FOUND')[:12]))"
# Should print 'sk-ant-api03'

# If NOT FOUND or wrong: add to ~/.zshrc permanently
echo "export ANTHROPIC_API_KEY=sk-ant-..." >> ~/.zshrc
source ~/.zshrc
```

**Root cause of auth failures:** `source .env` sets the variable in the current shell but subprocesses (Python) may not inherit it if `.env` uses `ANTHROPIC_API_KEY=...` without `export`. The `~/.zshrc` approach bypasses this entirely.

**The `.env` file** at `~/Documents/lexgraph_pipeline/.env` must have `export` prefix on ALL variables:
```
export ANTHROPIC_API_KEY=sk-ant-...
export NEO4J_PASSWORD=...
export NVIDIA_API_KEY=nvapi-...
```

If the `.env` file has duplicate entries (one truncated, one full), keep only the full key:
```bash
python3 -c "
lines = open('.env').readlines()
seen = {}
new = []
for l in lines:
    k = l.split('=')[0].strip().replace('export ','')
    if k not in seen:
        seen[k] = True
        new.append(l)
open('.env', 'w').writelines(new)
"
```

### Nvidia API Key

The Nvidia key must also have `export` and must be the full key (not truncated). Key starts with `nvapi-` and is ~80+ characters. The `.env` file historically had both a truncated placeholder and the real key — the truncated one was loading last and overwriting the real one.

Verify:
```bash
python3 -c "import os; k=os.environ.get('NVIDIA_API_KEY',''); print(f'Length: {len(k)}, OK: {len(k) > 50}')"
# Should show Length: 70+, OK: True
```

### Nvidia NIM — Model Access Notes

Available models confirmed working on the account (as of 2026-06-09):
- `meta/llama-3.3-70b-instruct` — works but 30-238s latency on free tier
- `meta/llama-4-maverick-17b-128e-instruct` — used in audit_panel.py
- `mistralai/mixtral-8x22b-v0.1` — used in audit_panel.py
- `nvidia/llama-3.1-nemotron-ultra-253b-v1` — untested for CARLA

Models that 403/504 (likely require paid tier or are overloaded):
- `qwen/qwen3.5-397b-a17b` — 403
- `deepseek-ai/deepseek-v4-pro` — 504

**The Nvidia free tier is suitable for batch async work (audit_panel.py) but not for interactive CARLA queries** due to variable latency (30s-238s per request).

**For future open model testing:** Use DeepSeek's own API ($0.27/million tokens, OpenAI-compatible) or Together AI. The `client.py` provider abstraction supports any OpenAI-compatible endpoint — change `NVIDIA_BASE` URL and key.

### audit_panel.py

The ring test infrastructure at `~/Documents/lexgraph_pipeline/audit_panel.py` uses three Nvidia NIM LLM judges for graph QC:
- Judge 1: `meta/llama-4-maverick-17b-128e-instruct`
- Judge 2: `qwen/qwen3.5-397b-a17b` (may require paid tier)
- Judge 3: `mistralai/mixtral-8x22b-instruct-v0.1`
- Overseer: Claude Sonnet (Anthropic API)

Takes `--nvidia-key` as CLI argument — bypasses `.env`. Useful for batch graph auditing where latency doesn't matter.

---

## Roadmap — Final (2026-06-10)

1. ✅ Graph — 898 nodes, 1298 edges, 8 First Amendment areas
2. ✅ Kingsfield v0.1 — 8 sections locked; Lite governs production CARLA
3. ✅ Test infrastructure — 100 questions, runner, evaluator, Neo4j REST tool
4. ✅ Model selection — Sonnet 4.6 (88/100, $0.08/query); Fable 5 (projected 94/100, premium tier)
5. ✅ Kingsfield-Lite — coverage discipline, normative prohibition, coverage narration fixes
6. **NEXT: MCP server** — Option B, Sonnet inner model, GCP Cloud Run, 10 query/month free tier
7. **THEN: Fable 5 full test** — 100-question run after MCP deployed; real usage patterns first
8. **THEN: LLM-as-judge** — Phase 2 evaluator for quality scoring
9. **THEN: Kingsfield v2 rewrite** — Sections 3-4 as genuine internal-only schema reference
10. Outside world test — real lawyers, real research tasks
11. Paid tier — Fable 5 as premium inner model; pricing TBD
