#!/usr/bin/env python3
"""
LexGraph — QA: Legal Agent
Adversarial LLM judge pair for legal accuracy review of draft graph nodes.

Judges:
    Judge A: Qwen3.5-397B (NVIDIA NIM) — precision, Feeney-level doctrinal depth
    Judge B: Llama 4 Maverick (NVIDIA NIM) — structure, broad coverage

Architecture:
    Both judges independently review each Case node and its edges.
    Each returns a structured verdict: pass | warn | fail + findings.

    Both pass   → high confidence, auto-approve for human review queue
    Both fail   → high confidence failure, send to needs_attention
    Disagree    → flag for mandatory human review, show both verdicts

Usage:
    python qa_legal.py --draft draft_sdp_graph.json
    python qa_legal.py --draft draft_sdp_graph.json --combined conlaw_graph_v02.json
    python qa_legal.py --draft draft_sdp_graph.json --case miranda_v_arizona_1966

Output:
    qa_legal_report.json  — structured findings
    Prints human-readable summary to stdout

Requires: NVIDIA_API_KEY in environment or .env file
"""

import os
import re
import json
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# ─── Configuration ─────────────────────────────────────────────────────────────

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
REQUEST_DELAY = 2.0  # seconds between judge calls

JUDGE_A = {
    "name": "Qwen3.5-397B",
    "model": "qwen/qwen3.5-397b-a17b",
    "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
}

JUDGE_B = {
    "name": "Llama-4-Maverick",
    "model": "meta/llama-4-maverick-17b-128e-instruct",
    "extra_body": {},
}

JUDGE_SYSTEM_PROMPT = """You are an expert constitutional law attorney conducting a legal accuracy review of a legal knowledge graph node.

Your task is to review a Case node and its associated edges for legal accuracy.

Review criteria:
1. HOLDING ACCURACY — Does the holding accurately state the legal rule announced by the Court? Is it complete? Does it avoid stating mere procedural outcomes?
2. HOLDING TYPE — Is holding_type (affirmative/by_negation) correct?
3. EDGE ACCURACY — Are the edge types legally correct? (ESTABLISHES vs APPLIES vs MODIFIES, OVERRULES only when explicit)
4. MODIFIES DIRECTION — If MODIFIES edges exist, is the direction (narrows/expands/clarifies/complicates) accurate?
5. DOCTRINE ACCURACY — Are doctrine node descriptions legally accurate? Do they correctly characterize the legal standard?
6. TEST ACCURACY — If a DoctrinalTest is present, are the prongs correctly stated? Is the scrutiny level correct?
7. MISSING CONNECTIONS — Are there important doctrinal connections missing? (e.g., case should APPLY an existing test but doesn't)

Cite precise Supreme Court precedents. Apply doctrinal standards exactly as courts do.
Distinguish between what a case held vs. what it assumed or dicta.
Note if a holding overstates or understates the actual rule.

You MUST respond with ONLY valid JSON in exactly this format:
{
  "verdict": "pass" | "warn" | "fail",
  "confidence": 0.0-1.0,
  "findings": [
    {
      "severity": "high" | "medium" | "low",
      "field": "holding | edge | doctrine | test | missing",
      "issue": "description of the legal inaccuracy",
      "suggestion": "what the correct statement should be"
    }
  ],
  "overall_assessment": "one sentence summary of legal accuracy"
}

verdict rules:
- pass: no high findings, at most 2 medium findings
- warn: 1-2 high findings OR 3+ medium findings
- fail: 3+ high findings or a fundamentally wrong holding

If the node is legally accurate, return an empty findings array and verdict: pass."""

# ─── Utilities ─────────────────────────────────────────────────────────────────

def load_graph(filepath):
    with open(filepath) as f:
        return json.load(f)

def get_client():
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("NVIDIA_API_KEY not found in environment")
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

