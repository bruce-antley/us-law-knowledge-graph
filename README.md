# U.S. Law Knowledge Graph

A machine-readable, navigable knowledge graph of U.S. constitutional law — built as a graph of typed nodes and edges rather than a document corpus.

<img width="2598" height="1616" alt="image" src="https://github.com/user-attachments/assets/a54828f2-8e7c-46b3-9cb6-4f0310d25383" />

The graph models legal doctrine as structure: what tests govern a doctrinal area, how cases established or modified those tests, which cases overruled which others, and how intellectual lineage flows from early dissents to later majority holdings. This is what keyword search cannot do.

**Current status:** 919 nodes · 1,306 edges · 0 validation errors · 424 SCOTUS decisions spanning 1803–2024. First Amendment complete at full treatise depth (8 doctrinal areas). Justiciability, Equal Protection, Substantive and Procedural Due Process, Takings, Criminal Procedure, Dormant Commerce Clause, and Separation of Powers at substantial depth. Coverage validated against the Seidman casebook (91/91, 100%) and the Rotunda constitutional law treatise. Independently audited via a 5-model LLM panel cross-checked against primary sources.

---

## The problem

Legal research tools are document corpora. They tell you what cases exist. They do not tell you how law is organized.

A lawyer researching commercial speech regulation needs to know: what test governs? what cases established it? what modifications has it survived? which of those modifications narrowed it and which expanded it? what preceded it intellectually? These are structural questions about a doctrinal network — not keyword queries over a pile of PDFs.

This graph answers them directly.

```cypher
// What tests currently govern commercial speech?
MATCH (a:Area {id: 'commercial_speech'})-[:GOVERNED_BY]->(t:DoctrinalTest)
WHERE t.status = 'active'
RETURN t.label

// Full intellectual lineage of Brandenburg
MATCH (source:Case)-[:INTELLECTUALLY_PRECEDES]->(target:Case)
      -[:ESTABLISHES]->(t:DoctrinalTest {id: 'brandenburg_test'})
RETURN source.short_name, source.decided_date, target.short_name
ORDER BY source.decided_date
```

---

## Graph model

The graph is a directed acyclic graph (DAG) with typed nodes and edges.

### Node types

| Type | Count | Description |
|------|-------|-------------|
| `Case` | 424 | Judicial decisions — authority nodes, not taxonomy nodes |
| `Doctrine` | 358 | Specific legal principles within an Area |
| `DoctrinalTest` | 112 | Formalized multi-prong tests (e.g., Central Hudson, Glucksberg) |
| `Area` | 21 | Doctrinal areas forming the taxonomy spine |
| `ConstitutionalProvision` | 4 | Constitutional text (e.g., U.S. Const. amend. I) |

### Edge types

| Edge | Count | Meaning |
|------|-------|---------|
| `ESTABLISHES` | 361 | Case created a Doctrine or DoctrinalTest |
| `APPLIES` | 269 | Case applied doctrine without changing it |
| `CHILD_OF` | 243 | Area hierarchy |
| `INTERPRETS` | 165 | Case interpreted a ConstitutionalProvision |
| `MODIFIES` | 115 | Case changed doctrine (`direction`: narrows, expands, clarifies, complicates, repudiates) |
| `GOVERNED_BY` | 62 | Area or Doctrine governed by a DoctrinalTest (`valid_from`, `valid_until`) |
| `INTELLECTUALLY_PRECEDES` | 32 | A dissent or concurrence originated reasoning later adopted as majority law |
| `DISTINGUISHES` | 20 | Case distinguished itself from a prior case |
| `OVERRULES` | 19 | Case overruled another (`overrule_type`: explicit, implicit, effective) |
| `GROUNDED_IN` | 17 | Doctrine grounded in a ConstitutionalProvision |
| `INCORPORATES` | 2 | 14th Amendment incorporating Bill of Rights provisions |
| `PRECONDITION_TO` | 1 | One doctrine must be satisfied before another applies |

**Within modeled coverage, absence of edges is informative.** No `MODIFIES` edge means a case applied but did not change doctrine. No `OVERRULES` edge means the prior case is still good law. Outside modeled coverage, absence means the area has not been modeled — not that the relationship does not exist in doctrine.

