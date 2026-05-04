#!/usr/bin/env python3
"""
LexGraph — QA: Doctrinal Review
Applies constitutional law expertise to check doctrinal completeness,
missing connections, and structural accuracy of draft graph nodes.

This is the "my perspective" layer — it checks things the LLM judges
can't see because they only have the draft in isolation:
  - Missing connections to existing graph nodes
  - Wrong scrutiny levels for tests
  - Doctrines that should be sub-typed differently
  - Cases that should MODIFIES an existing doctrine but use APPLIES
  - Tests that are missing prongs
  - Area_id mismatches

Unlike qa_legal.py (which evaluates legal accuracy of holdings),
qa_doctrinal.py evaluates structural and doctrinal completeness
of the graph representation.

Usage:
    python qa_doctrinal.py --draft draft.json --combined conlaw_graph_v02.json
    python qa_doctrinal.py --draft draft.json --combined conlaw_graph_v02.json --case terry_v_ohio_1968
"""

import json
import re
import argparse
from pathlib import Path

# ─── Known doctrine connections ─────────────────────────────────────────────────
# For each case pattern, what existing nodes should it connect to?
# These are the connections that the builder commonly misses.

EXPECTED_CONNECTIONS = {
    # First Amendment cases should connect to these areas/doctrines
    "area:free_speech": {
        "required_area_link": "free_speech",
        "common_missing": ["content_neutral_doctrine", "prior_restraint_doctrine"],
    },
    # Criminal procedure cases almost always touch these
    "area:criminal_procedure": {
        "common_missing": ["fourth_amendment_unreasonable_search", "exclusionary_rule"],
    },
    # Equal protection cases
    "area:equal_protection": {
        "common_missing": ["rational_basis_review", "strict_scrutiny_doctrine"],
    },
}

# Scrutiny level rules by test type
SCRUTINY_RULES = {
    # These test IDs should never have strict scrutiny
    "balancing": ["penn_central", "barker", "mathews", "pike"],
    # These should have strict scrutiny
    "strict": ["compelling_interest", "narrowly_tailored"],
    # Intermediate scrutiny patterns
    "intermediate": ["craig", "gender", "sex_based"],
    # Per se rules
    "per_se": ["loretto", "physical_occupation", "lucas", "total_deprivation"],
}

# Edge type rules — when a case should use MODIFIES not APPLIES
MODIFIES_TRIGGERS = {
    # If holding contains these patterns AND target exists, use MODIFIES
    "narrows": ["limits", "restrict", "narrow", "does not extend", "cannot extend"],
    "expands": ["extends", "expand", "broaden", "applies to", "also applies"],
    "clarifies": ["clarifies", "refines", "specifies", "defines more precisely"],
    "overrules": ["overrule", "overturn", "no longer", "abandoned"],
}

# Cases that should have Jackson's three-category framework attached
JACKSON_FRAMEWORK_CASES = [
    "youngstown_sheet_tube_co_v_sawyer_1952",
    "dames_moore_v_regan",
    "medellin_v_texas",
    "trump_v_hawaii",
    "zivotofsky_v_kerry_2015",
]

# Tests missing the prior conviction exception (Apprendi line)
APPRENDI_LINE = [
    "apprendi_v_new_jersey_2000",
    "blakely_v_washington_2004",
    "united_states_v_booker_2005",
    "alleyne_v_united_states",
]


# ─── Core check functions ────────────────────────────────────────────────────────

