#!/usr/bin/env python3
"""
LexGraph — QA: Factual Agent v1.1
Validates Case node metadata against CourtListener API.

Usage:
    python qa_factual.py --draft draft_sdp_graph.json --output qa_factual_report.json
    python qa_factual.py --draft draft_sdp_graph.json --patch  # also writes patched draft

Requires: COURTLISTENER_API_KEY environment variable
"""

import json
import os
import sys
import argparse
import time
import requests
from difflib import SequenceMatcher

COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v4"

def get_headers():
    key = os.environ.get("COURTLISTENER_API_KEY")
    if not key:
        print("ERROR: COURTLISTENER_API_KEY environment variable not set")
        sys.exit(1)
    return {"Authorization": f"Token {key}"}

def similarity(a, b):
    """String similarity ratio 0-1."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def search_courtlistener(case_node):
    """
    Search CourtListener for a case using the clusters endpoint.
    Returns the best matching cluster dict, or None.
    """
    citation = case_node.get("citation", "")
    short_name = case_node.get("short_name", "")
    decided_date = case_node.get("decided_date", "")
    court_level = case_node.get("court_level", "")
    headers = get_headers()

    # Map court_level to CourtListener court ID
    court_map = {
        "scotus": "scotus",
        "circuit": None,  # varies by circuit
        "district": None,
    }
    cl_court = court_map.get(court_level)

    # Strategy 1: clusters endpoint with citation string
    if citation:
        reporter_cite = citation.split("(")[0].strip()
        params = {"citation": reporter_cite}
        if cl_court:
            params["court"] = cl_court
        try:
            resp = requests.get(
                f"{COURTLISTENER_BASE}/clusters/",
                params=params,
                headers=headers,
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if results:
                # Verify name similarity to avoid false matches
                best = results[0]
                cl_name = best.get("case_name_short") or best.get("case_name", "")
                if similarity(short_name, cl_name) > 0.4:
                    return best, "cluster_citation"
                else:
                    print(f"    Citation matched '{cl_name}' but name similarity too low — trying name search")
        except Exception as e:
            print(f"    Cluster citation search failed: {e}")
        time.sleep(0.5)

    # Strategy 2: clusters endpoint with case name + year + court
    if short_name:
        params = {"case_name": short_name}
        if cl_court:
            params["court"] = cl_court
        if decided_date:
            year = decided_date[:4]
            params["filed_after"] = f"{year}-01-01"
            params["filed_before"] = f"{year}-12-31"
        try:
            resp = requests.get(
                f"{COURTLISTENER_BASE}/clusters/",
                params=params,
                headers=headers,
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if results:
                best = max(
                    results[:5],
                    key=lambda r: similarity(
                        short_name,
                        r.get("case_name_short") or r.get("case_name", "")
                    )
                )
                cl_name = best.get("case_name_short") or best.get("case_name", "")
                if similarity(short_name, cl_name) > 0.5:
                    return best, "cluster_name"
        except Exception as e:
            print(f"    Cluster name search failed: {e}")
        time.sleep(0.5)

    # Strategy 3: full-text search as fallback
    if short_name:
        params = {
            "q": f'"{short_name}"',
            "type": "o",
            "order_by": "score desc",
            "stat_Precedential": "on",
        }
        if cl_court:
            params["court"] = cl_court
        if decided_date:
            year = decided_date[:4]
            params["filed_after"] = f"{year}-01-01"
            params["filed_before"] = f"{year}-12-31"
        try:
            resp = requests.get(
                f"{COURTLISTENER_BASE}/search/",
                params=params,
                headers=headers,
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if results:
                best = max(
                    results[:5],
                    key=lambda r: similarity(short_name, r.get("caseName", ""))
                )
                if similarity(short_name, best.get("caseName", "")) > 0.5:
                    # Convert search result to cluster-like format
                    return {
                        "case_name_short": best.get("caseName", ""),
                        "case_name": best.get("caseName", ""),
                        "date_filed": best.get("dateFiled", ""),
                        "court": best.get("court", ""),
                        "judges": best.get("judge", ""),
                        "id": best.get("cluster_id", ""),
                    }, "fulltext_search"
        except Exception as e:
            print(f"    Full-text search failed: {e}")

    return None, None

def extract_cl_facts(cl_result):
    """Extract the facts we care about from a CourtListener cluster result."""
    if not cl_result:
        return {}
    facts = {}
    facts["case_name"] = (
        cl_result.get("case_name_short") or
        cl_result.get("case_name") or
        cl_result.get("caseName", "")
    )
    facts["date_filed"] = (
        cl_result.get("date_filed") or
        cl_result.get("dateFiled", "")
    )
    facts["court"] = cl_result.get("court", "")
    facts["author"] = cl_result.get("judges", "") or cl_result.get("judge", "") or ""
    facts["cluster_id"] = str(cl_result.get("id", ""))
    if facts["cluster_id"]:
        facts["courtlistener_url"] = (
            f"https://www.courtlistener.com/opinion/{facts['cluster_id']}/"
        )
    return facts

def compare_case(case_node, cl_facts):
    """Compare Case node fields against CourtListener facts."""
    findings = []
    case_id = case_node.get("id", "?")

    # Check decided_date year
    draft_date = case_node.get("decided_date", "")
    cl_date = cl_facts.get("date_filed", "")
    if draft_date and cl_date:
        draft_year = draft_date[:4]
        cl_year = cl_date[:4]
        if draft_year != cl_year:
            findings.append({
                "field": "decided_date",
                "severity": "high",
                "draft_value": draft_date,
                "cl_value": cl_date,
                "message": f"Year mismatch: draft={draft_year}, CourtListener={cl_year}"
            })

    # Check majority_author
    draft_author = case_node.get("majority_author")
    cl_author = cl_facts.get("author", "")
    if not draft_author and cl_author:
        findings.append({
            "field": "majority_author",
            "severity": "medium",
            "draft_value": None,
            "cl_value": cl_author,
            "message": f"majority_author is null — CourtListener judges field: '{cl_author}' (verify manually)",
            "auto_patch": False
        })
    elif draft_author and cl_author:
        clean_draft = draft_author.split("(")[0].strip().lower()
        if clean_draft and cl_author and similarity(clean_draft, cl_author.lower()) < 0.4:
            findings.append({
                "field": "majority_author",
                "severity": "low",
                "draft_value": draft_author,
                "cl_value": cl_author,
                "message": f"Author names differ: draft='{draft_author}', CL='{cl_author}'"
            })

    # Check case name similarity
    draft_name = case_node.get("short_name", "")
    cl_name = cl_facts.get("case_name", "")
    if draft_name and cl_name:
        sim = similarity(draft_name, cl_name)
        if sim < 0.5:
            findings.append({
                "field": "short_name",
                "severity": "high",
                "draft_value": draft_name,
                "cl_value": cl_name,
                "message": f"Case name similarity low ({sim:.2f}): draft='{draft_name}', CL='{cl_name}' — possible hallucination or wrong match"
            })

    return findings

def run_qa_factual(draft_path, output_path, patch=False):
    """Main QA: Factual pass."""
    print(f"\nQA: Factual Agent v1.1")
    print("─" * 60)
    print(f"Draft:  {draft_path}")
    print(f"Output: {output_path}")
    print()

    with open(draft_path) as f:
        draft = json.load(f)

    cases = draft.get("nodes", {}).get("cases", [])
    print(f"Cases to check: {len(cases)}")
    print()

    report = {
        "draft_file": draft_path,
        "cases_checked": len(cases),
        "cases_found_in_cl": 0,
        "cases_not_found": [],
        "findings": [],
        "patches": []
    }

    for case in cases:
        case_id = case.get("id", "?")
        short_name = case.get("short_name", case_id)
        print(f"  Checking: {short_name}")

        cl_result, strategy = search_courtlistener(case)

        if not cl_result:
            print(f"    ✗ Not found in CourtListener")
            report["cases_not_found"].append({
                "case_id": case_id,
                "short_name": short_name,
                "severity": "medium",
                "message": "Case not found — verify case exists and check for hallucination"
            })
            continue

        report["cases_found_in_cl"] += 1
        cl_facts = extract_cl_facts(cl_result)
        cl_display = cl_facts.get("case_name", "")[:60]
        print(f"    ✓ Found via {strategy}: {cl_display}")

        # Auto-patch courtlistener_id if missing
        cl_id = cl_facts.get("cluster_id")
        if cl_id and not case.get("courtlistener_id"):
            report["patches"].append({
                "case_id": case_id,
                "field": "courtlistener_id",
                "value": cl_id,
                "auto_apply": True
            })

        # Compare fields
        findings = compare_case(case, cl_facts)
        if findings:
            for f in findings:
                f["case_id"] = case_id
                report["findings"].append(f)
                sev = f["severity"].upper()
                print(f"    [{sev}] {f['field']}: {f['message']}")
        else:
            print(f"    ✓ No discrepancies found")

        time.sleep(0.3)

    # Summary
    print()
    print("─" * 60)
    print(f"Cases checked:       {report['cases_checked']}")
    print(f"Found in CL:         {report['cases_found_in_cl']}")
    print(f"Not found:           {len(report['cases_not_found'])}")
    print(f"Findings:            {len(report['findings'])}")
    print(f"Auto-patchable IDs:  {len(report['patches'])}")

    high = [f for f in report["findings"] if f["severity"] == "high"]
    med  = [f for f in report["findings"] if f["severity"] == "medium"]
    low  = [f for f in report["findings"] if f["severity"] == "low"]
    print(f"  High: {len(high)}  Medium: {len(med)}  Low: {len(low)}")

    # Apply patches
    if patch and report["patches"]:
        print()
        print("Applying auto-patches...")
        case_map = {c["id"]: c for c in cases}
        for p in report["patches"]:
            if p.get("auto_apply"):
                node = case_map.get(p["case_id"])
                if node:
                    node[p["field"]] = p["value"]
                    print(f"  ✓ {p['case_id']}.{p['field']} = {p['value']}")
        patched_path = draft_path.replace(".json", "_patched.json")
        with open(patched_path, "w") as f:
            json.dump(draft, f, indent=2)
        print(f"  Patched draft saved to: {patched_path}")

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {output_path}")

    return len(high) == 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="QA: Factual Agent — validate Case nodes against CourtListener"
    )
    parser.add_argument("--draft", required=True, help="Path to draft JSON file")
    parser.add_argument("--output", default="qa_factual_report.json", help="Output report path")
    parser.add_argument("--patch", action="store_true", help="Apply auto-patches to draft")
    args = parser.parse_args()

    ok = run_qa_factual(args.draft, args.output, patch=args.patch)
    sys.exit(0 if ok else 1)