def build_review_context(case_node, draft_data, combined_data=None):
    """Build the context string for judge review."""
    lines = []
    lines.append("## Case Node Under Review")
    lines.append(f"ID: {case_node.get('id')}")
    lines.append(f"Short name: {case_node.get('short_name')}")
    lines.append(f"Citation: {case_node.get('citation')}")
    lines.append(f"Decided: {case_node.get('decided_date')}")
    lines.append(f"Holding: {case_node.get('holding')}")
    lines.append(f"Holding type: {case_node.get('holding_type')}")
    lines.append(f"Opinion form: {case_node.get('opinion_form')}")
    lines.append(f"Vote: {case_node.get('vote')}")
    lines.append(f"Majority author: {case_node.get('majority_author')}")
    if case_node.get('notes'):
        lines.append(f"Notes: {case_node.get('notes')}")

    # Edges from this case
    case_id = case_node.get('id')
    edges = [e for e in draft_data.get('edges', [])
             if e.get('source_id') == case_id]

    if edges:
        lines.append("\n## Edges from this case")
        for e in edges:
            edge_str = f"- [{e.get('edge_type')}] → {e.get('target_id')}"
            if e.get('direction'):
                edge_str += f" (direction: {e.get('direction')})"
            if e.get('overrule_type'):
                edge_str += f" (overrule_type: {e.get('overrule_type')})"
            if e.get('notes'):
                edge_str += f"\n  Notes: {e.get('notes')}"
            lines.append(edge_str)

    # Connected doctrine/test nodes
    target_ids = {e.get('target_id') for e in edges}
    doctrines = [d for d in draft_data.get('nodes', {}).get('doctrines', [])
                 if d.get('id') in target_ids]
    tests = [t for t in draft_data.get('nodes', {}).get('doctrinal_tests', [])
             if t.get('id') in target_ids]

    if doctrines:
        lines.append("\n## Connected Doctrine Nodes")
        for d in doctrines:
            lines.append(f"- {d.get('id')}: {d.get('label')}")
            lines.append(f"  Description: {d.get('description')}")

    if tests:
        lines.append("\n## Connected DoctrinalTest Nodes")
        for t in tests:
            lines.append(f"- {t.get('id')}: {t.get('label')}")
            lines.append(f"  Scrutiny: {t.get('scrutiny_level')} | Burden: {t.get('burden')}")
            lines.append(f"  Description: {t.get('description')}")
            for p in t.get('prongs', []):
                lines.append(f"  Prong {p.get('number')}: {p.get('label')} — {p.get('description')}")

    return '\n'.join(lines)

def call_judge(client, judge, context, case_id):
    """Call a single judge and return parsed verdict."""
    prompt = f"""Please review the following legal knowledge graph node for legal accuracy:

{context}

Respond with ONLY valid JSON as specified in your instructions."""

    try:
        kwargs = {
            "model": judge["model"],
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1500,
            "temperature": 0.1,
        }
        if judge.get("extra_body"):
            kwargs["extra_body"] = judge["extra_body"]

        response = client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()

        parsed = json.loads(raw)
        parsed['judge'] = judge['name']
        parsed['case_id'] = case_id
        return parsed

    except json.JSONDecodeError as e:
        return {
            "judge": judge['name'],
            "case_id": case_id,
            "verdict": "error",
            "confidence": 0.0,
            "findings": [],
            "overall_assessment": f"JSON parse error: {e}",
            "raw_response": raw if 'raw' in dir() else "no response"
        }
    except Exception as e:
        return {
            "judge": judge['name'],
            "case_id": case_id,
            "verdict": "error",
            "confidence": 0.0,
            "findings": [],
            "overall_assessment": f"API error: {e}"
        }

def reconcile_verdicts(verdict_a, verdict_b):
    """Determine overall outcome from two judge verdicts."""
    va = verdict_a.get('verdict', 'error')
    vb = verdict_b.get('verdict', 'error')

    if va == 'error' or vb == 'error':
        return 'error', 'One or both judges returned an error'

    if va == vb:
        if va == 'pass':
            return 'pass', 'Both judges pass — high confidence'
        elif va == 'fail':
            return 'fail', 'Both judges fail — high confidence'
        else:
            return 'warn', 'Both judges warn — review recommended'

    # Disagreement
    return 'review', f'Judges disagree: {verdict_a["judge"]}={va}, {verdict_b["judge"]}={vb} — mandatory human review'

# ─── Main Review Function ──────────────────────────────────────────────────────

