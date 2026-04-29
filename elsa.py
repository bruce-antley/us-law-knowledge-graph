#!/usr/bin/env python3
"""
Elsa — Case Retrieval Agent
Named after Bruce's sister's beloved elderly Golden Retriever.

Takes a list of case names/citations and retrieves clean syllabus text
ready for the Graph Builder. Uses LII as primary source, CourtListener
as fallback for older cases.

Usage:
    python elsa.py --cases cases.txt --output syllabi/
    python elsa.py --case "Griswold v. Connecticut" --year 1965 --output syllabi/

Input file format (cases.txt):
    One case per line: "Case Name, Year" or "Case Name v. Other Party, Year"
    Examples:
        Washington v. Glucksberg, 1997
        Griswold v. Connecticut, 1965
        Planned Parenthood v. Casey, 1992

Output:
    One .txt file per case: {case_id}_syllabus.txt
    Ready to feed directly to Graph Builder (cell 3)

Requires: COURTLISTENER_API_KEY in environment
"""

import os
import re
import sys
import time
import argparse
import requests
from pathlib import Path
from urllib.parse import quote_plus

# ─── Configuration ────────────────────────────────────────────────────────────

LII_BASE = "https://www.law.cornell.edu/supremecourt/text"
CL_BASE = "https://www.courtlistener.com/api/rest/v4"

# Cases decided before this year likely don't have LII structured syllabi
LII_SYLLABUS_CUTOFF = 1990

# ─── Utilities ────────────────────────────────────────────────────────────────

def slugify(name):
    """Convert case name to snake_case ID."""
    name = name.lower()
    name = re.sub(r"['\"]", "", name)
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")

def case_id_from_name(name, year):
    """Generate a case ID from name and year."""
    # Handle "Party1 v. Party2" format
    parts = re.split(r"\s+v\.?\s+", name, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        p1 = slugify(parts[0].split(",")[0].strip())
        p2 = slugify(parts[1].split(",")[0].strip())
        return f"{p1}_v_{p2}_{year}"
    return f"{slugify(name)}_{year}"

def clean_text(text):
    """
    Clean retrieved text for Graph Builder input.
    Removes page numbers, headers, hyphenation artifacts,
    and other noise from copied/scraped text.
    """
    # Remove page number patterns like "381 U.S. 480" mid-text
    text = re.sub(r"\n\s*\d+\s+U\.S\.\s+\d+\s*\n", "\n", text)
    # Remove standalone page numbers
    text = re.sub(r"\n\s*Page\s+\d+\s*\n", "\n", text, flags=re.IGNORECASE)
    # Remove soft hyphens and hyphenation artifacts
    text = re.sub(r"-\s*\n\s*", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove leading/trailing whitespace per line
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()

def extract_syllabus_section(text):
    """
    Extract just the syllabus section from a full opinion text.
    The syllabus appears between 'SYLLABUS' and the first opinion section
    (typically 'OPINION', 'MR. JUSTICE', 'JUSTICE X delivered', or 'I.')
    """
    # Normalize
    text_upper = text.upper()

    # Find syllabus start
    syllabus_start = None
    for marker in ["SYLLABUS\n", "SYLLABUS\r\n", "\nSYLLABUS"]:
        idx = text_upper.find(marker.upper())
        if idx != -1:
            syllabus_start = idx + len(marker)
            break

    if syllabus_start is None:
        # No syllabus marker — return the whole text
        return text

    # Find syllabus end (start of opinion)
    opinion_markers = [
        "MR. JUSTICE",
        "MR. CHIEF JUSTICE",
        "JUSTICE ",
        "PER CURIAM",
        "\nI.\n",
        "\n   I\n",
        "OPINION OF THE COURT",
        "delivered the opinion",
        "CHIEF JUSTICE ",
    ]

    syllabus_end = len(text)
    for marker in opinion_markers:
        idx = text_upper.find(marker.upper(), syllabus_start + 100)
        if idx != -1 and idx < syllabus_end:
            syllabus_end = idx

    syllabus = text[syllabus_start:syllabus_end]
    return clean_text(syllabus)

# ─── Source: LII ──────────────────────────────────────────────────────────────

def fetch_from_lii(citation_volume, citation_page, session):
    """
    Fetch syllabus from LII using volume/page citation.
    URL format: https://www.law.cornell.edu/supremecourt/text/{volume}/{page}
    
    LII HTML structure:
    - The syllabus is marked with class="writingtype_syllabus" or id="writing-ZS"
    - The opinion text follows in separate writing sections
    - We need to strip all JS, nav, and ad content before extracting text
    """
    url = f"{LII_BASE}/{citation_volume}/{citation_page}"
    print(f"    Trying LII: {url}")

    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Strategy 1: Find the syllabus section by LII's class markers
        # LII wraps the syllabus in <div class="writingtype_syllabus"> or similar
        import re as _re
        
        syllabus_patterns = [
            r'class="[^"]*syllabus[^"]*"[^>]*>(.*?)</div>',
            r'id="writing-ZS"[^>]*>(.*?)</(?:div|section)>',
            r'<section[^>]*syllabus[^>]*>(.*?)</section>',
        ]
        
        for pattern in syllabus_patterns:
            match = _re.search(pattern, html, _re.DOTALL | _re.IGNORECASE)
            if match:
                raw = match.group(1)
                # Strip inner HTML tags
                text = _re.sub(r'<[^>]+>', ' ', raw)
                text = _re.sub(r'&amp;', '&', text)
                text = _re.sub(r'&lt;', '<', text)
                text = _re.sub(r'&gt;', '>', text)
                text = _re.sub(r'&[a-z]+;', ' ', text)
                text = _re.sub(r'\s+', ' ', text)
                text = clean_text(text)
                if len(text) > 300:
                    return text, "lii_syllabus"

        # Strategy 2: Find the "Syllabus" marker in the HTML and extract text after it
        # Remove all <script> and <style> blocks first
        html_clean = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.DOTALL)
        html_clean = _re.sub(r'<style[^>]*>.*?</style>', '', html_clean, flags=_re.DOTALL)
        html_clean = _re.sub(r'<nav[^>]*>.*?</nav>', '', html_clean, flags=_re.DOTALL)
        html_clean = _re.sub(r'<header[^>]*>.*?</header>', '', html_clean, flags=_re.DOTALL)
        html_clean = _re.sub(r'<footer[^>]*>.*?</footer>', '', html_clean, flags=_re.DOTALL)
        
        # Now strip remaining tags and extract text
        plain = _re.sub(r'<[^>]+>', ' ', html_clean)
        plain = _re.sub(r'&[a-z]+;', ' ', plain)
        plain = _re.sub(r'\s+', ' ', plain)
        
        # Find "Syllabus" marker and extract from there
        syllabus_idx = plain.upper().find('SYLLABUS')
        if syllabus_idx > 0:
            # Take text from syllabus marker forward
            candidate = plain[syllabus_idx:]
            # Cut off at the opinion (find "delivered the opinion" or "C.J., delivered")
            opinion_markers = [
                "delivered the opinion",
                "C. J., delivered",
                "J., delivered",
                "Chief Justice",
                "MR. JUSTICE",
                "MR. CHIEF JUSTICE",
            ]
            cut = len(candidate)
            for marker in opinion_markers:
                idx = candidate.upper().find(marker.upper(), 200)
                if 200 < idx < cut:
                    cut = idx
            
            syllabus = clean_text(candidate[:cut])
            # Detect LII's intentionally omitted placeholder for pre-1990 cases
            if 'intentionally omitted' in syllabus.lower() or len(syllabus) < 200:
                print(f"    LII: syllabus intentionally omitted or too short — falling back to CourtListener")
                return None, None
            if len(syllabus) > 300:
                return syllabus, "lii_extracted"

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"    LII 404 — case not available")
        else:
            print(f"    LII error: {e}")
    except Exception as e:
        print(f"    LII fetch failed: {e}")

    return None, None

