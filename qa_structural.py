#!/usr/bin/env python3
"""
LexGraph — QA: Structural Agent
Rule-based graph traversal checks using NetworkX.
Catches temporal inconsistencies, orphaned nodes, and logical edge errors
that pass schema validation but are structurally wrong.

Usage:
    python qa_structural.py --draft draft_sdp_graph.json
    python qa_structural.py --draft draft_sdp_graph.json --combined conlaw_graph_v02.json

Error codes:
    S001 — Temporal: OVERRULES edge impossible (overruler predates overruled)
    S002 — Temporal: APPLIES/MODIFIES edge to test that didn't exist yet
    S003 — Temporal: DISTINGUISHES edge to future case
    S004 — Temporal: ESTABLISHES edge date mismatch (case date ≠ doctrine valid_from)
    S005 — Connectivity: Doctrine area_id not found in graph
    S006 — Connectivity: DoctrinalTest source_case_id not found in graph
    S007 — Connectivity: OVERRULES target status is not 'overruled'
    S008 — Consistency: DoctrinalTest has source_case_id but no ESTABLISHES edge
    S009 — Consistency: Case status='overruled' but valid_until is null
    S010 — Consistency: Case status='good_law' but valid_until is populated
"""

import json
import sys
import argparse
from datetime import date, datetime
from collections import defaultdict

# ─── Utilities ────────────────────────────────────────────────────────────────

def parse_date(date_str):
    """Parse a date string to a date object. Returns None if unparseable."""
    if not date_str:
        return None
    try:
        if len(date_str) == 10:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        elif len(date_str) == 4:
            return date(int(date_str), 1, 1)
    except (ValueError, TypeError):
        pass
    return None

class Result:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, code, message, location=""):
        self.errors.append({"code": code, "message": message, "location": location})

    def warning(self, code, message, location=""):
        self.warnings.append({"code": code, "message": message, "location": location})

# ─── Graph Loading ─────────────────────────────────────────────────────────────

def load_graph(filepath):
    """Load a graph JSON file and return (nodes_dict, edges_list)."""
    with open(filepath) as f:
        data = json.load(f)

    nodes = {}
    for ntype, arr in data.get("nodes", {}).items():
        for node in arr:
            nid = node.get("id")
            if nid:
                nodes[nid] = node

    edges = data.get("edges", [])
    return nodes, edges

def merge_graphs(draft_nodes, draft_edges, combined_nodes, combined_edges):
    """Merge draft into combined graph for cross-reference checks."""
    all_nodes = dict(combined_nodes)
    all_nodes.update(draft_nodes)  # draft takes precedence

    seen_triples = set()
    all_edges = []
    for e in combined_edges:
        key = (e.get("source_id"), e.get("target_id"), e.get("edge_type"))
        if key not in seen_triples:
            all_edges.append(e)
            seen_triples.add(key)
    for e in draft_edges:
        key = (e.get("source_id"), e.get("target_id"), e.get("edge_type"))
        if key not in seen_triples:
            all_edges.append(e)
            seen_triples.add(key)

    return all_nodes, all_edges

# ─── Checks ───────────────────────────────────────────────────────────────────

def check_temporal_consistency(draft_nodes, draft_edges, all_nodes, r):
    """S001-S004: Temporal consistency checks."""

    for e in draft_edges:
        etype = e.get("edge_type")
        sid = e.get("source_id")
        tid = e.get("target_id")
        eid = e.get("id", "?")

        source = all_nodes.get(sid, {})
        target = all_nodes.get(tid, {})

        source_date = parse_date(source.get("decided_date") or source.get("valid_from"))
        target_date = parse_date(target.get("decided_date") or target.get("valid_from"))

        # S001: OVERRULES — overruler must postdate overruled
        if etype == "OVERRULES" and source_date and target_date:
            if source_date <= target_date:
                r.error("S001",
                    f"OVERRULES temporal impossibility: {sid} ({source_date}) "
                    f"cannot overrule {tid} ({target_date}) — overruler does not postdate overruled",
                    f"Edge:{eid}")

        # S002: APPLIES/MODIFIES to a test/doctrine that didn't exist yet
        # Warning only — valid_from on doctrines often reflects formal naming,
        # not when the doctrine began developing
        if etype in ("APPLIES", "MODIFIES") and source_date and target_date:
            if source_date < target_date:
                r.warning("S002",
                    f"{etype} anachronism: {sid} ({source_date}) "
                    f"predates {tid} ({target_date}) — verify doctrine valid_from is correct",
                    f"Edge:{eid}")

        # S003: DISTINGUISHES — can't distinguish a future case
        if etype == "DISTINGUISHES" and source_date and target_date:
            if source_date < target_date:
                r.warning("S003",
                    f"DISTINGUISHES may be anachronistic: {sid} ({source_date}) "
                    f"distinguishes {tid} ({target_date}) which was decided later",
                    f"Edge:{eid}")

    # S004: ESTABLISHES date mismatch
    for e in draft_edges:
        if e.get("edge_type") == "ESTABLISHES":
            sid = e.get("source_id")
            tid = e.get("target_id")
            source = all_nodes.get(sid, {})
            target = all_nodes.get(tid, {})
            source_date = parse_date(source.get("decided_date"))
            target_date = parse_date(target.get("valid_from"))
            if source_date and target_date and source_date != target_date:
                # Allow same year as a warning rather than error
                if source_date.year != target_date.year:
                    r.error("S004",
                        f"ESTABLISHES date mismatch: {sid} decided {source_date} "
                        f"but {tid}.valid_from is {target_date}",
                        f"Edge:{e.get('id','?')}")
                elif abs(source_date.year - target_date.year) <= 10:
                    r.warning("S004",
                        f"ESTABLISHES date mismatch: {sid} decided {source_date} "
                        f"but {tid}.valid_from is {target_date} — verify valid_from on doctrine",
                        f"Edge:{e.get('id','?')}")
                else:
                    r.error("S004",
                        f"ESTABLISHES date mismatch: {sid} decided {source_date} "
                        f"but {tid}.valid_from is {target_date} — large gap, likely wrong",
                        f"Edge:{e.get('id','?')}")

