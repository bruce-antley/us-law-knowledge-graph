#!/usr/bin/env python3
"""
LexGraph — Overnight Batch Pipeline Runner
Runs the full pipeline on a list of cases and produces a human-readable
review report.

Usage:
    python run_pipeline.py --cases cases.txt
    python run_pipeline.py --cases sdp_batch.txt --model claude-haiku-4-5-20251001

Input file format (cases.txt):
    One case per line: "Case Name, Year, Citation"
    Lines starting with # are comments, blank lines are ignored.
    Examples:
        Meyer v. Nebraska, 1923, 262 U.S. 390
        Pierce v. Society of Sisters, 1925, 268 U.S. 510
        Moore v. City of East Cleveland, 1977, 431 U.S. 494

Output:
    syllabi/              — retrieved syllabus text files (Elsa)
    drafts/               — draft JSON files from Graph Builder
    review_queue/         — drafts that passed both QA layers (ready for review)
    needs_attention/      — drafts that failed QA or had high-severity findings
    pipeline_report.md    — human-readable run report

Requires: ANTHROPIC_API_KEY and COURTLISTENER_API_KEY in .env
"""

import os
import re
import json
import time
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic

# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 16000
TEMPERATURE = 0.0
REQUEST_DELAY = 2.0  # seconds between Graph Builder calls

PIPELINE_DIR = Path(__file__).parent
SYLLABUS_DIR = PIPELINE_DIR / "syllabi"
DRAFTS_DIR = PIPELINE_DIR / "drafts"
REVIEW_QUEUE_DIR = PIPELINE_DIR / "review_queue"
NEEDS_ATTENTION_DIR = PIPELINE_DIR / "needs_attention"
MASTER_GRAPH = Path("/Users/bruceantley/Downloads/us-law-knowledge-graph/data/conlaw_graph_v02.json")

VALID_AREAS = [
    "constitutional_law", "individual_rights", "substantive_due_process",
    "first_amendment", "free_speech", "commercial_speech", "core_political_speech",
    "prior_restraint", "freedom_of_the_press", "free_exercise_of_religion",
    "establishment_clause", "freedom_of_association", "freedom_of_petition",
    "equal_protection"
]

# ─── Utilities ────────────────────────────────────────────────────────────────

def load_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def strip_markdown_fences(raw):
    fence = '`' * 3
    cleaned = re.sub(r'^' + fence + r'(?:json)?\s*', '', raw, flags=re.MULTILINE)
    cleaned = re.sub(r'\s*' + fence + r'$', '', cleaned, flags=re.MULTILINE)
    return cleaned.strip()

def parse_cases_file(filepath):
    """Parse cases input file. Format: Name, Year, Citation"""
    cases = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split(',')]
            name = parts[0]
            year = parts[1] if len(parts) > 1 else None
            citation = ', '.join(parts[2:]) if len(parts) > 2 else None
            cases.append((name, year, citation))
    return cases

def slugify(name):
    name = name.lower()
    name = re.sub(r"['\"]", "", name)
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")

def case_id_from_name(name, year):
    parts = re.split(r"\s+v\.?\s+", name, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        p1 = slugify(parts[0].split(",")[0].strip())
        p2 = slugify(parts[1].split(",")[0].strip())
        return f"{p1}_v_{p2}_{year}"
    return f"{slugify(name)}_{year}"

def count_nodes_edges(draft_path):
    """Count nodes and edges in a draft JSON file."""
    try:
        with open(draft_path) as f:
            data = json.load(f)
        nodes = sum(len(v) for v in data.get('nodes', {}).values())
        edges = len(data.get('edges', []))
        return nodes, edges
    except Exception:
        return 0, 0

def has_plurality(draft_path):
    """Check if draft contains a plurality opinion."""
    try:
        with open(draft_path) as f:
            data = json.load(f)
        for case in data.get('nodes', {}).get('cases', []):
            if case.get('opinion_form') == 'plurality':
                return True
        return False
    except Exception:
        return False

# ─── Pipeline Steps ───────────────────────────────────────────────────────────

def step_elsa(case_name, year, citation, result):
    """Step 1: Retrieve syllabus via Elsa."""
    try:
        import sys
        sys.path.insert(0, str(PIPELINE_DIR))
        from elsa import retrieve_case

        case_id, syllabus_path = retrieve_case(
            case_name, year, citation,
            output_dir=SYLLABUS_DIR
        )

        if syllabus_path:
            result['case_id'] = case_id
            result['syllabus_path'] = str(syllabus_path)
            result['elsa_status'] = 'ok'
            return True
        else:
            result['elsa_status'] = 'failed'
            result['elsa_error'] = 'Could not retrieve from LII or CourtListener'
            return False
    except Exception as e:
        result['elsa_status'] = 'error'
        result['elsa_error'] = str(e)
        return False

def step_graph_builder(result, client, prompt_text):
    """Step 2: Run Graph Builder."""
    try:
        syllabus_text = load_file(result['syllabus_path'])
        dynamic_prompt = prompt_text + f"\n\n[CRITICAL: For area_id, choose from: {VALID_AREAS}]"

        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=dynamic_prompt,
            extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
            messages=[{
                "role": "user",
                "content": f"Extract the knowledge graph from the following text:\n\n{syllabus_text}"
            }]
        )

        raw_output = response.content[0].text

        # Save backup
        backup_path = DRAFTS_DIR / f"{result['case_id']}_raw.txt"
        backup_path.write_text(raw_output)

        # Parse JSON
        clean = strip_markdown_fences(raw_output)
        parsed = json.loads(clean)

        draft_path = DRAFTS_DIR / f"{result['case_id']}_draft.json"
        with open(draft_path, 'w') as f:
            json.dump(parsed, f, indent=2)

        result['draft_path'] = str(draft_path)
        result['graph_builder_status'] = 'ok'
        return True

    except json.JSONDecodeError as e:
        result['graph_builder_status'] = 'json_error'
        result['graph_builder_error'] = str(e)
        return False
    except Exception as e:
        result['graph_builder_status'] = 'error'
        result['graph_builder_error'] = str(e)
        return False