# ─── Source: CourtListener ────────────────────────────────────────────────────

def get_cl_headers():
    key = os.environ.get("COURTLISTENER_API_KEY")
    if not key:
        print("WARNING: COURTLISTENER_API_KEY not set — CourtListener fallback unavailable")
        return None
    return {"Authorization": f"Token {key}"}

def fetch_from_courtlistener(case_name, year, headers):
    """
    Fetch opinion text from CourtListener.
    Uses the search API to find the case, then fetches the opinion text.
    """
    if not headers:
        return None, None

    print(f"    Trying CourtListener: {case_name} ({year})")

    # Search for the case
    params = {
        "q": f'"{case_name}"',
        "type": "o",
        "order_by": "score desc",
        "stat_Precedential": "on",
        "court": "scotus",
    }
    if year:
        params["filed_after"] = f"{year}-01-01"
        params["filed_before"] = f"{year}-12-31"

    try:
        resp = requests.get(
            f"{CL_BASE}/search/",
            params=params,
            headers=headers,
            timeout=15
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if not results:
            print(f"    CourtListener: no results")
            return None, None

        # Get the cluster ID from the first result
        cluster_id = results[0].get("cluster_id")
        if not cluster_id:
            return None, None

        # Fetch the cluster to get opinion IDs
        time.sleep(0.3)
        cluster_resp = requests.get(
            f"{CL_BASE}/clusters/{cluster_id}/",
            headers=headers,
            timeout=15
        )
        cluster_resp.raise_for_status()
        cluster = cluster_resp.json()

        # Get the first opinion (usually the main opinion)
        opinion_urls = cluster.get("sub_opinions", [])
        if not opinion_urls:
            return None, None

        # Fetch the opinion text
        time.sleep(0.3)
        op_resp = requests.get(
            opinion_urls[0],
            headers=headers,
            timeout=15
        )
        op_resp.raise_for_status()
        opinion = op_resp.json()

        # Try plain_text first, then html_with_citations
        text = (opinion.get("plain_text") or
                opinion.get("html_with_citations") or
                opinion.get("html") or "")

        if text:
            # Strip HTML if needed
            if "<" in text:
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"&[a-z]+;", " ", text)

            syllabus = extract_syllabus_section(text)
            if len(syllabus) > 200:
                return syllabus, "courtlistener"

            # For old cases without a structured syllabus,
            # return first 3000 chars of opinion text
            if len(text) > 200:
                return clean_text(text[:3000]) + "\n\n[EXCERPT — full opinion available on CourtListener]", "courtlistener_excerpt"

    except Exception as e:
        print(f"    CourtListener failed: {e}")

    return None, None