def check_scrutiny_levels(draft: dict) -> list:
    """Check if test scrutiny levels are correct."""
    findings = []
    for test in draft.get("nodes", {}).get("doctrinal_tests", []):
        test_id = test.get("id", "")
        scrutiny = test.get("scrutiny_level", "")
        test_form = test.get("test_form", "")

        # Balancing tests should not have strict scrutiny
        if test_form == "balancing" and scrutiny == "strict":
            findings.append({
                "severity": "medium",
                "field": "test",
                "node_id": test_id,
                "issue": f"Test '{test_id}' uses test_form='balancing' but scrutiny_level='strict' — balancing tests don't apply strict scrutiny",
                "suggestion": "Change scrutiny_level to 'balancing' or 'none'"
            })

        # Physical occupation / total deprivation are categorical, not strict
        if any(p in test_id for p in ["physical_occupation", "loretto", "total_deprivation", "lucas"]):
            if scrutiny == "strict":
                findings.append({
                    "severity": "medium",
                    "field": "test",
                    "node_id": test_id,
                    "issue": f"'{test_id}' is a categorical rule, not strict scrutiny",
                    "suggestion": "Change scrutiny_level to 'per_se'"
                })

        # Intermediate scrutiny patterns
        if any(p in test_id for p in ["intermediate", "craig", "gender"]):
            if scrutiny not in ("intermediate", "none"):
                findings.append({
                    "severity": "low",
                    "field": "test",
                    "node_id": test_id,
                    "issue": f"Gender/intermediate scrutiny test has scrutiny_level='{scrutiny}'",
                    "suggestion": "Consider scrutiny_level='intermediate'"
                })

        # Rational basis should not be used for criminal procedure tests
        area = test.get("area_id", "")
        if area == "criminal_procedure" and scrutiny == "rational_basis":
            findings.append({
                "severity": "medium",
                "field": "test",
                "node_id": test_id,
                "issue": f"Criminal procedure test '{test_id}' uses rational_basis scrutiny — unusual",
                "suggestion": "Criminal procedure tests typically use 'none', 'balancing', or 'per_se'"
            })

    return findings


def check_area_ids(draft: dict) -> list:
    """Check for common area_id mismatches."""
    findings = []
    all_nodes = []
    for ntype, nodes in draft.get("nodes", {}).items():
        for n in nodes:
            n["_type"] = ntype
            all_nodes.append(n)

    for node in all_nodes:
        area = node.get("area_id", "")
        node_id = node.get("id", "")

        # Procedural due process nodes shouldn't be in substantive_due_process
        if area == "substantive_due_process":
            pdp_signals = ["welfare", "termination", "hearing", "property interest",
                          "liberty interest", "pretermination", "notice and opportunity",
                          "enemy combatant", "mathews", "goldberg", "loudermill"]
            desc = (node.get("description", "") + " " + node.get("label", "")).lower()
            if any(s in desc for s in pdp_signals):
                findings.append({
                    "severity": "medium",
                    "field": "doctrine",
                    "node_id": node_id,
                    "issue": f"'{node_id}' appears to be procedural due process but has area_id='substantive_due_process'",
                    "suggestion": "Change area_id to 'procedural_due_process' or 'individual_rights'"
                })

        # Criminal procedure nodes shouldn't be in individual_rights
        if area == "individual_rights":
            crim_signals = ["fourth amendment", "fifth amendment", "sixth amendment",
                           "exclusionary", "search", "seizure", "miranda", "custodial",
                           "self-incrimination"]
            desc = (node.get("description", "") + " " + node.get("label", "")).lower()
            if any(s in desc for s in crim_signals):
                findings.append({
                    "severity": "low",
                    "field": "doctrine",
                    "node_id": node_id,
                    "issue": f"'{node_id}' appears to be criminal procedure but has area_id='individual_rights'",
                    "suggestion": "Consider area_id='criminal_procedure'"
                })

        # Takings nodes should be in takings_clause
        if area == "constitutional_law":
            takings_signals = ["taking", "just compensation", "public use", "physical occupation",
                              "regulatory taking", "eminent domain"]
            desc = (node.get("description", "") + " " + node.get("label", "")).lower()
            if any(s in desc for s in takings_signals):
                findings.append({
                    "severity": "low",
                    "field": "doctrine",
                    "node_id": node_id,
                    "issue": f"'{node_id}' appears to be takings doctrine but has area_id='constitutional_law'",
                    "suggestion": "Consider area_id='takings_clause'"
                })

    return findings


