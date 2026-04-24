# U.S. Law Knowledge Graph

A machine-readable, navigable knowledge graph of U.S. law — built as a  graph of typed nodes and edges rather than a document corpus.

The graph models legal doctrine as structure: what tests govern a doctrinal area, how cases established or modified those tests, which cases overruled which others, and how doctrinal lineage flows from early dissents to later majority holdings.

**Current status:** MVP — Constitutional Law. First Amendment (complete) and Equal Protection (complete). Graph building pipeline operational with LLM-assisted extraction, schema validation, and CourtListener factual QA.

---
![U.S. Law Knowledge Graph — First Amendment and Equal Protection](docs/images/graph_screenshot.png)
*244 nodes · 522 edges · First Amendment (8 doctrinal areas) and Equal Protection fully modeled*

## Why a knowledge graph

Existing legal research tools are document corpora with keyword search. They tell you what cases exist. They do not tell you how law is organized.

This graph does. It answers questions like:

- What tests currently govern commercial speech?
- What is the full doctrinal lineage of the Brandenburg incitement test?
- Which cases have been overruled, and by what?
- What doctrine is a precondition to strict scrutiny in equal protection?
- Which early dissents became majority law, and when?

These are traversal queries over a semantic graph, not keyword searches over a document corpus.

---

## Graph model

The graph is a directed acyclic graph (DAG) with typed nodes and edges.

### Node types

| Type | Description |
|------|-------------|
| `Area` | Doctrinal areas forming the taxonomy spine (e.g., Commercial Speech, Equal Protection) |
| `Doctrine` | Specific legal principles within an Area (e.g., Suspect Classification Doctrine) |
| `DoctrinalTest` | Formalized multi-prong tests (e.g., Central Hudson Test, Glucksberg Two-Part Test) |
| `Case` | Judicial decisions — authority nodes, not taxonomy nodes |
| `ConstitutionalProvision` | Constitutional provisions (e.g., U.S. Const. amend. I, amend. XIV § 1) |
| `Statute` | Federal statutes — Phase 2 |
| `Regulation` | Federal regulations — Phase 2 |

### Edge types

| Edge | Meaning |
|------|---------|
| `CHILD_OF` | Area hierarchy |
| `GOVERNED_BY` | Area → governing Doctrine or DoctrinalTest |
| `ESTABLISHES` | Case created a Doctrine or DoctrinalTest |
| `MODIFIES` | Case changed a Doctrine or DoctrinalTest (direction: narrows, expands, clarifies, complicates, repudiates, extends) |
| `APPLIES` | Case applied a Doctrine or DoctrinalTest without changing it |
| `OVERRULES` | Case overruled another case (overrule_type: explicit, implicit, effective, partial) |
| `DISTINGUISHES` | Case distinguished itself from another case |
| `INTELLECTUALLY_PRECEDES` | A non-majority opinion originated reasoning later adopted as majority law |
| `PRECONDITION_TO` | One doctrine must be satisfied before another applies |
| `INTERPRETS` | Case interpreted a ConstitutionalProvision |
| `GROUNDED_IN` | Area or Doctrine grounded in a ConstitutionalProvision |

---

## Current coverage

### First Amendment — complete (casebook depth + CourtListener batch 1)

All eight doctrinal areas fully modeled:

- Free Speech › Commercial Speech
- Free Speech › Core Political Speech
- Free Speech › Prior Restraint
- Freedom of the Press
- Free Exercise of Religion
- Establishment Clause
- Freedom of Association
- Freedom of Petition

Includes the Brandenburg lineage (Abrams → Gitlow → Whitney → Yates → Brandenburg), the Central Hudson commercial speech test, the Lemon/Kennedy establishment clause transition, and CourtListener-enriched citation depth on commercial speech cases.

### Equal Protection — complete (casebook depth)

Full doctrinal spine including:

