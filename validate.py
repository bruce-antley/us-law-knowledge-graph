#!/usr/bin/env python3
"""
U.S. Law Knowledge Graph — Validator v0.5
Implements validation rules from the Validation Spec (Document 2 of 4).
Usage: python validate.py --file path/to/slice.json [--combined path/to/combined.json] [--draft]

v0.5 changes:
  - PRECONDITION_TO edge type added (E018)
  - overrule_type 'partial' added; partial requires notes (E019)
  - opinion_ref.opinion_type 'majority' added to INTELLECTUALLY_PRECEDES
  - provision_type enum enforced on ConstitutionalProvision
  - test_form required on DoctrinalTest
  - --draft flag suppresses E016 orphan node errors for pipeline drafts
"""

import json
import sys
import argparse
from collections import defaultdict

# ── Enums ────────────────────────────────────────────────────────────────────

VALID_EDGE_TYPES = {
    'CHILD_OF', 'RELATED_TO', 'INCORPORATES', 'GROUNDED_IN', 'GOVERNED_BY',
    'ESTABLISHES', 'APPLIES', 'MODIFIES', 'OVERRULES', 'INTERPRETS',
    'DISTINGUISHES', 'CIRCUIT_SPLIT', 'INTELLECTUALLY_PRECEDES',
    'PRECONDITION_TO',
    'IMPLEMENTS', 'CONSTRAINED_BY'
}

VALID_MODIFIES_DIRECTIONS = {
    'narrows', 'expands', 'clarifies', 'complicates', 'repudiates', 'extends'
}

VALID_OVERRULE_TYPES = {'explicit', 'implicit', 'effective', 'partial'}

VALID_COURT_LEVELS = {
    'scotus', 'circuit', 'district', 'state_high', 'state_appellate', 'state_trial'
}

VALID_OPINION_FORMS = {
    'signed_majority', 'per_curiam', 'plurality', 'memorandum', 'equally_divided'
}

VALID_PROCEDURAL_DISPOSITIONS = {
    'affirmed', 'reversed', 'vacated', 'remanded', 'affirmed_in_part',
    'dismissed', 'mooted', 'cert_denied', 'other', 'original_jurisdiction'
}

VALID_HOLDING_TYPES = {'affirmative', 'by_negation'}

VALID_CASE_STATUSES = {
    'good_law', 'overruled', 'limited', 'distinguished',
    'questioned', 'mooted', 'cert_denied', 'disputed'
}

VALID_PRECEDENTIAL_WEIGHTS = {'binding', 'persuasive', 'none'}

VALID_IP_OPINION_TYPES = {'dissent', 'concurrence', 'plurality', 'majority'}

VALID_PROVISION_TYPES = {'amendment', 'section', 'clause', 'article'}

VALID_TEST_FORMS = {
    'conjunctive', 'disjunctive', 'balancing', 'threshold_then_conjunctive'
}

# Edge type compatibility: source_type -> {valid target types}
EDGE_COMPATIBILITY = {
    'CHILD_OF':                {'Area': {'Area'}},
    'RELATED_TO':              {'Area': {'Area'}},
    'INCORPORATES':            {'ConstitutionalProvision': {'ConstitutionalProvision'}},
    'GROUNDED_IN':             {'Area': {'ConstitutionalProvision'}, 'Doctrine': {'ConstitutionalProvision'}},
    'GOVERNED_BY':             {'Area': {'Doctrine', 'DoctrinalTest'}},
    'ESTABLISHES':             {'Case': {'Doctrine', 'DoctrinalTest'}},
    'APPLIES':                 {'Case': {'Doctrine', 'DoctrinalTest'}},
    'MODIFIES':                {'Case': {'Doctrine', 'DoctrinalTest'}},
    'OVERRULES':               {'Case': {'Case'}},
    'INTERPRETS':              {'Case': {'ConstitutionalProvision'}},
    'DISTINGUISHES':           {'Case': {'Case'}},
    'CIRCUIT_SPLIT':           {'Case': {'Case'}},
    'INTELLECTUALLY_PRECEDES': {'Case': {'Case'}},
    'IMPLEMENTS':              {'Statute': {'ConstitutionalProvision'}},
    'CONSTRAINED_BY':          {'Statute': {'Doctrine'}},
    'PRECONDITION_TO':         {'Doctrine': {'Doctrine', 'DoctrinalTest'}},
}