def check_edge_types(draft: dict) -> list:
    """Check if edge types are appropriate — APPLIES vs MODIFIES."""
    findings = []
    cases = draft.get("nodes", {}).get("cases", [])
    holding = cases[0].get("holding", "").lower() if cases else ""

    for edge in draft.get("edges", []):
        etype = edge.get("edge_type", "")
        edge_id = edge.get("id", "")
        notes = (edge.get("notes", "") or "").lower()

        # APPLIES edges where MODIFIES might be more appropriate
        if etype == "APPLIES":
            for direction, triggers in MODIFIES_TRIGGERS.items():
                if any(t in holding or t in notes for t in triggers):
                    findings.append({
                        "severity": "low",
                        "field": "edge",
                        "node_id": edge_id,
                        "issue": f"Edge '{edge_id}' uses APPLIES but holding suggests MODIFIES (direction: {direction})",
                        "suggestion": f"Consider changing to MODIFIES with direction='{direction}'"
                    })
                    break

        # MODIFIES edges missing direction attribute
        if etype == "MODIFIES" and not edge.get("direction"):
            findings.append({
                "severity": "high",
                "field": "edge",
                "node_id": edge_id,
                "issue": f"MODIFIES edge '{edge_id}' missing required 'direction' attribute",
                "suggestion": "Add direction: narrows | expands | clarifies | complicates | repudiates"
            })

        # OVERRULES edges missing overrule_type
        if etype == "OVERRULES" and not edge.get("overrule_type"):
            findings.append({
                "severity": "high",
                "field": "edge",
                "node_id": edge_id,
                "issue": f"OVERRULES edge '{edge_id}' missing required 'overrule_type' attribute",
                "suggestion": "Add overrule_type: explicit | implicit | effective"
            })

    return findings


def check_missing_connections(draft: dict, master: dict) -> list:
    """Check for missing connections to existing graph nodes."""
    findings = []
    if not master:
        return findings

    existing_ids = {n["id"] for arr in master.get("nodes", {}).values() for n in arr}
    draft_node_ids = {n["id"] for arr in draft.get("nodes", {}).values() for n in arr}
    edge_targets = {e["target_id"] for e in draft.get("edges", [])}
    edge_sources = {e["source_id"] for e in draft.get("edges", [])}

    cases = draft.get("nodes", {}).get("cases", [])
    if not cases:
        return findings

    case = cases[0]
    case_id = case.get("id", "")
    holding = (case.get("holding", "") or "").lower()
    notes = (case.get("notes", "") or "").lower()

    # Check for Apprendi line cases missing connection to apprendi_rule
    if case_id in APPRENDI_LINE:
        if "apprendi_rule" in existing_ids and "apprendi_rule" not in edge_targets:
            findings.append({
                "severity": "medium",
                "field": "missing",
                "node_id": case_id,
                "issue": "Apprendi-line case missing connection to 'apprendi_rule' node",
                "suggestion": "Add APPLIES edge to 'apprendi_rule'"
            })

    # Check for Jackson framework cases
    if case_id in JACKSON_FRAMEWORK_CASES:
        if "youngstown_jackson_framework" in existing_ids and \
           "youngstown_jackson_framework" not in edge_targets:
            findings.append({
                "severity": "medium",
                "field": "missing",
                "node_id": case_id,
                "issue": "Separation of powers case should connect to Youngstown Jackson framework",
                "suggestion": "Add APPLIES edge to 'youngstown_jackson_framework'"
            })

    # Check for Miranda-related cases missing miranda_doctrine connection
    miranda_signals = ["miranda warning", "custodial interrogation", "right to remain silent",
                      "fifth amendment", "self-incrimination", "in custody"]
    if any(s in holding for s in miranda_signals):
        if "miranda_doctrine" in existing_ids and "miranda_doctrine" not in edge_targets:
            findings.append({
                "severity": "medium",
                "field": "missing",
                "node_id": case_id,
                "issue": "Case involves Miranda doctrine but has no edge to 'miranda_doctrine'",
                "suggestion": "Add APPLIES or MODIFIES edge to 'miranda_doctrine'"
            })

    # Check for Terry stop cases missing terry_stop_frisk_test
    terry_signals = ["reasonable suspicion", "stop and frisk", "terry stop", "investigatory stop",
                    "patdown", "pat-down"]
    if any(s in holding for s in terry_signals):
        if "terry_stop_frisk_test" in existing_ids and "terry_stop_frisk_test" not in edge_targets:
            findings.append({
                "severity": "medium",
                "field": "missing",
                "node_id": case_id,
                "issue": "Case involves Terry stop doctrine but has no edge to 'terry_stop_frisk_test'",
                "suggestion": "Add APPLIES or MODIFIES edge to 'terry_stop_frisk_test'"
            })

    # Check for exclusionary rule cases missing exclusionary_rule connection
    exclusion_signals = ["exclusionary rule", "fruit of the poisonous tree", "suppress",
                        "suppression of evidence", "motion to suppress"]
    if any(s in holding or s in notes for s in exclusion_signals):
        if "exclusionary_rule" in existing_ids and "exclusionary_rule" not in edge_targets:
            findings.append({
                "severity": "low",
                "field": "missing",
                "node_id": case_id,
                "issue": "Case involves exclusionary rule but has no edge to 'exclusionary_rule'",
                "suggestion": "Add APPLIES or MODIFIES edge to 'exclusionary_rule'"
            })

    # Check for dormant commerce clause cases
    dcc_signals = ["dormant commerce clause", "discriminates against interstate",
                  "burden on interstate commerce", "pike balancing"]
    if any(s in holding or s in notes for s in dcc_signals):
        if "dormant_commerce_clause" in existing_ids and "dormant_commerce_clause" not in edge_targets:
            findings.append({
                "severity": "medium",
                "field": "missing",
                "node_id": case_id,
                "issue": "Case involves dormant Commerce Clause but has no edge to 'dormant_commerce_clause'",
                "suggestion": "Add APPLIES or MODIFIES edge to 'dormant_commerce_clause'"
            })

    # Check for equal protection cases missing discriminatory purpose doctrine
    ep_signals = ["discriminatory purpose", "discriminatory intent", "washington v. davis",
                 "arlington heights"]
    if any(s in holding or s in notes for s in ep_signals):
        if "discriminatory_purpose_doctrine" in existing_ids and \
           "discriminatory_purpose_doctrine" not in edge_targets:
            findings.append({
                "severity": "low",
                "field": "missing",
                "node_id": case_id,
                "issue": "Case references discriminatory purpose doctrine but has no edge to it",
                "suggestion": "Add APPLIES edge to 'discriminatory_purpose_doctrine'"
            })

    return findings