def step_validate(result):
    """Step 3: Run validate.py."""
    try:
        proc = subprocess.run(
            ["python", "validate.py",
             "--file", result['draft_path'],
             "--combined", str(MASTER_GRAPH),
             "--draft"],
            capture_output=True, text=True,
            cwd=str(PIPELINE_DIR)
        )

        output = proc.stdout
        result['validate_output'] = output
        result['validate_returncode'] = proc.returncode

        # Parse error count
        error_match = re.search(r'(\d+) errors', output)
        warning_match = re.search(r'(\d+) warnings', output)
        result['validate_errors'] = int(error_match.group(1)) if error_match else 0
        result['validate_warnings'] = int(warning_match.group(1)) if warning_match else 0

        if proc.returncode == 0:
            result['validate_status'] = 'pass'
            return True
        else:
            result['validate_status'] = 'fail'
            return False

    except Exception as e:
        result['validate_status'] = 'error'
        result['validate_error'] = str(e)
        return False

def step_qa_factual(result):
    """Step 4: Run qa_factual.py."""
    try:
        qa_report_path = DRAFTS_DIR / f"{result['case_id']}_qa_report.json"
        patched_path = str(result['draft_path']).replace('_draft.json', '_patched.json')

        proc = subprocess.run(
            ["python", "qa_factual.py",
             "--draft", result['draft_path'],
             "--output", str(qa_report_path),
             "--patch"],
            capture_output=True, text=True,
            cwd=str(PIPELINE_DIR)
        )

        result['qa_factual_output'] = proc.stdout
        result['qa_factual_returncode'] = proc.returncode

        # Parse findings from report
        if qa_report_path.exists():
            with open(qa_report_path) as f:
                qa_data = json.load(f)
            findings = qa_data.get('findings', [])
            result['qa_high'] = len([f for f in findings if f.get('severity') == 'high'])
            result['qa_medium'] = len([f for f in findings if f.get('severity') == 'medium'])
            result['qa_low'] = len([f for f in findings if f.get('severity') == 'low'])
            result['qa_not_found'] = len(qa_data.get('cases_not_found', []))
            result['qa_report_path'] = str(qa_report_path)

            # Use patched draft if it exists
            patched = Path(str(result['draft_path']).replace('_draft.json', '_draft_patched.json'))
            if patched.exists():
                result['draft_path'] = str(patched)

        result['qa_factual_status'] = 'pass' if result.get('qa_high', 0) == 0 else 'fail'
        return result['qa_factual_status'] == 'pass'

    except Exception as e:
        result['qa_factual_status'] = 'error'
        result['qa_factual_error'] = str(e)
        return False

def step_qa_structural(result):
    """Step 5: Run qa_structural.py."""
    try:
        proc = subprocess.run(
            ["python", "qa_structural.py",
             "--draft", result['draft_path'],
             "--combined", str(MASTER_GRAPH)],
            capture_output=True, text=True,
            cwd=str(PIPELINE_DIR)
        )
        result['qa_structural_output'] = proc.stdout
        result['qa_structural_returncode'] = proc.returncode

        import re as _re
        error_match = _re.search(r'(\d+) errors', proc.stdout)
        warning_match = _re.search(r'(\d+) warnings', proc.stdout)
        result['struct_errors'] = int(error_match.group(1)) if error_match else 0
        result['struct_warnings'] = int(warning_match.group(1)) if warning_match else 0
        result['qa_structural_status'] = 'pass' if proc.returncode == 0 else 'fail'
        return proc.returncode == 0
    except Exception as e:
        result['qa_structural_status'] = 'error'
        result['qa_structural_error'] = str(e)
        return False

