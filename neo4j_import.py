#!/usr/bin/env python3
"""
U.S. Law Knowledge Graph — Neo4j Import Pipeline v0.4
Transforms conlaw_graph_v02.json into Neo4j property graph format.

Usage:
    python neo4j_import.py --uri bolt://localhost:7687 --user neo4j --password <password> --file conlaw_graph_v02.json
    python neo4j_import.py --uri bolt://localhost:7687 --user neo4j --password <password> --file conlaw_graph_v02.json --wipe

Requirements:
    pip install neo4j

Neo4j Setup (Community Edition):
    1. Download Neo4j Community from https://neo4j.com/download/
    2. Start: ./bin/neo4j start (or neo4j console)
    3. Default URI: bolt://localhost:7687
    4. Set password on first login at http://localhost:7474

Neo4j AuraDB (free cloud):
    1. Create free instance at https://console.neo4j.io
    2. Download credentials file
    3. Use the provided URI and password
"""

import json
import argparse
import sys
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError


# ── Node type -> Neo4j label mapping ─────────────────────────────────────────
NODE_TYPE_LABELS = {
    'Area':                   ['Area', 'TaxonomyNode'],
    'Doctrine':               ['Doctrine', 'TaxonomyNode'],
    'DoctrinalTest':          ['DoctrinalTest', 'TaxonomyNode'],
    'Case':                   ['Case', 'AuthorityNode'],
    'ConstitutionalProvision':['ConstitutionalProvision', 'AuthorityNode'],
    'Statute':                ['Statute', 'AuthorityNode'],
    'Regulation':             ['Regulation', 'AuthorityNode'],
}

# Fields to exclude from Neo4j properties (handled as relationships or too complex)
EXCLUDE_FIELDS = {'@type', 'prongs', 'opinions', 'elements', 'elements_history',
                  'pending_establishment', 'intellectual_source', 'secondary_parents'}

# Fields to serialize as JSON strings (arrays/objects that Neo4j stores as strings)
JSON_FIELDS = {'jurisdiction', 'tags'}


def connect(uri, user, password):
    """Create Neo4j driver and verify connection."""
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        print(f"✓ Connected to Neo4j at {uri}")
        return driver
    except ServiceUnavailable:
        print(f"✗ Cannot connect to Neo4j at {uri}")
        print("  Make sure Neo4j is running. Start with: neo4j start")
        sys.exit(1)
    except AuthError:
        print(f"✗ Authentication failed for user '{user}'")
        print("  Check your password. Set it at http://localhost:7474")
        sys.exit(1)