def check_prong_completeness(draft: dict) -> list:
    """Check if doctrinal tests have complete prong coverage."""
    findings = []
    for test in draft.get("nodes", {}).get("doctrinal_tests", []):
        test_id = test.get("id", "")
        prongs = test.get("prongs", [])
        test_form = test.get("test_form", "")
        desc = test.get("description", "").lower()

        # Conjunctive tests should have at least 2 prongs
        if test_form in ("conjunctive", "threshold_then_conjunctive") and len(prongs) < 2:
            findings.append({
                "severity": "medium",
                "field": "test",
                "node_id": test_id,
                "issue": f"Conjunctive test '{test_id}' has only {len(prongs)} prong(s) — likely incomplete",
                "suggestion": "Verify all prongs are captured"
            })

        # Balancing tests should have at least 2 factors
        if test_form == "balancing" and len(prongs) < 2:
            findings.append({
                "severity": "low",
                "field": "test",
                "node_id": test_id,
                "issue": f"Balancing test '{test_id}' has only {len(prongs)} factor(s)",
                "suggestion": "Balancing tests typically identify 2+ factors"
            })

        # Check for missing burden_note on prongs
        for prong in prongs:
            if not prong.get("burden_note"):
                findings.append({
                    "severity": "low",
                    "field": "test",
                    "node_id": test_id,
                    "issue": f"Prong {prong.get('number')} of '{test_id}' missing burden_note",
                    "suggestion": "Add burden_note indicating who bears the burden for this prong"
                })
                break  # Only flag once per test

    return findings