# ── Result collector ──────────────────────────────────────────────────────────

class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, code, message, location=None):
        prefix = f"[{location}] " if location else ""
        self.errors.append(f"  ✗ {code}: {prefix}{message}")

    def warning(self, code, message, location=None):
        prefix = f"[{location}] " if location else ""
        self.warnings.append(f"  ⚠ {code}: {prefix}{message}")

    def ok(self):
        return len(self.errors) == 0

    def summary(self):
        return f"{len(self.errors)} errors, {len(self.warnings)} warnings"

# ── Helpers ──────────────────────────────────────────────────────────────────

def slug_valid(s):
    import re
    return bool(re.match(r'^[a-z0-9_]{1,80}$', s))

def flatten_nodes(data):
    """Returns {id: node_dict} and {id: type_string}"""
    nodes = {}
    types = {}
    for ntype_key, arr in data.get('nodes', {}).items():
        type_map = {
            'areas': 'Area',
            'doctrines': 'Doctrine',
            'doctrinal_tests': 'DoctrinalTest',
            'cases': 'Case',
            'constitutional_provisions': 'ConstitutionalProvision',
            'statutes': 'Statute',
            'regulations': 'Regulation',
        }
        ntype = type_map.get(ntype_key, ntype_key)
        for n in arr:
            nid = n.get('id', '')
            nodes[nid] = n
            types[nid] = n.get('@type', ntype)
    return nodes, types

# ── Node validators ──────────────────────────────────────────────────────────

def validate_area(node, r):
    loc = f"Area:{node.get('id','?')}"
    for field in ['id', 'label', 'description', 'jurisdiction', 'status']:
        if not node.get(field):
            r.error('E001', f"Required field '{field}' missing or empty", loc)
    if node.get('tier') is None:
        r.error('E001', "Required field 'tier' missing", loc)
    if node.get('tier', 0) != 0 and not node.get('parent_id'):
        r.error('E001', "Non-root Area must have parent_id", loc)

def validate_doctrine(node, r):
    loc = f"Doctrine:{node.get('id','?')}"
    for field in ['id', 'label', 'description', 'area_id', 'jurisdiction', 'status']:
        if not node.get(field):
            r.error('E001', f"Required field '{field}' missing or empty", loc)

def validate_case(node, r):
    loc = f"Case:{node.get('id','?')}"
    for field in ['id', 'citation', 'short_name', 'full_name', 'decided_date',
                  'holding', 'holding_type', 'status', 'valid_from']:
        if not node.get(field):
            r.error('E001', f"Required field '{field}' missing or empty", loc)

    if node.get('court_level') and node['court_level'] not in VALID_COURT_LEVELS:
        r.error('E006', f"court_level '{node['court_level']}' not in valid enum", loc)
    elif not node.get('court_level'):
        r.error('E001', "Required field 'court_level' missing", loc)

    if node.get('opinion_form') and node['opinion_form'] not in VALID_OPINION_FORMS:
        r.error('E006', f"opinion_form '{node['opinion_form']}' not in valid enum", loc)
    elif not node.get('opinion_form'):
        r.error('E001', "Required field 'opinion_form' missing", loc)

    if node.get('procedural_disposition') and node['procedural_disposition'] not in VALID_PROCEDURAL_DISPOSITIONS:
        r.error('E006', f"procedural_disposition '{node['procedural_disposition']}' not in valid enum", loc)
    elif not node.get('procedural_disposition'):
        r.error('E001', "Required field 'procedural_disposition' missing", loc)

    if node.get('holding_type') not in VALID_HOLDING_TYPES:
        r.error('E006', "holding_type must be affirmative or by_negation", loc)

    if node.get('status') and node['status'] not in VALID_CASE_STATUSES:
        r.error('E006', f"status '{node['status']}' not in valid Case status enum", loc)

    if node.get('precedential_weight') and node['precedential_weight'] not in VALID_PRECEDENTIAL_WEIGHTS:
        r.error('E006', f"precedential_weight '{node['precedential_weight']}' not in valid enum", loc)

    # E017: per_curiam consistency
    if node.get('per_curiam') and node.get('majority_author'):
        r.error('E017', "per_curiam:true but majority_author is set", loc)
    if node.get('opinion_form') == 'per_curiam' and not node.get('per_curiam'):
        r.warning('W004', "opinion_form is per_curiam but per_curiam field is not true", loc)

    cl = node.get('court_level', '')
    pw = node.get('precedential_weight', '')
    st = node.get('status', '')
    if cl == 'district' and pw == 'binding':
        r.warning('W004', "district court case has precedential_weight:binding", loc)
    if st in ('mooted', 'cert_denied') and pw != 'none':
        r.warning('W004', f"status:{st} but precedential_weight is not 'none'", loc)

