#!/usr/bin/env python3
"""
Elsa — Case Retrieval Agent v2.1
Retrieves Supreme Court syllabi and opinion text for pipeline input.

Retrieval cascade (stops at first success):
    1. Case registry — direct CourtListener ID lookup (instant, no search)
    2. LII by citation — best for post-1990 SCOTUS cases
    3. CourtListener by citation — volume/page lookup via search API
    4. CourtListener by name variants — fallback name matching
    5. Justia — structured full-text for virtually all SCOTUS cases
    6. Google Scholar — broad coverage fallback
    7. Manual queue — writes to manual_queue.txt and continues

Self-populating registry: every successful retrieval writes the
CourtListener ID back to case_registry.json for future use.

Usage:
    from elsa import retrieve_case
    case_id, syllabus_path = retrieve_case("Miranda v. Arizona", "1966", "384 U.S. 436")
"""

import os
import re
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup

# ─── Configuration ─────────────────────────────────────────────────────────────

CL_BASE = "https://www.courtlistener.com/api/rest/v4"
LII_BASE = "https://www.law.cornell.edu/supremecourt/text"
SCOTUS_BASE = "https://www.supremecourt.gov/opinions"
LII_SYLLABUS_CUTOFF = 1990  # LII has structured syllabi for cases after this year

PIPELINE_DIR = Path(__file__).parent
REGISTRY_PATH = PIPELINE_DIR / "case_registry.json"
MANUAL_QUEUE_PATH = PIPELINE_DIR / "manual_queue.txt"

# ─── Registry ──────────────────────────────────────────────────────────────────

def load_registry():
    """Load the case registry from disk."""
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    return {}

def save_registry(registry):
    """Save the case registry to disk."""
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(registry, f, indent=2)

def update_registry(case_id, courtlistener_id, short_name="", citation="", decided_date=""):
    """Add or update a case in the registry."""
    registry = load_registry()
    if case_id not in registry:
        registry[case_id] = {}
    registry[case_id]["courtlistener_id"] = str(courtlistener_id)
    if short_name:
        registry[case_id]["short_name"] = short_name
    if citation:
        registry[case_id]["citation"] = citation
    if decided_date:
        registry[case_id]["decided_date"] = decided_date
    save_registry(registry)

def add_to_manual_queue(case_name, year, citation, reason):
    """Write a failed case to the manual queue file."""
    with open(MANUAL_QUEUE_PATH, 'a') as f:
        f.write(f"{case_name} ({year}) | {citation or 'no citation'} | {reason}\n")
    print(f"  → Added to manual_queue.txt: {case_name}")

# ─── Utilities ─────────────────────────────────────────────────────────────────

