# US Law Knowledge Graph — Session Journal
## 2026-05-20 — Audit Design, Ring 1, Dedup, Syllabus Corpus

---

## GRAPH STATE AT END OF SESSION

- **906 nodes · 1316 edges · 0 validation errors · 0 Ring 1 warnings**
- GitHub: github.com/bruce-antley/us-law-knowledge-graph (main, current)
- Neo4j AuraDB: 906/1316 confirmed
- Syllabus corpus: 446 files, 360/366 active cases (98%)

---

## FILES AND PATHS

| File | Path |
|------|------|
| Graph JSON | `~/Downloads/us-law-knowledge-graph/data/conlaw_graph_v02.json` |
| Pipeline dir | `~/Documents/lexgraph_pipeline/` |
| Syllabi dir | `~/Documents/lexgraph_pipeline/syllabi/` (446 files) |
| Ring 1 | `~/Documents/lexgraph_pipeline/ring1_health_check.py` |
| Audit panel | `~/Documents/lexgraph_pipeline/audit_panel.py` |
| Fetch syllabi | `~/Documents/lexgraph_pipeline/fetch_missing_syllabi.py` |
| Elsa | `~/Documents/lexgraph_pipeline/elsa.py` (v2.3) |
| Validator | `~/Documents/lexgraph_pipeline/validate.py` |

---

## NEO4J CONNECTION

