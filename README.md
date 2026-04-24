# U.S. Law Knowledge Graph

A machine-readable, navigable knowledge graph of U.S. constitutional law — built as a property graph of typed nodes and edges rather than a document corpus.

<img width="2598" height="1616" alt="image" src="https://github.com/user-attachments/assets/a54828f2-8e7c-46b3-9cb6-4f0310d25383" />


The graph models legal doctrine as structure: what tests govern a doctrinal area, how cases established or modified those tests, which cases overruled which others, and how intellectual lineage flows from early dissents to later majority holdings. This is what keyword search cannot do.

**Current status:** First Amendment (complete, 8 doctrinal areas) and Equal Protection (complete, casebook depth). 244 nodes · 522 edges · 0 validation errors. Graph building pipeline operational with LLM-assisted extraction, schema validation, and CourtListener factual QA.

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

| Type | Description |
|------|-------------|
| `Area` | Doctrinal areas forming the taxonomy spine |
| `Doctrine` | Specific legal principles within an Area |
| `DoctrinalTest` | Formalized multi-prong tests (e.g., Central Hudson, Glucksberg) |
| `Case` | Judicial decisions — authority nodes, not taxonomy nodes |
| `ConstitutionalProvision` | Constitutional text (e.g., U.S. Const. amend. I) |

### Edge types

| Edge | Meaning |
|------|---------|
| `ESTABLISHES` | Case created a Doctrine or DoctrinalTest |
| `MODIFIES` | Case changed doctrine (direction: narrows, expands, clarifies, complicates, repudiates, extends) |
| `APPLIES` | Case applied doctrine without changing it |
| `OVERRULES` | Case overruled another (overrule_type: explicit, implicit, effective, partial) |
| `INTELLECTUALLY_PRECEDES` | A dissent or concurrence originated reasoning later adopted as majority law |
| `PRECONDITION_TO` | One doctrine must be satisfied before another applies |
| `GOVERNED_BY` | Area → governing Doctrine or DoctrinalTest |
| `CHILD_OF` | Area hierarchy |
| `INTERPRETS` | Case interpreted a ConstitutionalProvision |

---

## Current coverage

### First Amendment — complete

All eight doctrinal areas modeled at casebook depth:

- Free Speech › Commercial Speech
- Free Speech › Core Political Speech  
- Free Speech › Prior Restraint
- Freedom of the Press
- Free Exercise of Religion
- Establishment Clause
- Freedom of Association
- Freedom of Petition

Includes: the Brandenburg lineage (Abrams 1919 → Gitlow → Whitney → Yates → Brandenburg 1969), the Central Hudson commercial speech test and its modifications, the Lemon/Kennedy establishment clause transition, and CourtListener citation depth on commercial speech cases.

### Equal Protection — complete

Full doctrinal spine including:

- Three scrutiny tiers as DoctrinalTest nodes (strict, intermediate, rational basis)
- Suspect classification doctrine: Strauder → Korematsu → Loving → Washington v. Davis → McCleskey → Adarand → SFFA (2023)
- Quasi-suspect classification: Reed → Frontiero → Craig v. Boren → VMI
- Rational basis with bite: Moreno → Cleburne → Romer
- Fundamental rights EP: Harper → Reynolds → Shapiro → Rodriguez → Obergefell
- Casebook cases: Bowers v. Hardwick, Saenz v. Roe, Bush v. Gore, Davis v. Bandemer

### Stats

- **244 nodes · 522 edges · 0 validation errors**
- Cases span 1857 (Dred Scott) through 2023 (SFFA v. Harvard)


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

Four documents in `docs/` define the schema (current: v0.5). Key principles:

- **Temporal validity everywhere** — `valid_from` and `valid_until` on all nodes and edges. Overruled cases are never deleted — they remain with `status: overruled` and `valid_until` populated.
- **Separation of taxonomy and authority** — Area/Doctrine/DoctrinalTest nodes are the navigational skeleton. Case/ConstitutionalProvision nodes are the authority layer.
- **Doctrinal lineage is explicit** — `INTELLECTUALLY_PRECEDES` with `opinion_ref` makes the dissent-to-majority path traversable. Holmes's Abrams dissent (1919) → Brandenburg majority (1969) is a graph edge.
- **MODIFIES carries direction** — narrows, expands, clarifies, complicates, repudiates, or extends.

---

## Roadmap

- [ ] Substantive Due Process
- [ ] CourtListener ID population for all existing Case nodes
- [ ] QA: Legal Pressure Test agent (NetworkX sandbox)
- [ ] Automated expansion pipeline (LangGraph/GCP)
- [ ] Federal statutory law — Phase 2
- [ ] CFR regulatory spine — Phase 2

---

## Author

Bruce Antley