def check_connectivity(draft_nodes, draft_edges, all_nodes, r):
    """S005-S007: Connectivity checks."""

    # Build edge index
    edges_by_source = defaultdict(list)
    edges_by_target = defaultdict(list)
    for e in draft_edges:
        edges_by_source[e.get("source_id")].append(e)
        edges_by_target[e.get("target_id")].append(e)

    for nid, node in draft_nodes.items():
        ntype = node.get("@type")

        # S005: Doctrine area_id must exist in graph
        if ntype == "Doctrine":
            area_id = node.get("area_id")
            if area_id and area_id not in all_nodes:
                r.error("S005",
                    f"area_id '{area_id}' not found in graph — "
                    f"must be an existing Area node ID",
                    f"Doctrine:{nid}")

        # S006: DoctrinalTest source_case_id must exist
        if ntype == "DoctrinalTest":
            scid = node.get("source_case_id")
            if scid and scid not in all_nodes:
                r.error("S006",
                    f"source_case_id '{scid}' not found in graph",
                    f"DoctrinalTest:{nid}")

    # S007: OVERRULES target must have status='overruled'
    for e in draft_edges:
        if e.get("edge_type") == "OVERRULES":
            tid = e.get("target_id")
            target = all_nodes.get(tid, {})
            if target and target.get("status") != "overruled":
                r.error("S007",
                    f"OVERRULES target '{tid}' has status='{target.get('status')}' "
                    f"— should be 'overruled'",
                    f"Edge:{e.get('id','?')}")

def check_consistency(draft_nodes, draft_edges, all_nodes, r):
    """S008-S010: Internal consistency checks."""

    # Build ESTABLISHES map
    establishes_targets = defaultdict(list)
    for e in draft_edges:
        if e.get("edge_type") == "ESTABLISHES":
            establishes_targets[e.get("source_id")].append(e.get("target_id"))

    for nid, node in draft_nodes.items():
        ntype = node.get("@type")

        # S008: DoctrinalTest with source_case_id but no ESTABLISHES edge
        if ntype == "DoctrinalTest":
            scid = node.get("source_case_id")
            if scid:
                case_establishes = establishes_targets.get(scid, [])
                if nid not in case_establishes:
                    r.warning("S008",
                        f"source_case_id='{scid}' set but no ESTABLISHES edge "
                        f"from that case to this test found in draft",
                        f"DoctrinalTest:{nid}")

        # S009: Case overruled but valid_until is null
        if ntype == "Case":
            if node.get("status") == "overruled" and node.get("valid_until") is None:
                r.error("S009",
                    f"Case status='overruled' but valid_until is null — "
                    f"overruled cases must have valid_until populated",
                    f"Case:{nid}")

        # S010: Case good_law but valid_until is populated
        if ntype == "Case":
            if node.get("status") == "good_law" and node.get("valid_until") is not None:
                r.warning("S010",
                    f"Case status='good_law' but valid_until='{node['valid_until']}' — "
                    f"verify this case is still good law",
                    f"Case:{nid}")

# ─── Main ─────────────────────────────────────────────────────────────────────

def run_qa_structural(draft_path, combined_path=None):
    print(f"\nQA: Structural Agent")
    print("─" * 60)
    print(f"Draft:    {draft_path}")
    if combined_path:
        print(f"Combined: {combined_path}")
    print()

    draft_nodes, draft_edges = load_graph(draft_path)

    if combined_path:
        combined_nodes, combined_edges = load_graph(combined_path)
        all_nodes, all_edges = merge_graphs(
            draft_nodes, draft_edges, combined_nodes, combined_edges)
    else:
        all_nodes = draft_nodes
        all_edges = draft_edges

    print(f"Draft nodes: {len(draft_nodes)} | Draft edges: {len(draft_edges)}")
    if combined_path:
        print(f"Combined nodes: {len(all_nodes)} (after merge)")
    print()

    r = Result()

    check_temporal_consistency(draft_nodes, draft_edges, all_nodes, r)
    check_connectivity(draft_nodes, draft_edges, all_nodes, r)
    check_consistency(draft_nodes, draft_edges, all_nodes, r)

    # Print results
    print("─" * 60)

    if r.errors:
        print(f"ERRORS ({len(r.errors)}):")
        for e in r.errors:
            print(f"  ✗ {e['code']}: [{e['location']}] {e['message']}")
    
    if r.warnings:
        print(f"\nWARNINGS ({len(r.warnings)}):")
        for w in r.warnings:
            print(f"  ⚠ {w['code']}: [{w['location']}] {w['message']}")

    print()
    if r.errors:
        print(f"Result: ✗ FAIL — {len(r.errors)} errors, {len(r.warnings)} warnings")
    else:
        print(f"Result: ✓ PASS — 0 errors, {len(r.warnings)} warnings")

    return len(r.errors) == 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="QA: Structural Agent — graph traversal consistency checks"
    )
    parser.add_argument("--draft", required=True, help="Path to draft JSON file")
    parser.add_argument("--combined", help="Path to combined master graph (for cross-reference)")
    args = parser.parse_args()

    ok = run_qa_structural(args.draft, args.combined)
    sys.exit(0 if ok else 1)