- Three-tier scrutiny framework (strict, intermediate, rational basis) as DoctrinalTest nodes
- Suspect classification doctrine (Strauder → Korematsu → Loving → Washington v. Davis → McCleskey → Adarand → SFFA)
- Quasi-suspect classification doctrine (Reed → Frontiero → Craig v. Boren → VMI)
- Rational basis with bite (Moreno → Cleburne → Romer)
- Fundamental rights EP (Harper → Reynolds → Shapiro → Rodriguez → Obergefell)
- Casebook cases including Bowers v. Hardwick, Saenz v. Roe, Bush v. Gore, Davis v. Bandemer

### Graph statistics (current)

- **244 nodes · 522 edges · 0 validation errors**
- 4 constitutional provision nodes
- 13 area nodes · 43 doctrine nodes · 20 doctrinal test nodes · 155 case nodes (1857–2023)

---

## Repo structure

```
data/
  conlaw_graph_v02.json           # Canonical combined graph (JSON-LD)
docs/
  uslawkg_ontology_v05.docx       # Node types, edge types, field definitions
  uslawkg_validation_v05.docx     # Validation rules and error codes
  uslawkg_editorial_v05.docx      # Label conventions, contribution workflow
  uslawkg_serialization_v05.docx  # JSON-LD format, Neo4j import, pipeline spec
prompts/
  graph_builder_prompt_v1_3.txt   # LLM Graph Builder system prompt
validate.py                       # Graph validator (v0.5)
neo4j_import.py                   # Neo4j import pipeline
qa_factual.py                     # QA: Factual agent (CourtListener cross-reference)
requirements.txt
README.md
```

---

## Quickstart

### Validate the graph

```bash
pip install -r requirements.txt
python validate.py --file data/conlaw_graph_v02.json
```

### Import to Neo4j

Requires a Neo4j AuraDB instance (free tier works).

```bash
python neo4j_import.py \
  --uri "neo4j+s://your-instance.databases.neo4j.io" \
  --user your-username \
  --password your-password \
  --file data/conlaw_graph_v02.json \
  --wipe
```

### Run the pipeline on new legal text

```bash
# Validate a draft output
python validate.py \
  --file draft_output.json \
  --combined data/conlaw_graph_v02.json \
  --draft

# Run factual QA against CourtListener
python qa_factual.py \
  --draft draft_output.json \
  --output qa_report.json \
  --patch
```

---

## Schema

The schema is defined in four documents in `docs/`. Current version: v0.5.

Key principles:

- **Temporal validity everywhere** — every node and edge carries `valid_from` and `valid_until`. Overruled cases are never deleted; they remain with `status: overruled` and `valid_until` populated.
- **Separation of taxonomy and authority** — Area/Doctrine/DoctrinalTest nodes are the navigational skeleton. Case/ConstitutionalProvision nodes are the authority layer.
- **Doctrinal lineage is explicit** — the `INTELLECTUALLY_PRECEDES` edge with `opinion_ref` models the path from dissent to majority law. Holmes's Abrams dissent (1919) → Brandenburg majority (1969) is a traversable edge.
- **MODIFIES carries direction** — every modification edge specifies whether the case narrowed, expanded, clarified, complicated, repudiated, or extended the doctrine.

---

## Canonical query tests

Six queries run automatically after every Neo4j import:

| Query | Tests |
|-------|-------|
| QT-1 | What tests currently govern commercial speech? |
| QT-2 | What cases touch the Brandenburg incitement test? |
| QT-3 | Full doctrinal lineage of the Brandenburg test |
| QT-4 | Taxonomy path from commercial speech to root |
| QT-5 | All overruled cases with their overruling cases |
| QT-6 | All RELATED_TO connections across doctrinal areas |

---

## Roadmap

- [ ] Substantive Due Process branch
- [ ] CourtListener ID population for existing Case nodes
- [ ] QA: Legal Pressure Test agent (NetworkX sandbox)
- [ ] Automated graph expansion pipeline (LangGraph)
- [ ] Federal statutory law — Phase 2
- [ ] CFR regulatory spine — Phase 2

---

## Author

Bruce Antley