def validate_doctrinal_test(node, r):
    loc = f"DoctrinalTest:{node.get('id','?')}"
    for field in ['id', 'label', 'description', 'area_id', 'source_case_id',
                  'scrutiny_level', 'burden', 'status', 'valid_from']:
        if not node.get(field):
            r.error('E001', f"Required field '{field}' missing or empty", loc)

    if not node.get('test_form'):
        r.error('E001', "Required field 'test_form' missing or empty", loc)
    elif node.get('test_form') not in VALID_TEST_FORMS:
        r.error('E006', f"test_form '{node['test_form']}' not in valid enum", loc)

    prongs = node.get('prongs', [])
    if len(prongs) < 2:
        r.error('E001', f"DoctrinalTest must have at least 2 prongs (has {len(prongs)})", loc)

    for p in prongs:
        if p.get('contested') and not p.get('contest_note'):
            r.error('E001', f"Prong {p.get('number','?')}: contested:true requires contest_note", loc)

def validate_constitutional_provision(node, r):
    loc = f"ConstitutionalProvision:{node.get('id','?')}"
    for field in ['id', 'label', 'text', 'provision_type']:
        if not node.get(field):
            r.error('E001', f"Required field '{field}' missing or empty", loc)
    if node.get('provision_type') and node['provision_type'] not in VALID_PROVISION_TYPES:
        r.error('E006', f"provision_type '{node['provision_type']}' not in valid enum "
                f"(amendment | section | clause | article)", loc)

# ── Edge validators ──────────────────────────────────────────────────────────