- URI: `neo4j+s://779dfe5d.databases.neo4j.io`
- User/DB: `779dfe5d`
- All credentials in `~/Documents/lexgraph_pipeline/.env`
  - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NVIDIA_API_KEY`, `ANTHROPIC_API_KEY`
- Always run: `export $(cat .env | xargs)` before pipeline commands
- Always prefix long-running commands with `caffeinate -i`

---

## NVIDIA JUDGES (confirmed working)

- `meta/llama-4-maverick-17b-128e-instruct`
- `qwen/qwen3.5-397b-a17b`
- `mistralai/mixtral-8x22b-instruct-v0.1`

---

## SESSION WORK COMPLETED

### 1. Duplicate Node Cleanup (15 merges)
- Merged 15 duplicate Case node pairs by citation match
- Fixed 2 wrong citations: INS v. Lopez-Mendoza (468 U.S. 1032), Virginia v. Maryland (540 U.S. 56)
- All edges rerouted to canonical IDs before stub deletion
- 8 validation errors fixed post-merge

### 2. ESTABLISHES → APPLIES/MODIFIES Fixes (15 edges)
- Date-based Cypher audit: earlier case already establishes same doctrine = error
- 13 edges converted ESTABLISHES → APPLIES
- Brandenburg → incitement_doctrine: MODIFIES/repudiates (replaced Schenck test)
- Miller v. California → obscenity_doctrine: MODIFIES/clarifies (replaced Roth-Memoirs test)

### 3. Syllabus Corpus
- 346 syllabi already existed (Oyez source, structured FACTS/CONCLUSION format)
- `fetch_missing_syllabi.py` built and run: 100/105 success, 5 no_syllabus failures
- Failures: Planned Parenthood v. ACLA, Davis v. FEC, Strauder v. WV, Douglas v. CA, Bond v. US
- Final: 446 syllabi, 360/366 active cases (98%)

### 4. Audit System Design (3-ring framework)

**Ring 1 — Deterministic (BUILT)**
- 13 checks, 2 seconds, 0 tokens, run before every commit

**Ring 2 — Reference cross-check (PLANNED)**
- Wikipedia API: decided_date, majority_author, vote, overruling relationships
- Own syllabus files for holding text comparison
- Not source of truth — reference point flagging discrepancies for human review

**Ring 3 — Syllabus-grounded LLM binary (PLANNED)**
- Unit of auditing: individual edge, not case node
- One binary question per edge type
- 3 judges: Llama 4 Maverick, Qwen3.5-397B, Mixtral-8x22B
- Overseer (Claude Sonnet) fires only on holding accuracy disputes or 2+ majority conflicts

### 5. Ring 1 Health Check (built and passing)
- 13 checks: temporal, status consistency, schema completeness, structural
- Runs in ~2 seconds, exit codes: 0=pass, 1=errors, 2=warnings
- Run: `python3 ring1_health_check.py` (reads .env automatically)
- **Current: 0 errors, 0 warnings**

### 6. Ring 1 Warning Fixes
**C07 (doctrines established only by overruled cases):**
- Gideon ESTABLISHES right_to_counsel_doctrine
- right_to_counsel duplicate node merged into right_to_counsel_doctrine (deleted)
- Duncan ESTABLISHES selective_incorporation_doctrine
- McDonald APPLIES selective_incorporation_doctrine
- ordered_liberty_doctrine valid_until = 2005-03-01 (Roper v. Simmons)
- excessive_entanglement_doctrine valid_until = 2022-06-27 (Kennedy v. Bremerton)
- fourth_amendment_privacy_protection valid_until = 1961-06-19 (Mapp v. Ohio)
- remedy_flexibility_doctrine valid_until = 1961-06-19 (Mapp v. Ohio)

**C12 (Oregon v. Elstad isolated):**
- elstad_applies_miranda_rights_doctrine added

---

## AUDIT DESIGN PRINCIPLES

- Never ask an LLM a question with a deterministic answer
- Never ask an LLM open-ended when binary will do
- Unit of LLM auditing = individual edge, not case node
- LLM judges need graph context (other edges to same target) before evaluating ESTABLISHES
- Holding text and prong quality are the highest-risk failure modes
- Overseer fires only on holding accuracy disputes or 2+ majority conflicts
- `caffeinate -i` prefix on all long-running terminal commands

---

## KEY ERROR CLASSES IDENTIFIED

| Error Class | Detection Method | Priority |
|-------------|-----------------|----------|
| ESTABLISHES vs APPLIES | Date-based Cypher | High — already fixed |
| MODIFIES/repudiates that should be OVERRULES | LLM binary per MODIFIES edge | High |
| Missing OVERRULES entirely | Curated ground-truth list + LLM | High |
| MODIFIES direction wrong | Binary LLM per edge | Medium |
| Holding text inaccuracy | Syllabus-grounded LLM binary | High |
| Prong quality (burden, scrutiny) | Binary LLM per prong vs source syllabus | High |

**Root causes:**
1. Early pipeline less rigorous — pre-v0.3 schema, pre-QC passes
2. Builder blindness — cases built in isolation, no awareness of existing graph state

---

## IMMEDIATE NEXT STEPS

1. Git commit and push current JSON (906/1316, 0 errors, 0 warnings)
2. Ring 2 — Wikipedia API cross-check for factual fields (date, author, vote, overruling)
3. Ring 3 — edge-type-specific binary LLM prompts, syllabus-grounded
4. Prong quality audit design
5. Holding text accuracy audit

---

## RING 2 DESIGN (agreed but not built)

Wikipedia can reliably check:
- `decided_date` (year at minimum)
- `majority_author`
- `vote`
- Overruling relationships (Wikipedia lists "overruled X" explicitly)
- `per_curiam`

Wikipedia cannot check:
- Edge types
- Holding accuracy nuance
- Doctrinal test structure

Implementation: Wikipedia API (free, no key), search by case name, extract infobox.
Compare 5 fields. Flag discrepancies for human review. Not auto-correcting.

---

## RING 3 DESIGN (agreed but not built)

Binary questions per edge type:
- **OVERRULES:** "Does the holding use explicit overruling language?" → determines explicit vs implicit/effective
- **MODIFIES:** "Is the direction attribute correct given this holding?" → binary per edge
- **MODIFIES:** "Did this case go further than MODIFIES — should this be OVERRULES?" → catch soft overrulings
- **APPLIES (landmark):** "Did this case do more than apply — should it be MODIFIES?" → catch under-typed edges
- **Holding text:** "Is this holding accurate and complete — no material omissions?" → syllabus-grounded
- **Prongs:** "Is the burden allocation correct for this prong?" → per prong vs source syllabus

Key: inject full list of edges to same doctrine target before ESTABLISHES evaluation.