def wipe_database(driver):
    """Remove all nodes and relationships."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("✓ Database wiped")


def create_constraints(driver):
    """Create uniqueness constraints and indexes for performance."""
    constraints = [
        # Uniqueness constraints — enforce ID uniqueness per label
        "CREATE CONSTRAINT area_id IF NOT EXISTS FOR (n:Area) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT doctrine_id IF NOT EXISTS FOR (n:Doctrine) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT test_id IF NOT EXISTS FOR (n:DoctrinalTest) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT case_id IF NOT EXISTS FOR (n:Case) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT provision_id IF NOT EXISTS FOR (n:ConstitutionalProvision) REQUIRE n.id IS UNIQUE",
        # Indexes for common query patterns
        "CREATE INDEX area_status IF NOT EXISTS FOR (n:Area) ON (n.status)",
        "CREATE INDEX doctrine_status IF NOT EXISTS FOR (n:Doctrine) ON (n.status)",
        "CREATE INDEX case_status IF NOT EXISTS FOR (n:Case) ON (n.status)",
        "CREATE INDEX case_court_level IF NOT EXISTS FOR (n:Case) ON (n.court_level)",
        "CREATE INDEX case_decided_date IF NOT EXISTS FOR (n:Case) ON (n.decided_date)",
        "CREATE INDEX case_precedential_weight IF NOT EXISTS FOR (n:Case) ON (n.precedential_weight)",
        "CREATE INDEX taxonomy_valid_from IF NOT EXISTS FOR (n:TaxonomyNode) ON (n.valid_from)",
        "CREATE INDEX authority_valid_from IF NOT EXISTS FOR (n:AuthorityNode) ON (n.valid_from)",
    ]
    with driver.session() as session:
        for cypher in constraints:
            try:
                session.run(cypher)
            except Exception as e:
                if 'already exists' not in str(e).lower():
                    print(f"  Warning on constraint: {e}")
    print(f"✓ Created {len(constraints)} constraints and indexes")


def prepare_node_props(node):
    """Convert JSON node dict to Neo4j-safe property dict."""
    props = {}
    for k, v in node.items():
        if k in EXCLUDE_FIELDS:
            continue
        if v is None:
            continue
        if k in JSON_FIELDS and isinstance(v, list):
            props[k] = json.dumps(v)
        elif isinstance(v, list):
            # Store simple string lists as arrays, complex lists as JSON
            if all(isinstance(i, str) for i in v):
                props[k] = v
            else:
                props[k] = json.dumps(v)
        elif isinstance(v, dict):
            props[k] = json.dumps(v)
        elif isinstance(v, bool):
            props[k] = v
        elif isinstance(v, (int, float, str)):
            props[k] = v
    return props


def prepare_edge_props(edge):
    """Convert JSON edge dict to Neo4j-safe property dict."""
    props = {}
    skip = {'id', 'source_id', 'target_id', 'edge_type'}
    for k, v in edge.items():
        if k in skip or v is None:
            continue
        if isinstance(v, list):
            if all(isinstance(i, str) for i in v):
                props[k] = v
            else:
                props[k] = json.dumps(v)
        elif isinstance(v, dict):
            props[k] = json.dumps(v)
        elif isinstance(v, (bool, int, float, str)):
            props[k] = v
    return props


def import_nodes(driver, data):
    """Import all node types."""
    type_key_map = {
        'areas': 'Area',
        'doctrines': 'Doctrine',
        'doctrinal_tests': 'DoctrinalTest',
        'cases': 'Case',
        'constitutional_provisions': 'ConstitutionalProvision',
    }

    total = 0
    with driver.session() as session:
        for type_key, node_type in type_key_map.items():
            nodes = data['nodes'].get(type_key, [])
            if not nodes:
                continue

            labels = ':'.join(NODE_TYPE_LABELS.get(node_type, [node_type]))

            for node in nodes:
                props = prepare_node_props(node)
                # Store prongs as JSON string for DoctrinalTests
                if node_type == 'DoctrinalTest' and 'prongs' in node:
                    props['prongs_json'] = json.dumps(node['prongs'])
                    props['prong_count'] = len(node['prongs'])
                # Store opinions as JSON for Cases
                if node_type == 'Case' and 'opinions' in node:
                    props['opinions_json'] = json.dumps(node.get('opinions', []))
                # Store elements as array for Doctrines
                if 'elements' in node and isinstance(node['elements'], list):
                    props['elements'] = node['elements']

                cypher = f"""
                    MERGE (n:{labels} {{id: $id}})
                    SET n += $props
                """
                session.run(cypher, id=props['id'], props=props)
                total += 1

            print(f"  ✓ Imported {len(nodes)} {node_type} nodes")

    print(f"✓ Total nodes imported: {total}")
    return total


def import_edges(driver, data):
    """Import all edges as Neo4j relationships."""
    edges = data.get('edges', [])
    total = 0
    skipped = 0

    with driver.session() as session:
        # Build set of all node IDs for reference checking
        all_ids_cypher = "MATCH (n) RETURN n.id as id"
        result = session.run(all_ids_cypher)
        existing_ids = {r['id'] for r in result}

        for edge in edges:
            sid = edge['source_id']
            tid = edge['target_id']
            etype = edge['edge_type']
            eid = edge['id']

            # Skip if either endpoint doesn't exist
            if sid not in existing_ids or tid not in existing_ids:
                skipped += 1
                continue

            props = prepare_edge_props(edge)
            props['id'] = eid

            cypher = f"""
                MATCH (source {{id: $source_id}})
                MATCH (target {{id: $target_id}})
                MERGE (source)-[r:{etype} {{id: $edge_id}}]->(target)
                SET r += $props
            """
            session.run(cypher,
                source_id=sid,
                target_id=tid,
                edge_id=eid,
                props=props)
            total += 1

    if skipped:
        print(f"  ⚠ Skipped {skipped} edges (cross-slice references not in this graph)")
    print(f"✓ Total edges imported: {total}")
    return total


def verify_import(driver, expected_nodes, expected_edges):
    """Run basic verification queries."""
    with driver.session() as session:
        node_count = session.run("MATCH (n) RETURN count(n) as c").single()['c']
        edge_count = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()['c']

    print(f"\n{'='*50}")
    print(f"IMPORT VERIFICATION")
    print(f"{'='*50}")
    print(f"Nodes:  {node_count} (expected {expected_nodes})")
    print(f"Edges:  {edge_count} (expected {expected_edges})")

    if node_count == expected_nodes and edge_count == expected_edges:
        print("✓ Counts match — import successful")
    else:
        print("⚠ Count mismatch — check for cross-slice edge skips")


def run_sample_queries(driver):
    """Run the four canonical query templates to verify the graph is queryable."""
    print(f"\n{'='*50}")
    print("CANONICAL QUERY TESTS")
    print(f"{'='*50}")

    queries = [
        {
            'name': 'QT-1: What tests currently govern commercial speech?',
            'cypher': """
                MATCH (a:Area {id: 'commercial_speech'})-[r:GOVERNED_BY]->(t:DoctrinalTest)
                WHERE t.status <> 'overruled' AND (r.valid_until IS NULL OR r.valid_until = 'null')
                RETURN t.id as test_id, t.label as test_label, t.status as status
                ORDER BY t.valid_from
            """
        },
        {
            'name': 'QT-2: What cases touch the Brandenburg incitement test?',
            'cypher': """
                MATCH (c:Case)-[r:ESTABLISHES|MODIFIES|APPLIES]->(t:DoctrinalTest {id: 'brandenburg_test'})
                RETURN c.short_name as case_name, c.decided_date as date, type(r) as relationship,
                       r.direction as direction
                ORDER BY c.decided_date
            """
        },
        {
            'name': 'QT-3: Full doctrinal lineage of the Brandenburg test',
            'cypher': """
                MATCH (source:Case)-[ip:INTELLECTUALLY_PRECEDES]->(target:Case)-[:ESTABLISHES]->(t:DoctrinalTest {id: 'brandenburg_test'})
                RETURN source.short_name as intellectual_source, source.decided_date as source_date,
                       target.short_name as establishing_case, target.decided_date as established_date
            """
        },
        {
            'name': 'QT-4: Taxonomy path from commercial speech to root',
            'cypher': """
                MATCH path = (a:Area {id: 'commercial_speech'})-[:CHILD_OF*]->(root:Area)
                WHERE NOT (root)-[:CHILD_OF]->()
                RETURN [n IN nodes(path) | n.label] as taxonomy_path
            """
        },
        {
            'name': 'QT-5: All overruled cases with their overruling cases',
            'cypher': """
                MATCH (newer:Case)-[r:OVERRULES]->(older:Case)
                RETURN newer.short_name as overruling, newer.decided_date as overruling_date,
                       older.short_name as overruled, older.decided_date as overruled_date,
                       r.overrule_type as type
                ORDER BY newer.decided_date
            """
        },
        {
            'name': 'QT-6: All RELATED_TO connections across doctrinal areas',
            'cypher': """
                MATCH (a1:Area)-[:RELATED_TO]->(a2:Area)
                RETURN a1.label as area1, a2.label as area2
                ORDER BY a1.label
            """
        },
    ]

    with driver.session() as session:
        for q in queries:
            print(f"\n{q['name']}")
            try:
                result = session.run(q['cypher'])
                rows = list(result)
                if rows:
                    for row in rows:
                        print(f"  {dict(row)}")
                else:
                    print("  (no results)")
            except Exception as e:
                print(f"  ✗ Query error: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Import U.S. Law Knowledge Graph into Neo4j'
    )
    parser.add_argument('--uri',      default='bolt://localhost:7687',
                        help='Neo4j bolt URI (default: bolt://localhost:7687)')
    parser.add_argument('--uri-aura', default=None,
                        help='Neo4j AuraDB URI (overrides --uri)')
    parser.add_argument('--user',     default='neo4j',
                        help='Neo4j username (default: neo4j)')
    parser.add_argument('--password', required=True,
                        help='Neo4j password')
    parser.add_argument('--file',     default='conlaw_graph_v02.json',
                        help='Path to graph JSON file')
    parser.add_argument('--wipe',     action='store_true',
                        help='Wipe database before importing (USE WITH CAUTION)')
    parser.add_argument('--queries-only', action='store_true',
                        help='Skip import, only run verification queries')
    args = parser.parse_args()

    uri = args.uri_aura or args.uri

    print(f"\nU.S. Law Knowledge Graph — Neo4j Import Pipeline v0.4")
    print(f"{'='*50}")
    print(f"Source:   {args.file}")
    print(f"Target:   {uri}")
    print(f"{'='*50}\n")

    # Load graph data
    try:
        with open(args.file) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"✗ File not found: {args.file}")
        sys.exit(1)

    expected_nodes = data['meta']['node_count']
    expected_edges = data['meta']['edge_count']
    print(f"Graph: {expected_nodes} nodes · {expected_edges} edges · "
          f"{len(data.get('meta', {}).get('slices', []))} slices")
    print(f"Schema issues documented: {data['meta'].get('schema_issue_count', '?')}\n")

    # Connect
    driver = connect(uri, args.user, args.password)

    if args.queries_only:
        run_sample_queries(driver)
        driver.close()
        return

    # Wipe if requested
    if args.wipe:
        confirm = input("⚠ This will delete ALL data in the database. Type 'yes' to confirm: ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            driver.close()
            sys.exit(0)
        wipe_database(driver)

    # Create constraints and indexes
    print("Creating constraints and indexes...")
    create_constraints(driver)

    # Import nodes
    print("\nImporting nodes...")
    import_nodes(driver, data)

    # Import edges
    print("\nImporting edges...")
    import_edges(driver, data)

    # Verify
    verify_import(driver, expected_nodes, expected_edges)

    # Run sample queries
    run_sample_queries(driver)

    driver.close()
    print(f"\n✓ Import complete. Graph is queryable at {uri}")
    print(f"  Browser: http://localhost:7474 (local) or your AuraDB console URL")


if __name__ == '__main__':
    main()