def validate_edges(edges, nodes, node_types, cross_slice_ok, r):
    seen_edge_ids = set()
    seen_pairs = defaultdict(list)

    for e in edges:
        eid = e.get('id', '?')
        loc = f"Edge:{eid}"
        etype = e.get('edge_type', '')
        sid = e.get('source_id', '')
        tid = e.get('target_id', '')

        # E002: ID uniqueness
        if eid in seen_edge_ids:
            r.error('E002', f"Duplicate edge id '{eid}'", loc)
        seen_edge_ids.add(eid)

        # E003: slug format
        if eid != '?' and not slug_valid(eid):
            r.error('E003', f"Edge id '{eid}' invalid slug format", loc)

        # E005: reference integrity
        if sid not in nodes and sid not in cross_slice_ok:
            r.error('E005', f"source_id '{sid}' not found", loc)
        if tid not in nodes and tid not in cross_slice_ok:
            r.error('E005', f"target_id '{tid}' not found", loc)

        # E006: edge type validity
        if etype not in VALID_EDGE_TYPES:
            r.error('E006', f"edge_type '{etype}' not in valid enum", loc)
            continue

        # E006: type compatibility
        s_type = node_types.get(sid)
        t_type = node_types.get(tid)
        if s_type and t_type and etype in EDGE_COMPATIBILITY:
            compat = EDGE_COMPATIBILITY[etype]
            valid_targets = compat.get(s_type, set())
            if valid_targets and t_type not in valid_targets:
                r.error('E006', f"{etype}: {s_type}->{t_type} is not a valid type combination", loc)

        # E007: duplicate edges
        pair_key = (sid, tid)
        seen_pairs[pair_key].append(etype)

        # E008: MODIFIES direction
        if etype == 'MODIFIES':
            if 'direction' not in e:
                r.error('E008', "MODIFIES edge missing 'direction' attribute", loc)
            elif e['direction'] not in VALID_MODIFIES_DIRECTIONS:
                r.error('E008', f"direction '{e['direction']}' not in valid enum", loc)

        # E009: OVERRULES overrule_type
        if etype == 'OVERRULES':
            if 'overrule_type' not in e:
                r.error('E009', "OVERRULES edge missing 'overrule_type' attribute", loc)
            elif e['overrule_type'] not in VALID_OVERRULE_TYPES:
                r.error('E009', f"overrule_type '{e['overrule_type']}' not in valid enum", loc)
            # E019: partial overrule requires notes
            if e.get('overrule_type') == 'partial' and not e.get('notes'):
                r.error('E019', "OVERRULES with overrule_type:partial requires notes describing scope", loc)

        # INTELLECTUALLY_PRECEDES: opinion_ref required
        if etype == 'INTELLECTUALLY_PRECEDES':
            if 'opinion_ref' not in e:
                r.error('E001', "INTELLECTUALLY_PRECEDES missing 'opinion_ref' attribute", loc)
            else:
                oref = e['opinion_ref']
                if oref.get('opinion_type') not in VALID_IP_OPINION_TYPES:
                    r.error('E006', f"opinion_ref.opinion_type '{oref.get('opinion_type')}' not in valid enum", loc)

        # E018: PRECONDITION_TO validation
        if etype == 'PRECONDITION_TO':
            if not e.get('condition_note'):
                r.error('E018', "PRECONDITION_TO edge missing required 'condition_note' attribute", loc)
            if s_type and s_type != 'Doctrine':
                r.error('E018', f"PRECONDITION_TO source must be Doctrine, got {s_type}", loc)
            if t_type and t_type not in {'Doctrine', 'DoctrinalTest'}:
                r.error('E018', f"PRECONDITION_TO target must be Doctrine or DoctrinalTest, got {t_type}", loc)

        # W003: historical GOVERNED_BY without termination note
        if etype == 'GOVERNED_BY' and e.get('valid_until'):
            r.warning('W003', "Historical GOVERNED_BY edge (valid_until set) — verify terminating event is modeled", loc)

    # E011: APPLIES+MODIFIES collision
    for (sid, tid), etypes in seen_pairs.items():
        if 'APPLIES' in etypes and 'MODIFIES' in etypes:
            r.error('E011', f"Both APPLIES and MODIFIES exist from '{sid}' to '{tid}' — MODIFIES subsumes APPLIES",
                    f"Edge pair:{sid}->{tid}")

    # E007: true duplicate edges
    triple_seen = defaultdict(int)
    for e in edges:
        key = (e.get('source_id'), e.get('target_id'), e.get('edge_type'))
        triple_seen[key] += 1
    for key, count in triple_seen.items():
        if count > 1:
            r.error('E007', f"Duplicate edge: {key[0]} -[{key[2]}]-> {key[1]} appears {count} times")

# ── Graph-level validators ────────────────────────────────────────────────────