def case_id_from_name(name, year):
    """Generate a stable snake_case case ID from name and year."""
    parts = re.split(r'\s+v\.?\s+', name, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        p1 = re.sub(r"['\"]", "", parts[0].split(",")[0].strip())
        p2 = re.sub(r"['\"]", "", parts[1].split(",")[0].strip())
        p1 = re.sub(r"[^a-z0-9]+", "_", p1.lower()).strip("_")
        p2 = re.sub(r"[^a-z0-9]+", "_", p2.lower()).strip("_")
        return f"{p1}_v_{p2}_{year}"
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"{slug}_{year}"

def parse_citation(citation_str):
    """Parse a US Reports citation like '381 U.S. 479 (1965)'."""
    if not citation_str:
        return None, None, None
    match = re.search(r"(\d+)\s+U\.S\.\s+(\d+)(?:\s*\((\d{4})\))?", citation_str)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None

def build_name_variants(case_name):
    """Generate simplified name variants for search."""
    variants = [case_name]
    # Strip corporate suffixes
    stripped = re.sub(r'\b(Co\.|Corp\.|Inc\.|Ltd\.|LLC)\b', '', case_name).strip()
    stripped = re.sub(r'\s+', ' ', stripped)
    if stripped != case_name and stripped not in variants:
        variants.append(stripped)
    # Strip comma-separated suffixes from each party
    parts = re.split(r'\s+v\.\s+', case_name, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        p1 = parts[0].split(',')[0].strip()
        p2 = parts[1].split(',')[0].strip()
        simple = f"{p1} v. {p2}"
        if simple not in variants:
            variants.append(simple)
    return variants

def get_cl_headers():
    """Get CourtListener API headers."""
    api_key = os.environ.get("COURTLISTENER_API_KEY", "")
    if not api_key:
        return None
    return {
        "Authorization": f"Token {api_key}",
        "User-Agent": "LexGraph/2.0 (legal research; contact via github)"
    }

def clean_text(text):
    """Clean whitespace from extracted text."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()

# ─── Text Extraction ───────────────────────────────────────────────────────────

def extract_syllabus_section(text):
    """Extract the syllabus portion from opinion text."""
    patterns = [
        r'(?:SYLLABUS|Syllabus)\s*\n+(.*?)(?=\n+(?:OPINION|Opinion|CHIEF JUSTICE|JUSTICE|Justice|MR\. JUSTICE|PER CURIAM))',
        r'(?:^|\n)Syllabus\s*\n+(.*?)(?=\n+(?:Opinion|JUSTICE|Justice))',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return clean_text(match.group(1))
    # Return first 3000 chars if no syllabus found
    return clean_text(text[:3000])

# ─── Strategy 1: Case Registry ─────────────────────────────────────────────────

def fetch_by_registry(case_id, headers):
    """Fetch directly using a known CourtListener ID from the registry."""
    registry = load_registry()
    entry = registry.get(case_id)
    if not entry or not entry.get("courtlistener_id"):
        return None, None

    cl_id = entry["courtlistener_id"]
    print(f"    Registry hit: CourtListener ID {cl_id}")

    try:
        # Try opinion endpoint directly
        resp = requests.get(
            f"{CL_BASE}/opinions/{cl_id}/",
            headers=headers,
            timeout=15
        )
        if resp.status_code == 200:
            opinion = resp.json()
            text = (opinion.get("plain_text") or
                    opinion.get("html_with_citations") or
                    opinion.get("html") or "")
            if text and "<" in text:
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"&[a-z]+;", " ", text)
            if len(text) > 200:
                syllabus = extract_syllabus_section(text)
                return syllabus, "registry_courtlistener"

        # Try cluster endpoint
        resp = requests.get(
            f"{CL_BASE}/clusters/{cl_id}/",
            headers=headers,
            timeout=15
        )
        if resp.status_code == 200:
            cluster = resp.json()
            opinion_urls = cluster.get("sub_opinions", [])
            if opinion_urls:
                time.sleep(0.3)
                op_resp = requests.get(opinion_urls[0], headers=headers, timeout=15)
                if op_resp.status_code == 200:
                    opinion = op_resp.json()
                    text = (opinion.get("plain_text") or
                            opinion.get("html_with_citations") or
                            opinion.get("html") or "")
                    if text and "<" in text:
                        text = re.sub(r"<[^>]+>", " ", text)
                        text = re.sub(r"&[a-z]+;", " ", text)
                    if len(text) > 200:
                        syllabus = extract_syllabus_section(text)
                        return syllabus, "registry_courtlistener"

    except Exception as e:
        print(f"    Registry fetch failed: {e}")

    return None, None

# ─── Strategy 2: LII by Citation ───────────────────────────────────────────────

def fetch_from_lii(volume, page, session):
    """Fetch syllabus from LII using US Reports citation."""
    url = f"{LII_BASE}/{volume}/{page}"
    print(f"    Trying LII: {url}")
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 404:
            print(f"    LII 404 — case not available")
            return None, None
        resp.raise_for_status()
        html = resp.text

        # Check for intentionally omitted placeholder
        if 'intentionally omitted' in html.lower():
            print(f"    LII: syllabus intentionally omitted — falling back")
            return None, None

        soup = BeautifulSoup(html, 'html.parser')

        # Try structured syllabus div
        for selector in ['.syllabus', '#syllabus', '[class*="syllabus"]']:
            el = soup.select_one(selector)
            if el:
                text = clean_text(el.get_text())
                if len(text) > 300:
                    return text, "lii_structured"

        # Try finding Syllabus section in text
        text = soup.get_text()
        for marker in ['Syllabus', 'SYLLABUS']:
            idx = text.find(marker)
            if idx >= 0:
                candidate = text[idx + len(marker):idx + 8000]
                # Find where opinion starts
                for end_marker in ['\nOPINION', '\nJUSTICE', '\nMR. JUSTICE',
                                   '\nCHIEF JUSTICE', '\nPER CURIAM']:
                    cut = candidate.find(end_marker)
                    if cut > 300:
                        syllabus = clean_text(candidate[:cut])
                        if len(syllabus) > 300:
                            return syllabus, "lii_extracted"

    except Exception as e:
        print(f"    LII failed: {e}")

    return None, None

# ─── Strategy 3: CourtListener by Citation ─────────────────────────────────────

def fetch_cl_by_citation(volume, page, year, headers):
    """Search CourtListener by US Reports citation volume and page."""
    if not headers or not volume or not page:
        return None, None, None

    print(f"    Trying CourtListener citation: {volume} U.S. {page}")
    try:
        resp = requests.get(
            f"{CL_BASE}/search/",
            params={
                "q": f"{volume} U.S. {page}",
                "type": "o",
                "court": "scotus",
                "order_by": "score desc",
                "filed_after": f"{year}-01-01" if year else None,
                "filed_before": f"{year}-12-31" if year else None,
            },
            headers=headers,
            timeout=15
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            cluster_id = results[0].get("cluster_id")
            if cluster_id:
                return fetch_cl_by_cluster_id(cluster_id, headers)
    except Exception as e:
        print(f"    CourtListener citation search failed: {e}")

    return None, None, None

# ─── Strategy 4: CourtListener by Name Variants ────────────────────────────────

def fetch_cl_by_name(case_name, year, headers):
    """Search CourtListener using name variants."""
    if not headers:
        return None, None, None

    variants = build_name_variants(case_name)
    for variant in variants:
        print(f"    Trying CourtListener name: {variant}")
        try:
            params = {
                "q": f'"{variant}"',
                "type": "o",
                "order_by": "score desc",
                "stat_Precedential": "on",
                "court": "scotus",
            }
            if year:
                params["filed_after"] = f"{year}-01-01"
                params["filed_before"] = f"{year}-12-31"

            resp = requests.get(
                f"{CL_BASE}/search/",
                params=params,
                headers=headers,
                timeout=15
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                cluster_id = results[0].get("cluster_id")
                if cluster_id:
                    text, source, cl_id = fetch_cl_by_cluster_id(cluster_id, headers)
                    if text:
                        print(f"    CourtListener: found via name variant '{variant}'")
                        return text, source, cl_id
        except Exception as e:
            print(f"    CourtListener name search failed for '{variant}': {e}")
            continue

    return None, None, None

def fetch_cl_by_cluster_id(cluster_id, headers):
    """Fetch opinion text from a CourtListener cluster ID."""
    try:
        time.sleep(0.3)
        cluster_resp = requests.get(
            f"{CL_BASE}/clusters/{cluster_id}/",
            headers=headers,
            timeout=15
        )
        cluster_resp.raise_for_status()
        cluster = cluster_resp.json()

        opinion_urls = cluster.get("sub_opinions", [])
        if not opinion_urls:
            return None, None, None

        time.sleep(0.3)
        op_resp = requests.get(opinion_urls[0], headers=headers, timeout=15)
        op_resp.raise_for_status()
        opinion = op_resp.json()

        cl_id = str(opinion.get("id", cluster_id))
        text = (opinion.get("plain_text") or
                opinion.get("html_with_citations") or
                opinion.get("html") or "")

        if text and "<" in text:
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&[a-z]+;", " ", text)

        if len(text) > 200:
            syllabus = extract_syllabus_section(text)
            return syllabus, "courtlistener", cl_id

    except Exception as e:
        print(f"    CourtListener cluster fetch failed: {e}")

    return None, None, None

# ─── Strategy 5: Justia ────────────────────────────────────────────────────────

def fetch_from_justia(volume, page, case_name):
    """
    Fetch from Justia Supreme Court database.
    Justia has structured full-text for virtually all SCOTUS cases.
    URL pattern: https://supreme.justia.com/cases/federal/us/{volume}/{page}/
    """
    if not volume or not page:
        return None, None

    url = f"https://supreme.justia.com/cases/federal/us/{volume}/{page}/"
    print(f"    Trying Justia: {url}")
    try:
        resp = requests.get(url, timeout=15,
                           headers={"User-Agent": "LexGraph/2.0 (legal research)"})
        if resp.status_code == 404:
            print(f"    Justia 404 — not available at this URL")
            return None, None
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Try to find the syllabus/opinion section
        # Justia structures content in <p> tags within main content divs
        content = None
        for selector in ['#opinion-text', '.opinion-text', 'article', 'main',
                         '[class*="opinion"]', '[id*="opinion"]']:
            el = soup.select_one(selector)
            if el:
                content = el
                break

        if not content:
            content = soup.find('body')

        if content:
            text = clean_text(content.get_text())
            if len(text) > 300:
                # Try to extract just the syllabus
                syllabus = extract_syllabus_section(text)
                if len(syllabus) > 200:
                    return syllabus, "justia"
                # Return first 3000 chars of opinion
                return clean_text(text[:3000]), "justia_excerpt"

    except Exception as e:
        print(f"    Justia failed: {e}")

    return None, None

# ─── Strategy 6: Google Scholar ────────────────────────────────────────────────

def fetch_from_google_scholar(case_name, year, citation):
    """
    Fetch from Google Scholar case law database.
    Google Scholar has broad SCOTUS coverage including pre-1900 cases.
    """
    volume, page, _ = parse_citation(citation)

    # Build search query — citation is most reliable
    if volume and page:
        query = f"{volume} U.S. {page}"
    else:
        query = case_name

    url = f"https://scholar.google.com/scholar?q={requests.utils.quote(query)}&as_sdt=2006&hl=en"
    print(f"    Trying Google Scholar: {query}")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, timeout=15, headers=headers)
        if resp.status_code != 200:
            print(f"    Google Scholar: status {resp.status_code}")
            return None, None

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Find case links in results
        case_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/scholar_case?' in href and 'case=' in href:
                case_links.append(href)

        if not case_links:
            print(f"    Google Scholar: no case links found")
            return None, None

        # Fetch the first case result
        case_url = case_links[0]
        if not case_url.startswith('http'):
            case_url = f"https://scholar.google.com{case_url}"

        time.sleep(1.0)  # Be polite
        case_resp = requests.get(case_url, timeout=15, headers=headers)
        if case_resp.status_code != 200:
            return None, None

        case_soup = BeautifulSoup(case_resp.text, 'html.parser')

        # Extract opinion text
        opinion_div = case_soup.find('div', id='gs_opinion')
        if not opinion_div:
            opinion_div = case_soup.find('div', class_='gs_opinion')
        if not opinion_div:
            opinion_div = case_soup.find('body')

        if opinion_div:
            text = clean_text(opinion_div.get_text())
            if len(text) > 300:
                syllabus = extract_syllabus_section(text)
                if len(syllabus) > 200:
                    return syllabus, "google_scholar"
                return clean_text(text[:3000]), "google_scholar_excerpt"

    except Exception as e:
        print(f"    Google Scholar failed: {e}")

    return None, None

# ─── Main Retrieval Function ───────────────────────────────────────────────────

def retrieve_case(case_name, year, citation=None, output_dir=Path("syllabi")):
    """
    Retrieve syllabus/opinion text for a SCOTUS case.
    Returns (case_id, output_path) — output_path is None on failure.
    """
    output_dir = Path(output_dir)
    case_id = case_id_from_name(case_name, year or "unknown")
    output_path = output_dir / f"{case_id}_syllabus.txt"

    # Check if already retrieved
    if output_path.exists():
        print(f"  ✓ {case_name} — already retrieved, skipping")
        return case_id, output_path

    print(f"  Retrieving: {case_name} ({year})")

    session = requests.Session()
    session.headers.update({"User-Agent": "LexGraph/2.0 (legal research; contact via github)"})
    cl_headers = get_cl_headers()

    text = None
    source = None
    cl_id = None

    # Strategy 1: Registry lookup
    if cl_headers:
        text, source = fetch_by_registry(case_id, cl_headers)

    # Strategy 2: LII by citation
    if not text and citation:
        volume, page, _ = parse_citation(citation)
        if volume and page and year and int(year) >= LII_SYLLABUS_CUTOFF:
            text, source = fetch_from_lii(volume, page, session)

    # Strategy 3: CourtListener by citation
    if not text and citation and cl_headers:
        volume, page, _ = parse_citation(citation)
        if volume and page:
            text, source, cl_id = fetch_cl_by_citation(volume, page, year, cl_headers)

    # Strategy 4: CourtListener by name variants
    if not text and cl_headers:
        text, source, cl_id = fetch_cl_by_name(case_name, year, cl_headers)

    # Strategy 5: Justia
    if not text:
        volume, page, _ = parse_citation(citation)
        text, source = fetch_from_justia(volume, page, case_name)

    # Strategy 6: Google Scholar
    if not text:
        text, source = fetch_from_google_scholar(case_name, year, citation)

    # All strategies failed
    if not text:
        print(f"  ✗ {case_name} — could not retrieve from any source")
        add_to_manual_queue(
            case_name, year, citation,
            f"All retrieval strategies failed. Try: https://www.courtlistener.com/?q={case_name.replace(' ', '+')}&type=o&order_by=score+desc&stat_Precedential=on&court=scotus"
        )
        return case_id, None

    # Update registry with newly found CourtListener ID
    if cl_id and source in ("courtlistener", "courtlistener_excerpt"):
        update_registry(case_id, cl_id, case_name, citation or "", "")
        print(f"    Registry updated: {case_id} → {cl_id}")

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

    print(f"  ✓ {case_name} — saved [{source}]")
    return case_id, output_path

# ─── Batch Processing ──────────────────────────────────────────────────────────

def parse_cases_file(filepath):
    """Parse cases input file. Format: Name, Year, Citation"""
    cases = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            name = parts[0]
            year = parts[1] if len(parts) > 1 else None
            citation = ", ".join(parts[2:]) if len(parts) > 2 else None
            cases.append((name, year, citation))
    return cases

def run_batch(cases_file, output_dir, delay=1.0):
    """Run Elsa on a batch of cases."""
    output_dir = Path(output_dir)
    cases = parse_cases_file(cases_file)

    print(f"\nElsa v2.0 — Case Retrieval Agent")
    print(f"{'─' * 60}")
    print(f"Cases: {len(cases)}")

    results = {"retrieved": [], "failed": [], "skipped": []}

    for case_name, year, citation in cases:
        case_id, path = retrieve_case(case_name, year, citation, output_dir)
        if path:
            if path.exists():
                results["retrieved"].append(case_name)
        else:
            results["failed"].append(case_name)
        time.sleep(delay)

    print(f"\nRetrieved: {len(results['retrieved'])} | Failed: {len(results['failed'])}")
    if results["failed"]:
        print(f"Failed cases written to: {MANUAL_QUEUE_PATH}")
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Elsa v2.0 — Case Retrieval Agent")
    parser.add_argument("--cases", help="Path to cases list file")
    parser.add_argument("--name", help="Single case name")
    parser.add_argument("--year", help="Case year")
    parser.add_argument("--citation", help="Case citation")
    parser.add_argument("--output-dir", default="syllabi", help="Output directory")
    args = parser.parse_args()

    if args.cases:
        run_batch(args.cases, args.output_dir)
    elif args.name:
        case_id, path = retrieve_case(args.name, args.year, args.citation,
                                       Path(args.output_dir))
        if path:
            print(f"Success: {path}")
        else:
            print("Failed — check manual_queue.txt")
    else:
        parser.print_help()
