#!/usr/bin/env python3
"""
LexGraph — QA: Legal Pre-Check
Fast identity and domain validation BEFORE calling LLM judges.
Catches wrong-case extractions without burning LLM API calls.

Two layers:
  Layer 1: Area-level domain check — holding should match the area's vocabulary
  Layer 2: Case-level override — specific forbidden/expected terms per known case

Returns:
  'pass'     → proceed to judges
  'fail'     → identity mismatch, move to needs_attention immediately
  'stub'     → 1 node, 0 edges, correct case — flag for thin-extraction prompt
  'unknown'  → not enough information to determine, proceed to judges with warning
"""

import json
import re
from pathlib import Path

# ─── Area-level domain signals ─────────────────────────────────────────────────
# Keys are area_id values from the schema.
# 'required': at least ONE of these must appear in the holding
# 'forbidden': if ANY of these appear, flag as wrong case

AREA_DOMAIN_SIGNALS = {
    "criminal_procedure": {
        "required": [
            "fourth amendment", "fifth amendment", "sixth amendment",
            "search", "seizure", "warrant", "arrest", "interrogation",
            "miranda", "counsel", "jury", "trial", "evidence",
            "suppression", "exclusionary", "probable cause", "reasonable suspicion",
            "defendant", "prosecution", "criminal", "conviction", "sentence",
            "custodial", "confession", "indictment", "grand jury"
        ],
        "forbidden": [
            "arbitration", "collective bargaining", "labor union", "nlrb",
            "admiralty", "bankruptcy", "patent", "copyright", "trademark",
            "securities", "antitrust", "insurance", "divorce", "custody",
            "laches", "union contract", "wage", "memorandum agreement"
        ]
    },
    "equal_protection": {
        "required": [
            "equal protection", "fourteenth amendment", "discrimination",
            "race", "gender", "sex", "classification", "scrutiny",
            "disparate", "minority", "protected class", "invidious"
        ],
        "forbidden": [
            "arbitration", "collective bargaining", "admiralty", "bankruptcy",
            "patent", "securities", "search", "seizure", "exclusionary rule",
            "miranda", "fourth amendment"
        ]
    },
    "substantive_due_process": {
        "required": [
            "due process", "fundamental right", "liberty", "fourteenth amendment",
            "privacy", "family", "marriage", "unenumerated", "substantive"
        ],
        "forbidden": [
            "arbitration", "collective bargaining", "admiralty", "patent",
            "securities", "antitrust", "search", "seizure"
        ]
    },
    "procedural_due_process": {
        "required": [
            "due process", "notice", "hearing", "property interest",
            "liberty interest", "opportunity", "deprivation", "process"
        ],
        "forbidden": [
            "arbitration", "collective bargaining", "admiralty", "patent",
            "fourth amendment", "search", "seizure"
        ]
    },
    "free_speech": {
        "required": [
            "first amendment", "speech", "expression", "press", "assembly",
            "petition", "content", "viewpoint", "forum", "prior restraint",
            "defamation", "obscenity", "incitement", "commercial speech"
        ],
        "forbidden": [
            "arbitration", "collective bargaining", "admiralty", "patent",
            "bankruptcy", "securities", "search", "seizure", "fourth amendment"
        ]
    },
    "constitutional_law": {
        "required": [
            "congress", "constitution", "federal", "state", "power",
            "clause", "amendment", "supremacy", "commerce", "spending",
            "president", "executive", "legislative", "judicial"
        ],
        "forbidden": [
            "arbitration", "collective bargaining", "nlrb", "admiralty",
            "patent infringement", "trademark", "copyright", "divorce",
            "laches in arbitration"
        ]
    },
    "individual_rights": {
        "required": [
            "right", "liberty", "freedom", "amendment", "protection",
            "citizen", "person", "government", "constitutional"
        ],
        "forbidden": [
            "arbitration", "collective bargaining", "nlrb",
            "admiralty", "patent", "trademark"
        ]
    }
}

# ─── Case-level overrides ───────────────────────────────────────────────────────
# For cases where we've seen wrong-case errors historically.
# 'expected': at least ONE must appear
# 'forbidden': if ANY appear, it's the wrong case