def validate_graph_level(nodes, node_types, edges, cross_slice_ok, r, draft_mode=False):

    # E016: Orphan nodes — suppressed in draft mode
    connected = set()
    for e in edges:
        connected.add(e.get('source_id'))
        connected.add(e.get('target_id'))
    if not draft_mode:
        for nid, node in nodes.items():
            if nid not in connected and nid not in cross_slice_ok:
                r.error('E016', "Orphan node — no edges connect to this node", f"Node:{nid}")

    # E004: Label uniqueness
    label_map = defaultdict(list)
    for nid, node in nodes.items():
        lbl = node.get('label') or node.get('short_name') or ''
        if lbl:
            label_map[lbl].append(nid)
    for lbl, nids in label_map.items():
        if len(nids) > 1:
            r.error('E004', f"Label '{lbl}' used by multiple nodes: {nids}")

    # E002: Node ID uniqueness
    seen_ids = defaultdict(list)
    for nid in nodes:
        seen_ids[nid].append(nid)
    for nid, dupes in seen_ids.items():
        if len(dupes) > 1:
            r.error('E002', f"Duplicate node id '{nid}'")

    # E003: Node slug format
    for nid in nodes:
        if not slug_valid(nid):
            r.error('E003', f"Node id '{nid}' invalid slug format", f"Node:{nid}")

    # E012: parent_id / CHILD_OF consistency
    child_of_edges = {e['source_id']: e['target_id'] for e in edges if e.get('edge_type') == 'CHILD_OF'}
    for nid, node in nodes.items():
        if node_types.get(nid) == 'Area':
            pid = node.get('parent_id')
            if pid:
                if nid not in child_of_edges:
                    r.error('E012', f"parent_id='{pid}' set but no CHILD_OF edge exists", f"Area:{nid}")
                elif child_of_edges[nid] != pid:
                    r.error('E012', f"parent_id='{pid}' disagrees with CHILD_OF edge target='{child_of_edges[nid]}'",
                            f"Area:{nid}")

    # E013: source_case_id / ESTABLISHES consistency
    establishes_map = defaultdict(set)
    for e in edges:
        if e.get('edge_type') == 'ESTABLISHES':
            establishes_map[e['target_id']].add(e['source_id'])

    for nid, node in nodes.items():
        if node_types.get(nid) == 'DoctrinalTest':
            scid = node.get('source_case_id')
            if scid:
                # E020 (v0.5): DoctrinalTest must not be sourced from a stub/inferred case
                # Only applies in draft mode — in production, overruled cases can legitimately
                # have established tests that survive (e.g., Korematsu → strict scrutiny)
                source_node = nodes.get(scid, {})
                if draft_mode and (source_node.get('data_tier') == 'inferred' or
                        source_node.get('status') == 'overruled'):
                    r.error('E020',
                        f"DoctrinalTest source_case_id='{scid}' points to an overruled or "
                        f"stub case in this draft. Do not extract DoctrinalTest nodes for "
                        f"overruled stub cases — remove this DoctrinalTest from the draft.",
                        f"DoctrinalTest:{nid}")

                source_is_local = scid in nodes
                if source_is_local:
                    if nid not in establishes_map:
                        r.error('E013', f"source_case_id='{scid}' set but no ESTABLISHES edge found targeting this test",
                                f"DoctrinalTest:{nid}")
                    elif scid not in establishes_map[nid]:
                        sources = list(establishes_map[nid])
                        r.error('E013', f"source_case_id='{scid}' but ESTABLISHES edge(s) come from {sources}",
                                f"DoctrinalTest:{nid}")

    # E014: DAG cycle check
    child_of_pairs = [(e['source_id'], e['target_id']) for e in edges if e.get('edge_type') == 'CHILD_OF']
    adj = defaultdict(set)
    for s, t in child_of_pairs:
        adj[s].add(t)

    def has_cycle(start, visited=None, path=None):
        if visited is None: visited = set()
        if path is None: path = set()
        visited.add(start)
        path.add(start)
        for neighbor in adj.get(start, set()):
            if neighbor not in visited:
                if has_cycle(neighbor, visited, path):
                    return True
            elif neighbor in path:
                return True
        path.discard(start)
        return False

    all_area_ids = [nid for nid, nt in node_types.items() if nt == 'Area']
    for aid in all_area_ids:
        if has_cycle(aid):
            r.error('E014', "CHILD_OF edges create a cycle involving this node", f"Area:{aid}")
            break

    # E015: multiple CHILD_OF per Area
    child_of_counts = defaultdict(int)
    for e in edges:
        if e.get('edge_type') == 'CHILD_OF':
            child_of_counts[e['source_id']] += 1
    for nid, count in child_of_counts.items():
        if count > 1:
            r.error('E015', f"Area has {count} CHILD_OF edges — only 1 allowed", f"Area:{nid}")

    # DoctrinalTest ESTABLISHES check
    dt_ids = {nid for nid, nt in node_types.items() if nt == 'DoctrinalTest'}
    for dt_id in dt_ids:
        if dt_id not in establishes_map:
            dt_node = nodes.get(dt_id, {})
            scid = dt_node.get('source_case_id', '')
            if scid in nodes:
                r.error('E001', "DoctrinalTest has no ESTABLISHES edge from any Case node",
                        f"DoctrinalTest:{dt_id}")

    # W001: OVERRULES cascade check
    overrules_edges = [(e['source_id'], e['target_id']) for e in edges if e.get('edge_type') == 'OVERRULES']
    establishes_by_case = defaultdict(list)
    for e in edges:
        if e.get('edge_type') == 'ESTABLISHES':
            establishes_by_case[e['source_id']].append(e['target_id'])

    for overruler, overruled in overrules_edges:
        established = establishes_by_case.get(overruled, [])
        if established:
            r.warning('W001',
                      f"'{overruler}' overrules '{overruled}' which ESTABLISHED: {established}. "
                      "Confirm whether each also needs an OVERRULES or MODIFIES edge.",
                      f"OVERRULES:{overruler}->{overruled}")

    # W002: stale pending_establishment
    for nid, node in nodes.items():
        pe = node.get('pending_establishment', [])
        if pe:
            r.warning('W002',
                      f"Node has {len(pe)} pending_establishment entries — verify these are being tracked for resolution",
                      f"Node:{nid}")