def review_case(client, case_node, draft_data, combined_data=None):
    """Run both judges on a single case node."""
    case_id = case_node.get('id')
    print(f"  Reviewing: {case_node.get('short_name', case_id)}")

    context = build_review_context(case_node, draft_data, combined_data)

    # Judge A
    print(f"    Judge A ({JUDGE_A['name']})...")
    verdict_a = call_judge(client, JUDGE_A, context, case_id)
    time.sleep(REQUEST_DELAY)

    # Judge B
    print(f"    Judge B ({JUDGE_B['name']})...")
    verdict_b = call_judge(client, JUDGE_B, context, case_id)
    time.sleep(REQUEST_DELAY)

    # Reconcile
    outcome, outcome_note = reconcile_verdicts(verdict_a, verdict_b)

    # Collect all findings
    all_findings = []
    for finding in verdict_a.get('findings', []):
        finding['judge'] = verdict_a['judge']
        all_findings.append(finding)
    for finding in verdict_b.get('findings', []):
        finding['judge'] = verdict_b['judge']
        all_findings.append(finding)

    high = len([f for f in all_findings if f.get('severity') == 'high'])
    medium = len([f for f in all_findings if f.get('severity') == 'medium'])
    low = len([f for f in all_findings if f.get('severity') == 'low'])

    result = {
        "case_id": case_id,
        "short_name": case_node.get('short_name'),
        "outcome": outcome,
        "outcome_note": outcome_note,
        "verdict_a": verdict_a,
        "verdict_b": verdict_b,
        "all_findings": all_findings,
        "finding_counts": {"high": high, "medium": medium, "low": low}
    }

    # Print summary
    icon = {"pass": "✓", "warn": "⚠", "fail": "✗", "review": "⟳", "error": "!"}.get(outcome, "?")
    print(f"    {icon} {outcome.upper()} — {high}H/{medium}M/{low}L findings — {outcome_note}")

    return result

def run_qa_legal(draft_path, combined_path=None, case_filter=None):
    """Run legal QA on all primary cases in a draft."""
    load_dotenv(override=True)

    print(f"\nQA: Legal Agent")
    print("─" * 60)
    print(f"Draft:    {draft_path}")
    if combined_path:
        print(f"Combined: {combined_path}")
    print(f"Judge A:  {JUDGE_A['name']} ({JUDGE_A['model']})")
    print(f"Judge B:  {JUDGE_B['name']} ({JUDGE_B['model']})")
    print()

    draft_data = load_graph(draft_path)
    combined_data = load_graph(combined_path) if combined_path else None

    client = get_client()

    # Get primary cases (not stubs)
    cases = [c for c in draft_data.get('nodes', {}).get('cases', [])
             if c.get('status') != 'overruled'
             and c.get('data_tier') != 'inferred']

    if case_filter:
        cases = [c for c in cases if c.get('id') == case_filter]

    print(f"Cases to review: {len(cases)}")
    print()

    results = []
    for case_node in cases:
        result = review_case(client, case_node, draft_data, combined_data)
        results.append(result)
        print()

    # Summary
    passed = [r for r in results if r['outcome'] == 'pass']
    warned = [r for r in results if r['outcome'] == 'warn']
    failed = [r for r in results if r['outcome'] == 'fail']
    review = [r for r in results if r['outcome'] == 'review']
    errors = [r for r in results if r['outcome'] == 'error']

    print("─" * 60)
    print(f"Results: {len(passed)} pass | {len(warned)} warn | {len(failed)} fail | {len(review)} review | {len(errors)} error")

    if failed:
        print(f"\nFAILED — fix before merge:")
        for r in failed:
            print(f"  ✗ {r['short_name']}")
            for f in r['all_findings']:
                if f.get('severity') == 'high':
                    print(f"    [{f['judge']}] {f['issue']}")

    if review:
        print(f"\nMANDATORY HUMAN REVIEW — judges disagree:")
        for r in review:
            print(f"  ⟳ {r['short_name']}")
            print(f"    {JUDGE_A['name']}: {r['verdict_a'].get('verdict')} — {r['verdict_a'].get('overall_assessment')}")
            print(f"    {JUDGE_B['name']}: {r['verdict_b'].get('verdict')} — {r['verdict_b'].get('overall_assessment')}")

    if warned:
        print(f"\nWARNINGS — review recommended:")
        for r in warned:
            print(f"  ⚠ {r['short_name']} — {r['finding_counts']['medium']}M/{r['finding_counts']['low']}L findings")

    # Save report
    report_path = Path(draft_path).parent / "qa_legal_report.json"
    with open(report_path, 'w') as f:
        json.dump({
            "draft": str(draft_path),
            "summary": {
                "total": len(results),
                "pass": len(passed),
                "warn": len(warned),
                "fail": len(failed),
                "review": len(review),
                "error": len(errors)
            },
            "results": results
        }, f, indent=2)
    print(f"\nReport saved to: {report_path}")

    return results

# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QA: Legal Agent — adversarial LLM judge pair")
    parser.add_argument("--draft", required=True, help="Path to draft JSON file")
    parser.add_argument("--combined", help="Path to combined master graph (for context)")
    parser.add_argument("--case", help="Review a specific case ID only")
    args = parser.parse_args()

    run_qa_legal(args.draft, args.combined, args.case)