CASE_LEVEL_OVERRIDES = {
    "giglio_v_united_states_1972": {
        "expected": ["brady", "disclosure", "prosecution", "exculpatory",
                     "witness", "promise", "leniency", "material"],
        "forbidden": ["arbitration", "collective bargaining", "laches",
                      "union", "memorandum agreement", "steelworkers",
                      "air line pilots"]
    },
    "powers_v_ohio_1991": {
        "expected": ["peremptory", "juror", "race", "equal protection",
                     "batson", "jury selection", "standing"],
        "forbidden": ["arbitration", "collective bargaining", "air line pilots",
                      "steelworkers", "rawson", "tenth circuit"]
    },
    "ins_v_chadha_1983": {
        "expected": ["legislative veto", "bicameralism", "presentment",
                     "congress", "president", "veto", "article i"],
        "forbidden": ["deportation proceeding", "exclusionary rule",
                      "body of defendant", "civil deportation", "lopez-mendoza"]
    },
    "clinton_v_city_of_new_york_1998": {
        "expected": ["line item veto", "presentment", "article i",
                     "cancel", "enact", "legislation", "constitution"],
        "forbidden": ["armed forces", "court martial", "all writs act",
                      "military", "goldsmith", "air force"]
    },
    "j_e_b_v_alabama_1994": {
        "expected": ["peremptory", "gender", "sex", "jury", "equal protection",
                     "batson", "fourteenth amendment"],
        "forbidden": ["bankruptcy", "appellate", "vacatur", "moot",
                      "settlement", "new value exception", "priority rule"]
    },
    "united_states_v_stevens_2010": {
        "expected": ["first amendment", "speech", "crush", "animal",
                     "depiction", "overbroad", "unprotected"],
        "forbidden": ["tenth amendment", "standing", "chemical weapons",
                      "bond", "third circuit", "tenth amendment standing"]
    },
    "manson_v_brathwaite_1977": {
        "expected": ["eyewitness", "identification", "reliability",
                     "due process", "suggestive", "totality"],
        "forbidden": ["arbitration", "labor", "collective bargaining"]
    },
    "neil_v_biggers_1972": {
        "expected": ["eyewitness", "identification", "suggestive",
                     "totality", "due process", "lineup", "reliability"],
        "forbidden": ["granted certiorari to review the case on the merits",
                      "arbitration", "labor"]
    }
}

# ─── Core check function ───────────────────────────────────────────────────────