# ─── Parse citation ───────────────────────────────────────────────────────────

def parse_citation(citation_str):
    """
    Parse a US Reports citation like '381 U.S. 479 (1965)'
    Returns (volume, page, year) or (None, None, None)
    """
    match = re.search(r"(\d+)\s+U\.S\.\s+(\d+)(?:\s*\((\d{4})\))?", citation_str)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None

# ─── Main retrieval logic ─────────────────────────────────────────────────────

def retrieve_case(case_name, year, citation=None, output_dir=Path("syllabi")):
    """
    Retrieve syllabus text for a single case.
    Returns (case_id, output_path) or (case_id, None) on failure.
    """
    year = str(year) if year else None
    case_id = case_id_from_name(case_name, year or "unknown")
    output_path = output_dir / f"{case_id}_syllabus.txt"

    # Skip if already retrieved
    if output_path.exists():
        print(f"  ✓ {case_name} — already retrieved, skipping")
        return case_id, output_path

    print(f"  Retrieving: {case_name} ({year})")

    session = requests.Session()
    session.headers.update({"User-Agent": "LexGraph/1.0 (legal research; contact via github)"})

    text = None
    source = None

    # Strategy 1: LII (best for post-1990 SCOTUS cases)
    if citation:
        volume, page, _ = parse_citation(citation)
        if volume and page:
            text, source = fetch_from_lii(volume, page, session)
    elif year and int(year) >= LII_SYLLABUS_CUTOFF:
        # Try to find the LII URL by searching
        # For now, skip — need citation for LII
        pass

    # Strategy 2: CourtListener (fallback)
    if not text:
        cl_headers = get_cl_headers()
        text, source = fetch_from_courtlistener(case_name, year, cl_headers)
        time.sleep(0.5)

    if not text:
        print(f"  ✗ {case_name} — could not retrieve from any source")
        return case_id, None

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    header = f"""Case: {case_name}
Year: {year or 'unknown'}
Citation: {citation or 'unknown'}
Source: {source}
Case ID: {case_id}
{'=' * 60}

"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + text)

    print(f"  ✓ {case_name} — saved to {output_path} [{source}]")
    return case_id, output_path

# ─── Batch processing ─────────────────────────────────────────────────────────

def parse_cases_file(filepath):
    """
    Parse a cases input file.
    Format: one case per line — "Case Name, Year" or "Case Name, Year, Citation"
    Lines starting with # are comments.
    """
    cases = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            name = parts[0]
            year = parts[1] if len(parts) > 1 else None
            citation = parts[2] if len(parts) > 2 else None
            cases.append((name, year, citation))
    return cases

def run_batch(cases_file, output_dir, delay=1.0):
    """Run Elsa on a batch of cases."""
    output_dir = Path(output_dir)
    cases = parse_cases_file(cases_file)

    print(f"\nElsa — Case Retrieval Agent")
    print(f"{'─' * 60}")
    print(f"Cases to retrieve: {len(cases)}")
    print(f"Output directory:  {output_dir}")
    print()

    results = {"success": [], "failed": []}

    for i, (name, year, citation) in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}]")
        case_id, path = retrieve_case(name, year, citation, output_dir)
        if path:
            results["success"].append(case_id)
        else:
            results["failed"].append(name)
        if i < len(cases):
            time.sleep(delay)

    print(f"\n{'─' * 60}")
    print(f"Retrieved: {len(results['success'])}/{len(cases)}")
    if results["failed"]:
        print(f"Failed ({len(results['failed'])}):")
        for name in results["failed"]:
            print(f"  ✗ {name}")

    return results

# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Elsa — Case Retrieval Agent for LexGraph"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cases", help="Path to cases list file")
    group.add_argument("--case", help="Single case name")

    parser.add_argument("--year", help="Year (for single case mode)")
    parser.add_argument("--citation", help="US Reports citation e.g. '381 U.S. 479'")
    parser.add_argument("--output", default="syllabi", help="Output directory (default: syllabi/)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between requests in seconds (default: 1.0)")
    args = parser.parse_args()

    if args.cases:
        run_batch(args.cases, args.output, args.delay)
    else:
        case_id, path = retrieve_case(
            args.case, args.year, args.citation, Path(args.output)
        )
        if not path:
            sys.exit(1)