# ─── Report Generation ────────────────────────────────────────────────────────

def generate_report(run_results, cases, run_start, run_end):
    """Generate a human-readable markdown review report."""
    duration = run_end - run_start
    minutes = int(duration.total_seconds() / 60)
    seconds = int(duration.total_seconds() % 60)

    passed = [r for r in run_results if r.get('overall_status') == 'passed']
    failed = [r for r in run_results if r.get('overall_status') == 'failed']
    skipped = [r for r in run_results if r.get('overall_status') == 'skipped']

    lines = []
    lines.append(f"# LexGraph Pipeline Run Report")
    lines.append(f"**Date:** {run_start.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Duration:** {minutes}m {seconds}s")
    lines.append(f"**Cases processed:** {len(cases)}")
    lines.append(f"**Passed QA:** {len(passed)} | **Failed:** {len(failed)} | **Skipped:** {len(skipped)}")
    lines.append("")

    # Passed section
    lines.append("---")
    lines.append("## ✓ PASSED — Ready for Doctrinal Review")
    lines.append("")
    if passed:
        for r in passed:
            nodes, edges = count_nodes_edges(r.get('draft_path', ''))
            plurality = " **[PLURALITY — verify holding]**" if has_plurality(r.get('draft_path', '')) else ""
            lines.append(f"### {r['case_name']} ({r['year']})")
            lines.append(f"- **Case ID:** `{r.get('case_id', 'unknown')}`")
            lines.append(f"- **Draft:** `{Path(r.get('draft_path', '')).name}`")
            lines.append(f"- **Nodes:** {nodes} | **Edges:** {edges}{plurality}")
            if r.get('qa_medium', 0) > 0:
                lines.append(f"- **QA flags:** {r['qa_medium']} medium (see qa_report)")
            if r.get('qa_not_found', 0) > 0:
                lines.append(f"- **CourtListener:** {r['qa_not_found']} case(s) not found — courtlistener_id will be null")
            if r.get('validate_warnings', 0) > 0:
                lines.append(f"- **Validator warnings:** {r['validate_warnings']}")
            if r.get('struct_errors', 0) > 0:
                lines.append(f"- **QA Structural:** {r['struct_errors']} errors, {r['struct_warnings']} warnings — check before merging")
            elif r.get('struct_warnings', 0) > 0:
                lines.append(f"- **QA Structural:** {r['struct_warnings']} warnings")
            lines.append("")
    else:
        lines.append("_No cases passed QA._")
        lines.append("")

    # Failed section
    lines.append("---")
    lines.append("## ✗ NEEDS ATTENTION")
    lines.append("")
    if failed:
        for r in failed:
            lines.append(f"### {r['case_name']} ({r['year']})")

            if r.get('elsa_status') in ('failed', 'error'):
                lines.append(f"- **Elsa failed:** {r.get('elsa_error', 'unknown error')}")

            if r.get('graph_builder_status') in ('json_error', 'error'):
                lines.append(f"- **Graph Builder failed:** {r.get('graph_builder_error', 'unknown error')}")

            if r.get('validate_status') == 'fail':
                lines.append(f"- **Validator:** {r.get('validate_errors', 0)} errors, {r.get('validate_warnings', 0)} warnings")
                # Extract error lines from validator output
                validate_out = r.get('validate_output', '')
                error_lines = [l.strip() for l in validate_out.split('\n') if '✗' in l]
                for el in error_lines[:5]:  # Show first 5 errors
                    lines.append(f"  - {el}")
                if len(error_lines) > 5:
                    lines.append(f"  - ... and {len(error_lines)-5} more")

            if r.get('qa_high', 0) > 0:
                lines.append(f"- **QA Factual:** {r['qa_high']} HIGH severity findings")

            lines.append("")
    else:
        lines.append("_No failures._")
        lines.append("")

    # Skipped section
    if skipped:
        lines.append("---")
        lines.append("## ↷ SKIPPED")
        lines.append("")
        for r in skipped:
            lines.append(f"- **{r['case_name']}** — {r.get('skip_reason', 'already retrieved')}")
        lines.append("")

    # Next steps
    lines.append("---")
    lines.append("## Next Steps")
    lines.append("")
    lines.append("For each case in PASSED:")
    lines.append("1. Open the draft JSON in `review_queue/`")
    lines.append("2. Review holding accuracy, edge types, and doctrine nodes")
    lines.append("3. If approved: merge into `conlaw_graph_v02.json`, reload Neo4j, push to GitHub")
    lines.append("")
    lines.append("For each case in NEEDS ATTENTION:")
    lines.append("1. Check the error details above")
    lines.append("2. Fix the input (syllabus text, prompt, or manual draft edit)")
    lines.append("3. Re-run manually via notebook")
    lines.append("")

    return '\n'.join(lines)