---

## Current coverage

### First Amendment — full treatise depth

All eight doctrinal areas modeled:

- Free Speech › Commercial Speech
- Free Speech › Core Political Speech
- Free Speech › Prior Restraint
- Freedom of the Press
- Free Exercise of Religion
- Establishment Clause
- Freedom of Association
- Freedom of Petition

Includes: the Brandenburg lineage (Abrams 1919 → Gitlow → Whitney → Yates → Brandenburg 1969), the Central Hudson commercial speech test and its modifications, the Lemon/Kennedy establishment clause transition, Smith/Sherbert free exercise dual-track with scope and condition properties on GOVERNED_BY edges, and CourtListener citation depth on commercial speech cases.

### Constitutional law — substantial depth

- **Justiciability** — standing (Article III injury/causation/redressability, per Lujan), political question doctrine (Baker v. Carr six-factor test), taxpayer standing (Flast v. Cohen), ripeness
- **Equal Protection** — three scrutiny tiers; suspect and quasi-suspect classification doctrine (Strauder through SFFA 2023); rational basis with bite; fundamental rights EP
- **Substantive Due Process** — Glucksberg framework; liberty interests; Obergefell; Dobbs
- **Procedural Due Process** — Mathews balancing; property and liberty interests; pretermination requirements
- **Takings Clause** — Penn Central; Lucas; regulatory vs. physical takings
- **Criminal Procedure** — Fourth Amendment search and seizure; third-party doctrine; Carpenter
- **Dormant Commerce Clause** — Pike balancing; discrimination per se; market participant exception
- **Separation of Powers** — non-delegation; appointment and removal; executive privilege

### Stats

- **919 nodes · 1,306 edges · 0 validation errors**
- Cases span 1803 (Marbury v. Madison) through 2024
- Validated: Seidman casebook 91/91 (100%), Rotunda treatise systematic gap analysis
- Independently audited: a 5-model LLM panel cross-checks every edge's legal characterization against primary source text; findings verified against case law before any correction is applied

---

## Quickstart

### Validate

```bash
pip install -r requirements.txt
python validate.py --file data/conlaw_graph_v02.json
```

### Import to Neo4j

```bash
python neo4j_import.py \
  --uri "neo4j+s://your-instance.databases.neo4j.io" \
  --user your-username \
  --password your-password \
  --file data/conlaw_graph_v02.json \
  --wipe
```

### Pipeline — extract new doctrinal content

```bash
# Validate a draft
python validate.py \
  --file draft.json \
  --combined data/conlaw_graph_v02.json \
  --draft

# Factual QA against CourtListener
python qa_factual.py \
  --draft draft.json \
  --output qa_report.json \
  --patch
```

---

## Schema

Four documents in `docs/` define the schema. Key principles:

- **Temporal validity everywhere** — `valid_from` and `valid_until` on all nodes and edges. Overruled cases are never deleted — they remain with `status: overruled` and `valid_until` populated.
- **Separation of taxonomy and authority** — Area/Doctrine/DoctrinalTest nodes are the navigational skeleton. Case/ConstitutionalProvision nodes are the authority layer.
- **Doctrinal lineage is explicit** — `INTELLECTUALLY_PRECEDES` with `opinion_ref` makes the dissent-to-majority path traversable. Holmes's Abrams dissent (1919) → Brandenburg majority (1969) is a graph edge.
- **MODIFIES carries direction** — narrows, expands, clarifies, complicates, or repudiates.
- **GOVERNED_BY carries validity** — `valid_from` and `valid_until` track when a governing test was active, making doctrinal transitions queryable.

---

## CARLA

This graph is the data layer for CARLA (Constitutional Law Research and Legal Analysis), a graph-grounded legal research system that combines LexGraph with a proprietary governance layer to produce citation-disciplined, provenance-attributed constitutional law analysis. CARLA is maintained in a separate repository.

---

## Roadmap

- [ ] CourtListener ID population for all existing Case nodes
- [x] Automated expansion pipeline
- [x] Independent LLM-panel audit system, cross-checked against primary sources
- [ ] Federal statutory law — Phase 2
- [ ] CFR regulatory spine — Phase 2