# ── Main ──────────────────────────────────────────────────────────────────────

def validate_file(filepath, combined_filepath=None, draft_mode=False):
    print(f"\nValidating: {filepath}")
    print("─" * 60)

    with open(filepath) as f:
        data = json.load(f)

    nodes, node_types = flatten_nodes(data)

    # Build cross-slice ok set from meta
    cross_slice_ok = set()
    for dep in data.get('meta', {}).get('cross_slice_dependencies', []):
        node_id = dep.split(' ')[0]
        cross_slice_ok.add(node_id)

    # If combined graph provided, use it for cross-slice resolution
    if combined_filepath:
        with open(combined_filepath) as f:
            combined = json.load(f)
        combined_nodes, combined_types = flatten_nodes(combined)
        for nid in combined_nodes:
            if nid not in nodes:
                cross_slice_ok.add(nid)
                node_types[nid] = combined_types.get(nid, 'Unknown')

    edges = data.get('edges', [])
    r = ValidationResult()

    # Validate each node
    validators = {
        'Area': validate_area,
        'Doctrine': validate_doctrine,
        'Case': validate_case,
        'DoctrinalTest': validate_doctrinal_test,
        'ConstitutionalProvision': validate_constitutional_provision,
    }
    for nid, node in nodes.items():
        ntype = node_types.get(nid, '')
        if ntype in validators:
            validators[ntype](node, r)

    # Validate edges
    validate_edges(edges, nodes, node_types, cross_slice_ok, r)

    # Graph-level validation
    validate_graph_level(nodes, node_types, edges, cross_slice_ok, r, draft_mode=draft_mode)

    # Print results
    n_nodes = sum(len(v) for v in data.get('nodes', {}).values())
    n_edges = len(edges)
    n_issues = len(data.get('schema_issues_found', []))

    if draft_mode:
        print("[DRAFT MODE — E016 orphan checks suppressed]")

    print(f"Nodes: {n_nodes}  |  Edges: {n_edges}  |  Schema issues documented: {n_issues}")
    print()

    if r.errors:
        print(f"ERRORS ({len(r.errors)}):")
        for e in r.errors:
            print(e)
        print()

    if r.warnings:
        print(f"WARNINGS ({len(r.warnings)}):")
        for w in r.warnings:
            print(w)
        print()

    status = "✓ PASS" if r.ok() else "✗ FAIL"
    print(f"Result: {status} — {r.summary()}")
    return r.ok()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Validate a U.S. Law Knowledge Graph slice or combined graph')
    parser.add_argument('--file', required=True, help='Path to the JSON file to validate')
    parser.add_argument('--combined', help='Path to combined graph (for cross-slice reference resolution)')
    parser.add_argument('--draft', action='store_true', help='Draft mode: suppress E016 orphan node errors')
    args = parser.parse_args()

    ok = validate_file(args.file, args.combined, draft_mode=args.draft)
    sys.exit(0 if ok else 1)