def check_valid_from_dates(draft: dict) -> list:
    """Check for placeholder dates (Jan 1 of a year)."""
    findings = []
    for ntype, nodes in draft.get("nodes", {}).items():
        for node in nodes:
            date = node.get("decided_date", "") or node.get("valid_from", "")
            node_id = node.get("id", "")
            if date and re.match(r'^\d{4}-01-01$', date):
                findings.append({
                    "severity": "low",
                    "field": "case",
                    "node_id": node_id,
                    "issue": f"Date '{date}' appears to be a placeholder (Jan 1) — verify actual date",
                    "suggestion": "Look up the actual decision date"
                })
    return findings


# ─── Main review function ────────────────────────────────────────────────────────

def run_qa_doctrinal(draft_path: str, combined_path: str = None, case_filter: str = None) -> dict:
    """Run doctrinal completeness review on a draft."""

    with open(draft_path) as f:
        draft = json.load(f)

    master = None
    if combined_path and Path(combined_path).exists():
        with open(combined_path) as f:
            master = json.load(f)

    cases = draft.get("nodes", {}).get("cases", [])
    if case_filter:
        cases = [c for c in cases if c.get("id") == case_filter]

    if not cases:
        return {"findings": [], "summary": "No cases to review"}

    print(f"\nQA: Doctrinal Review")
    print(f"{'─'*60}")
    print(f"Draft: {draft_path}")
    print(f"Cases: {len(cases)}")

    all_findings = []

    # Run all checks
    all_findings.extend(check_scrutiny_levels(draft))
    all_findings.extend(check_area_ids(draft))
    all_findings.extend(check_edge_types(draft))
    all_findings.extend(check_prong_completeness(draft))
    all_findings.extend(check_valid_from_dates(draft))
    if master:
        all_findings.extend(check_missing_connections(draft, master))

    # Report
    high = [f for f in all_findings if f["severity"] == "high"]
    medium = [f for f in all_findings if f["severity"] == "medium"]
    low = [f for f in all_findings if f["severity"] == "low"]

    print(f"\nFindings: {len(high)} high | {len(medium)} medium | {len(low)} low")

    if high:
        print("\nHIGH (fix before merge):")
        for f in high:
            print(f"  ✗ [{f['field']}] {f['node_id']}")
            print(f"    {f['issue']}")
            print(f"    → {f['suggestion']}")

    if medium:
        print("\nMEDIUM (review recommended):")
        for f in medium:
            print(f"  ⚠ [{f['field']}] {f['node_id']}")
            print(f"    {f['issue']}")
            print(f"    → {f['suggestion']}")

    if low:
        print("\nLOW (informational):")
        for f in low:
            print(f"  · [{f['field']}] {f['node_id']}: {f['issue']}")

    if not all_findings:
        print("  ✓ No doctrinal issues found")

    return {
        "findings": all_findings,
        "counts": {"high": len(high), "medium": len(medium), "low": len(low)},
        "verdict": "fail" if high else ("warn" if medium else "pass")
    }


# ─── Pipeline integration ────────────────────────────────────────────────────────

def step_qa_doctrinal(result: dict, combined_path: str = None) -> bool:
    """Step 7: Run doctrinal review. Returns True if no high findings."""
    draft_path = result.get("draft_path")
    if not draft_path or not Path(draft_path).exists():
        result["qa_doctrinal_status"] = "skipped"
        return True

    try:
        report = run_qa_doctrinal(draft_path, combined_path)
        result["qa_doctrinal_findings"] = report["findings"]
        result["qa_doctrinal_high"] = report["counts"]["high"]
        result["qa_doctrinal_medium"] = report["counts"]["medium"]
        result["qa_doctrinal_low"] = report["counts"]["low"]
        result["qa_doctrinal_status"] = report["verdict"]
        return report["counts"]["high"] == 0
    except Exception as e:
        result["qa_doctrinal_status"] = "error"
        result["qa_doctrinal_error"] = str(e)
        return True  # Don't block pipeline on doctrinal errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QA: Doctrinal Review")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--combined", help="Master graph for connection checks")
    parser.add_argument("--case", help="Specific case ID to review")
    args = parser.parse_args()
    run_qa_doctrinal(args.draft, args.combined, args.case)