# ─── Main ─────────────────────────────────────────────────────────────────────

def run_pipeline(cases_file, model=DEFAULT_MODEL):
    """Run the full pipeline on a list of cases."""

    load_dotenv(override=True)

    # Setup
    for d in [SYLLABUS_DIR, DRAFTS_DIR, REVIEW_QUEUE_DIR, NEEDS_ATTENTION_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt_text = load_file(PIPELINE_DIR / "graph_builder_prompt_v1_4.txt")
    cases = parse_cases_file(cases_file)

    run_start = datetime.now()
    print(f"\nLexGraph Pipeline Runner")
    print(f"{'─' * 60}")
    print(f"Cases: {len(cases)}")
    print(f"Model: {model}")
    print(f"Started: {run_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    run_results = []

    for i, (case_name, year, citation) in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case_name} ({year})")
        print(f"{'─' * 40}")

        result = {
            'case_name': case_name,
            'year': year,
            'citation': citation,
        }

        # Step 1: Elsa
        print("  Step 1: Elsa — retrieving syllabus...")
        elsa_ok = step_elsa(case_name, year, citation, result)
        if not elsa_ok:
            result['overall_status'] = 'failed'
            print(f"  ✗ Elsa failed: {result.get('elsa_error')}")
            run_results.append(result)
            continue

        # Check if draft already exists (skip Graph Builder if so)
        draft_path = DRAFTS_DIR / f"{result['case_id']}_draft.json"
        if draft_path.exists():
            print(f"  ↷ Draft already exists, skipping Graph Builder")
            result['draft_path'] = str(draft_path)
            result['graph_builder_status'] = 'skipped'
            result['overall_status'] = 'skipped'
            result['skip_reason'] = 'draft already exists'
        else:
            # Step 2: Graph Builder
            print("  Step 2: Graph Builder — extracting graph...")
            gb_ok = step_graph_builder(result, client, prompt_text)
            if not gb_ok:
                result['overall_status'] = 'failed'
                print(f"  ✗ Graph Builder failed: {result.get('graph_builder_error')}")
                run_results.append(result)
                time.sleep(REQUEST_DELAY)
                continue

        # Step 3: Validate
        print("  Step 3: Validate — checking schema...")
        validate_ok = step_validate(result)
        if not validate_ok:
            result['overall_status'] = 'failed'
            print(f"  ✗ Validation failed: {result['validate_errors']} errors")
            # Copy to needs_attention
            import shutil
            shutil.copy(result['draft_path'],
                       NEEDS_ATTENTION_DIR / Path(result['draft_path']).name)
            run_results.append(result)
            time.sleep(REQUEST_DELAY)
            continue

        # Step 4: QA Factual
        print("  Step 4: QA Factual — checking CourtListener...")
        qa_ok = step_qa_factual(result)

        # Step 5: QA Structural
        print("  Step 5: QA Structural — checking graph consistency...")
        step_qa_structural(result)
        if result.get('struct_errors', 0) > 0:
            print(f"  ⚠ Structural: {result['struct_errors']} errors, {result['struct_warnings']} warnings")
        else:
            print(f"  ✓ Structural: 0 errors, {result.get('struct_warnings', 0)} warnings")

        if qa_ok:
            result['overall_status'] = 'passed'
            print(f"  ✓ Passed — {result.get('qa_high',0)} high / {result.get('qa_medium',0)} medium / {result.get('qa_low',0)} low findings")
            # Copy to review_queue
            import shutil
            shutil.copy(result['draft_path'],
                       REVIEW_QUEUE_DIR / Path(result['draft_path']).name)
        else:
            result['overall_status'] = 'failed'
            print(f"  ✗ QA Factual: {result.get('qa_high',0)} HIGH severity findings")
            import shutil
            shutil.copy(result['draft_path'],
                       NEEDS_ATTENTION_DIR / Path(result['draft_path']).name)

        run_results.append(result)
        print()
        time.sleep(REQUEST_DELAY)

    # Generate report
    run_end = datetime.now()
    report = generate_report(run_results, cases, run_start, run_end)
    report_path = PIPELINE_DIR / "pipeline_report.md"
    report_path.write_text(report)

    print(f"\n{'═' * 60}")
    print(f"Run complete: {datetime.now().strftime('%H:%M:%S')}")
    print(f"Passed: {len([r for r in run_results if r.get('overall_status') == 'passed'])}/{len(cases)}")
    print(f"Report: {report_path}")
    print()
    print(report)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LexGraph Overnight Batch Pipeline")
    parser.add_argument("--cases", required=True, help="Path to cases list file")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model to use for Graph Builder")
    args = parser.parse_args()
    run_pipeline(args.cases, args.model)