def precheck_draft(draft_path: str) -> dict:
    """
    Run identity and domain pre-check on a draft JSON file.
    Returns a dict with keys:
      status: 'pass' | 'fail' | 'stub' | 'unknown'
      reason: human-readable explanation
      details: list of specific findings
    """
    try:
        with open(draft_path) as f:
            draft = json.load(f)
    except Exception as e:
        return {"status": "unknown", "reason": f"Could not load draft: {e}", "details": []}

    cases = draft.get("nodes", {}).get("cases", [])
    if not cases:
        return {"status": "unknown", "reason": "No case nodes found in draft", "details": []}

    case = cases[0]
    case_id = case.get("id", "")
    holding = (case.get("holding", "") or "").lower()
    area_id = case.get("area_id", "")

    # Infer area from connected doctrine nodes if not on case
    if not area_id:
        for doc in draft.get("nodes", {}).get("doctrines", []):
            if doc.get("area_id"):
                area_id = doc.get("area_id")
                break

    total_nodes = sum(len(v) for v in draft.get("nodes", {}).values())
    total_edges = len(draft.get("edges", []))

    details = []
    findings = []

    # ── Layer 1: Holding content sanity ──────────────────────────────────────
    if len(holding) < 30:
        return {
            "status": "fail",
            "reason": "Holding is too short to be meaningful — likely wrong case or empty extraction",
            "details": [f"Holding length: {len(holding)} chars"]
        }

    # Check for obvious wrong-case signals regardless of area
    UNIVERSAL_FORBIDDEN = [
        ("air line pilots v. o'neill", "Labor case content in non-labor case"),
        ("steelworkers v. rawson", "Labor case content in non-labor case"),
        ("memorandum agreement to arbitrate", "Arbitration case content"),
        ("laches barred enforcement", "Labor arbitration content"),
        ("court of appeals for the armed forces", "Military law content"),
        ("all writs act", "Military jurisdiction content"),
    ]
    for term, reason in UNIVERSAL_FORBIDDEN:
        if term in holding:
            findings.append(f"WRONG CASE SIGNAL: '{term}' — {reason}")

    if findings:
        return {
            "status": "fail",
            "reason": "Holding contains universal wrong-case signals",
            "details": findings
        }

    # ── Layer 2: Case-level override check ───────────────────────────────────
    if case_id in CASE_LEVEL_OVERRIDES:
        override = CASE_LEVEL_OVERRIDES[case_id]

        # Check forbidden terms
        for term in override.get("forbidden", []):
            if term.lower() in holding:
                findings.append(f"FORBIDDEN TERM for {case_id}: '{term}'")

        if findings:
            return {
                "status": "fail",
                "reason": f"Holding contains terms that should never appear in {case_id}",
                "details": findings
            }

        # Check expected terms — at least one must appear
        expected = override.get("expected", [])
        if expected:
            found_expected = [t for t in expected if t.lower() in holding]
            if not found_expected:
                return {
                    "status": "fail",
                    "reason": f"Holding contains none of the expected terms for {case_id}",
                    "details": [f"Expected at least one of: {expected[:5]}"]
                }

    # ── Layer 3: Area-level domain check ─────────────────────────────────────
    if area_id and area_id in AREA_DOMAIN_SIGNALS:
        signals = AREA_DOMAIN_SIGNALS[area_id]

        # Check forbidden
        for term in signals.get("forbidden", []):
            if term.lower() in holding:
                findings.append(f"FORBIDDEN for area '{area_id}': '{term}'")

        if findings:
            return {
                "status": "fail",
                "reason": f"Holding contains terms incompatible with area '{area_id}'",
                "details": findings
            }

        # Check required — at least one must appear
        required = signals.get("required", [])
        if required:
            found_required = [t for t in required if t.lower() in holding]
            if not found_required:
                details.append(
                    f"WARNING: No expected domain terms found for area '{area_id}' "
                    f"(checked: {required[:4]})"
                )
                # Don't hard fail on missing required — holding may use different phrasing
                # But flag it as unknown for judge awareness

    # ── Layer 4: Stub detection ───────────────────────────────────────────────
    if total_nodes <= 1 and total_edges == 0:
        # Correct case (passed above checks) but no doctrine nodes
        return {
            "status": "stub",
            "reason": "Correct case but no doctrine nodes extracted — thin extraction",
            "details": [
                f"Nodes: {total_nodes}, Edges: {total_edges}",
                "Builder was conservative — judges should prompt for missing doctrine nodes"
            ]
        }

    # ── All checks passed ─────────────────────────────────────────────────────
    if details:
        return {
            "status": "unknown",
            "reason": "Passed hard checks but has warnings — proceed to judges",
            "details": details
        }

    return {
        "status": "pass",
        "reason": "Identity and domain checks passed",
        "details": []
    }


def run_precheck_batch(draft_paths: list) -> dict:
    """Run pre-check on a list of draft files. Returns summary."""
    results = {}
    for path in draft_paths:
        case_name = Path(path).stem
        result = precheck_draft(path)
        results[case_name] = result
        icon = {"pass": "✓", "fail": "✗", "stub": "⚠", "unknown": "?"}.get(
            result["status"], "?"
        )
        print(f"  {icon} {result['status'].upper()}: {case_name}")
        if result["status"] in ("fail", "stub"):
            print(f"    → {result['reason']}")
            for d in result["details"]:
                print(f"      {d}")

    summary = {k: sum(1 for r in results.values() if r["status"] == k)
               for k in ("pass", "fail", "stub", "unknown")}
    return {"results": results, "summary": summary}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python qa_legal_precheck.py <draft.json> [draft2.json ...]")
        sys.exit(1)
    paths = sys.argv[1:]
    print(f"\nQA: Legal Pre-Check — {len(paths)} draft(s)\n{'─'*50}")
    batch = run_precheck_batch(paths)
    print(f"\n{'─'*50}")
    s = batch["summary"]
    print(f"Summary: {s['pass']} pass | {s['fail']} fail | {s['stub']} stub | {s['unknown']} unknown")
