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

# Known case name variants — maps input names to Oyez canonical names
CASE_NAME_VARIANTS = {
    'dred scott v. sandford': 'dred scott v. sanford',  # Common misspelling
    'youngstown sheet and tube co. v. sawyer': 'youngstown sheet tube co v sawyer',
    'youngstown sheet & tube co. v. sawyer': 'youngstown sheet tube co v sawyer',
    'board of education v. earls': 'board of education of independent school district no 92 of pottawatomie county v earls',
    'massachusetts v. epa': 'massachusetts v environmental protection agency',
    'massachusetts v. e.p.a.': 'massachusetts v environmental protection agency',
}

def normalize_case_name(name):
    """Normalize case name — strip periods from initials like J.E.B. -> JEB, U.S. -> US."""
    # Interior periods between caps: J.E.B -> JEB (two passes handles odd counts)
    result = re.sub(r'([A-Z])\.([A-Z])', r'\1\2', name)
    result = re.sub(r'([A-Z])\.([A-Z])', r'\1\2', result)
    # Trailing period after all-caps sequence before space/end/punctuation
    result = re.sub(r'([A-Z]{2,})\. ', r'\1 ', result)
    result = re.sub(r'([A-Z]{2,})\.$', r'\1', result)
    result = re.sub(r'([A-Z]{2,})\.v\.', r'\1 v.', result)
    result = re.sub(r'([A-Z]{1})\. v\.', r'\1 v.', result)
    result = re.sub(r'([A-Z]{1})\.,', r'\1,', result)
    result = ' '.join(result.split())
    return result

def build_name_variants(case_name):
    """Generate simplified name variants for search."""
    variants = [case_name]

    # Add normalized variant (strips periods from initials like J.E.B. -> JEB)
    normalized = normalize_case_name(case_name)
    if normalized != case_name and normalized not in variants:
        variants.append(normalized)

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
        # Also add normalized simple variant
        norm_simple = normalize_case_name(simple)
        if norm_simple not in variants:
            variants.append(norm_simple)

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
    """Extract the syllabus portion from opinion text.
    Falls back to opening opinion text if no syllabus found.
    Extends to 5000 chars to capture more doctrinal content for thin sources.
    """
    patterns = [
        r'(?:SYLLABUS|Syllabus)\s*\n+(.*?)(?=\n+(?:OPINION|Opinion|CHIEF JUSTICE|JUSTICE|Justice|MR\. JUSTICE|PER CURIAM))',
        r'(?:^|\n)Syllabus\s*\n+(.*?)(?=\n+(?:Opinion|JUSTICE|Justice))',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            extracted = clean_text(match.group(1))
            if len(extracted) > 300:
                return extracted

    # No syllabus section found — extract opening of majority opinion
    # Try to find where the majority opinion starts and take more content
    opinion_start_patterns = [
        r'(?:CHIEF JUSTICE|JUSTICE|Justice|MR\. JUSTICE)\s+\w+\s+delivered the opinion',
        r'(?:CHIEF JUSTICE|JUSTICE|Justice)\s+\w+\s+announced the judgment',
        r'PER CURIAM',
        r'Opinion of the Court',
    ]
    for pattern in opinion_start_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Take from opinion start up to 5000 chars
            opinion_text = text[match.start():match.start() + 5000]
            extracted = clean_text(opinion_text)
            if len(extracted) > 300:
                return extracted

    # Last resort: first 5000 chars
    return clean_text(text[:5000])

# ─── Strategy 1: Case Registry ─────────────────────────────────────────────────

def verify_case_identity(case_name, text, citation, debug=False):
    """
    Verify that retrieved text is actually for the expected case.
    Returns text if valid, None if identity check fails.
    Checks for party names and basic content length.
    Set debug=True to print detailed trace.
    """
    if not text or len(text) < 400:
        print(f"    Identity check: text too short ({len(text) if text else 0} chars) — likely docket entry or order")
        return None

    # Pre-compute normalized text for abbreviation expansion checks (INS, JEB, etc.)
    text_lower_norm = normalize_case_name(text[:500]).lower()

    # Oyez text starts with "Case: {name}" — compare full name, not just 4 chars
    text_start = text[:300].lower()
    if text_start.startswith("case:"):
        case_line_raw = text_start.split("\n")[0]
        # Normalize the Oyez case line (strip periods from initials) for comparison
        case_line = normalize_case_name(case_line_raw).lower().replace("case: ", "").strip()
        case_line = "case: " + case_line  # put prefix back for split logic
        normalized_input = normalize_case_name(case_name).lower()

        # Extract both party names from input and check they appear in the Oyez case line
        if " v. " in normalized_input:
            input_p1 = normalized_input.split(" v. ")[0].strip()
            input_p2 = normalized_input.split(" v. ", 1)[1].strip()
            # Get first meaningful word of each party
            p1_word = re.sub(r'[^a-z]', '', input_p1.split()[0]) if input_p1.split() else ''
            p2_word = re.sub(r'[^a-z]', '', input_p2.split()[0]) if input_p2.split() else ''
            common = {'united', 'state', 'states', 'city', 'county', 'board',
                      'department', 'commissioner', 'director', 'people'}
            # Split Oyez case line at " v. " for positional matching
            if " v. " in case_line or " v " in case_line:
                sep = " v. " if " v. " in case_line else " v "
                oyez_p1 = case_line.split(sep)[0].replace("case: ", "").strip()
                oyez_p2 = case_line.split(sep, 1)[1].strip() if sep in case_line else ""
            else:
                oyez_p1 = case_line.replace("case: ", "").strip()
                oyez_p2 = ""

            # p1 should be in the LEFT side of Oyez name (strict positional check)
            # Do NOT check text_lower_norm for p1 — that breaks Fulton-style wrong-case detection
            p1_ok = (p1_word in oyez_p1) if p1_word not in common else True
            # p2 checks right side; text_lower_norm only for abbreviation expansion fallback
            p2_ok = (p2_word in oyez_p2) if p2_word not in common else True

            if p1_ok and p2_ok:
                # Oyez case header confirms both parties — no content body check needed
                # (Oyez abbreviates names e.g. "Ed." for "Education", "Cty." for "County")
                return text  # Oyez identity confirmed
            # Handle legal abbreviations (INS, NLRB, FTC, etc.)
            LEGAL_ABBREVIATIONS = {
                'ins': 'immigration and naturalization service',
                'nlrb': 'national labor relations board',
                'ftc': 'federal trade commission',
                'fcc': 'federal communications commission',
                'sec': 'securities and exchange commission',
                'epa': 'environmental protection agency',
                'irs': 'internal revenue service',
                'doj': 'department of justice',
                'dhs': 'department of homeland security',
                'hhs': 'department of health and human services',
                'pcaob': 'public company accounting oversight board',
                'cfpb': 'consumer financial protection bureau',
                'fhfa': 'federal housing finance agency',
                # Additional common legal abbreviations
                'fec': 'federal election commission',
                'naacp': 'national association for the advancement of colored people',
                'aclu': 'american civil liberties union',
                'eeoc': 'equal employment opportunity commission',
                'nlra': 'national labor relations act',
                'ada': 'americans with disabilities act',
                'dea': 'drug enforcement administration',
                'fbi': 'federal bureau of investigation',
                'cia': 'central intelligence agency',
                'afa': 'armed forces act',
                'fair': 'forum for academic and institutional rights',
                'pga': 'professional golfers association',
                'atp': 'association of tennis professionals',
            }
            if not p1_ok and p1_word not in common and len(p1_word) <= 6:
                # Check known abbreviations
                if p1_word in LEGAL_ABBREVIATIONS:
                    expanded = LEGAL_ABBREVIATIONS[p1_word]
                    if any(w in oyez_p1 for w in expanded.split()):
                        p1_ok = True
                # Check if it could be an acronym matching the Oyez p1 words
                else:
                    oyez_p1_initials = ''.join(w[0] for w in oyez_p1.split() if w)
                    if p1_word == oyez_p1_initials:
                        p1_ok = True

            if not p1_ok and p1_word not in common:
                print(f"    Oyez identity FAILED: '{p1_word}' not in Oyez p1 '{oyez_p1}' | case_line='{case_line}'")
                return None
            # Also check p2 abbreviations (e.g. McCutcheon v. FEC)
            if not p2_ok and p2_word not in common and len(p2_word) <= 6:
                if p2_word in LEGAL_ABBREVIATIONS:
                    expanded = LEGAL_ABBREVIATIONS[p2_word]
                    if any(w in oyez_p2 or w in oyez_p1 for w in expanded.split()):
                        p2_ok = True
                else:
                    oyez_p2_initials = ''.join(w[0] for w in oyez_p2.split() if w)
                    if p2_word == oyez_p2_initials:
                        p2_ok = True

            if not p2_ok and p2_word not in common:
                print(f"    Oyez identity FAILED: '{p2_word}' not in Oyez name '{case_line}' | oyez_p1='{oyez_p1}' oyez_p2='{oyez_p2}'")
                return None
            return text
        else:
            # Single-party name — check it appears
            p1_word = re.sub(r'[^a-z]', '', normalized_input.split()[0]) if normalized_input.split() else ''
            if p1_word and p1_word in case_line:
                return text
            print(f"    Oyez identity FAILED: '{p1_word}' not in Oyez case line")
            return None

    # Extract party names from case_name — normalize first to handle J.E.B. -> JEB
    normalized_name = normalize_case_name(case_name)
    parts = re.split(r'\s+v\.?\s+', normalized_name, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        p1 = parts[0].split(',')[0].strip().lower()
        p2 = parts[1].split(',')[0].strip().lower()

        # Only check first meaningful word of each party (handles long names)
        p1_word = re.sub(r'[^a-z]', '', p1.split()[0]) if p1.split() else ''
        p2_word = re.sub(r'[^a-z]', '', p2.split()[0]) if p2.split() else ''

        # Also build a version with periods stripped from text for comparison
        # This handles "J. E. B." in text matching "JEB" search term
        text_lower = text.lower()
        text_alpha_only = re.sub(r'[^a-z\s]', '', text_lower)  # strip all non-alpha

        # Skip identity check for very common single-word parties that appear everywhere
        common_words = {'united', 'state', 'states', 'people', 'county', 'city',
                        'board', 'department', 'commissioner', 'director'}

        # Check both in original text and alpha-only text
        p1_found = (p1_word in text_lower or p1_word in text_alpha_only) \
            if p1_word not in common_words else True
        p2_found = (p2_word in text_lower or p2_word in text_alpha_only) \
            if p2_word not in common_words else True

        # Also check legal abbreviations in the text
        if not p1_found and p1_word not in common_words and len(p1_word) <= 6:
            abbrevs = {'ins':'immigration','nlrb':'labor','fcc':'communications',
                      'fec':'election','naacp':'colored','aclu':'liberties',
                      'epa':'environmental','irs':'revenue','ftc':'trade'}
            if p1_word in abbrevs and abbrevs[p1_word] in text_lower:
                p1_found = True

        if not p2_found and p2_word not in common_words and len(p2_word) <= 6:
            abbrevs = {'fec':'election','epa':'environmental','nlrb':'labor',
                      'fcc':'communications','naacp':'colored'}
            if p2_word in abbrevs and abbrevs[p2_word] in text_lower:
                p2_found = True

        if not p1_found and not p2_found:
            print(f"    Identity check FAILED: neither '{p1_word}' nor '{p2_word}' found in text")
            return None

        # If one specific party name is missing, fail — don't just warn
        if not p1_found and p1_word not in common_words:
            print(f"    Identity check FAILED: '{p1_word}' not found in text")
            return None

        if not p2_found and p2_word not in common_words:
            print(f"    Identity check FAILED: '{p2_word}' not found in text")
            return None

    return text
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
        # Try cluster endpoint first
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

    except Exception as e:
        print(f"    Registry fetch failed: {e}")

    return None, None

# ─── Strategy 2: Oyez ──────────────────────────────────────────────────────────

OYEZ_BASE = "https://api.oyez.org"

# Direct Oyez case URLs — bypasses name matching, identity guaranteed by URL
# Format: case_id -> (oyez_term, oyez_docket)
OYEZ_DIRECT_URLS = {
    # Landmark cases with known Oyez term/docket
    "marbury_v_madison_1803":                     ("1789-1850", "5us137"),
    "mcculloch_v_maryland_1819":                  ("1789-1850", "17us316"),
    "dred_scott_v_sandford_1857":                 ("1789-1850", "60us393"),
    "plessy_v_ferguson_1896":                     ("1850-1900", "163us537"),
    "schenck_v_united_states_1919":               ("1900-1940", "249us47"),
    "gitlow_v_new_york_1925":                     ("1900-1940", "268us652"),
    "whitney_v_california_1927":                  ("1900-1940", "274us357"),
    "near_v_minnesota_1931":                      ("1900-1940", "283us697"),
    "nlrb_v_jones_and_laughlin_steel_corp_1937":  ("1900-1940", "301us1"),
    "west_coast_hotel_co_v_parrish_1937":         ("1900-1940", "300us379"),
    "korematsu_v_united_states_1944":             ("1940-1955", "323us214"),
    "everson_v_board_of_education_1947":          ("1940-1955", "330us1"),
    "shelley_v_kraemer_1948":                     ("1940-1955", "334us1"),
    "youngstown_sheet_tube_co_v_sawyer_1952":     ("1940-1955", "343us579"),
    "yates_v_united_states_1957":                 ("1955-1975", "354us298"),
    "naacp_v_alabama_1958":                       ("1955-1975", "357us449"),
    "brown_v_board_of_education_1954":            ("1940-1955", "347us483"),
    "baker_v_carr_1962":                          ("1955-1975", "369us186"),
    "roe_v_wade_1973":                            ("1971", "70-18"),
    "fcc_v_pacifica_foundation_1978":             ("1977", "77-528"),
    "board_of_education_v_earls_2002":            ("2001", "01-332"),
    "mccutcheon_v_fec_2014":                      ("2013", "12-536"),
    "massachusetts_v_epa_2007":                   ("2006", "05-1120"),
    # Additional cases with known Oyez dockets
    "board_of_education_v_earls_2002":            ("2001", "01-332"),
    "fcc_v_pacifica_foundation_1978":             ("1977", "77-528"),
    "baker_v_carr_1962":                          ("1960", "6"),
    "roe_v_wade_1973":                            ("1971", "70-18"),
    "mapp_v_ohio_1961":                           ("1955-1975", "367us643"),
    "gideon_v_wainwright_1963":                   ("1955-1975", "372us335"),
    "new_york_times_co_v_sullivan_1964":          ("1955-1975", "376us254"),
    "griswold_v_connecticut_1965":                ("1955-1975", "381us479"),
    "miranda_v_arizona_1966":                     ("1955-1975", "384us436"),
    "loving_v_virginia_1967":                     ("1955-1975", "388us1"),
    "terry_v_ohio_1968":                          ("1955-1975", "392us1"),
    "roe_v_wade_1973":                            ("1971", "70-18"),
    "united_states_v_nixon_1974":                 ("1955-1975", "418us683"),
    "buckley_v_valeo_1976":                       ("1955-1975", "424us1"),
}

def _citation_to_oyez_docket(citation, year):
    """
    Convert a US Reports citation to an Oyez URL docket string.
    Pre-1956 cases: Oyez uses citation as docket e.g. 347us483
    Post-1956 cases: Oyez uses numeric docket number (unknown without registry)
    """
    if not citation or not year:
        return None, None
    # Parse volume and page from citation
    m = re.match(r'(\d+)\s+U\.?S\.?\s+(\d+)', citation)
    if not m:
        return None, None
    volume, page = m.group(1), m.group(2)
    yr = int(year)
    if yr < 1956:
        # Pre-1956: Oyez uses citation-based docket and grouped terms
        if yr < 1941:
            term = "1789-1850" if yr <= 1850 else "1851-1900" if yr <= 1900 else "1900-1940"
        else:
            term = "1940-1955"
        docket = f"{volume}us{page}"
        return term, docket
    return None, None  # Post-1955: need explicit registry entry

def fetch_oyez_direct(case_id, case_name, citation):
    """Fetch directly from Oyez using known term/docket. Identity is guaranteed."""
    term, docket = None, None

    # First check explicit registry
    if case_id in OYEZ_DIRECT_URLS:
        term, docket = OYEZ_DIRECT_URLS[case_id]
    # Then try citation-based URL construction (pre-1956 cases)
    elif citation:
        year = case_id.split('_')[-1] if case_id.split('_')[-1].isdigit() else None
        term, docket = _citation_to_oyez_docket(citation, year)

    if not term or not docket:
        return None, None

    url = f"{OYEZ_BASE}/cases/{term}/{docket}"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; LexGraph/2.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"    Oyez direct: HTTP {resp.status_code} for {url}")
            return None, None
        # Check we got JSON not HTML (old Oyez CMS returns HTML login page)
        ct = resp.headers.get("content-type", "")
        if "html" in ct.lower():
            print(f"    Oyez direct: got HTML (login page) for {url} — falling through")
            return None, None
        data = resp.json()
        # Oyez API sometimes returns a list — find the right case in it
        if isinstance(data, list):
            # Find case matching our citation or name
            detail = None
            norm_name = normalize_case_name(case_name).lower()
            for item in data:
                item_name = normalize_case_name(item.get('name', '')).lower()
                if norm_name in item_name or item_name in norm_name:
                    detail = item
                    break
                # Also match by citation
                item_cite = item.get('citation', {})
                if isinstance(item_cite, dict):
                    cite_str = item_cite.get('cite', '')
                elif isinstance(item_cite, str):
                    cite_str = item_cite
                else:
                    cite_str = ''
                if citation and citation.replace(' ','') in cite_str.replace(' ',''):
                    detail = item
                    break
            if not detail and data:
                detail = data[0]  # fallback to first result
        else:
            detail = data
        text = _format_oyez_text(detail, case_name)
        if text and len(text) > 200:  # Lower threshold — Oyez direct is pre-formatted
            print(f"    ✓ Oyez direct [{url}]")
            return text, "oyez_direct"
        else:
            print(f"    Oyez direct: text too short ({len(text) if text else 0} chars) for {url}")
    except Exception as e:
        print(f"    Oyez direct failed: {e}")
    return None, None



def fetch_from_oyez_by_citation(volume, page, year, case_name):
    """Fetch case data from Oyez by citation (volume + page) and year."""
    if not volume or not page or not year:
        return None, None
    try:
        # Search Oyez cases for the given term year
        url = f"{OYEZ_BASE}/cases?filter=term:{year}&per_page=50"
        resp = requests.get(url, timeout=15,
            headers={"User-Agent": "LexGraph/2.0 (legal research)"})
        if resp.status_code != 200:
            return None, None

        cases = resp.json()
        if not isinstance(cases, list):
            return None, None

        # Match by citation
        target_cite = f"{volume} U.S. {page}"
        normalized = normalize_case_name(case_name).lower()

        matched = None
        for case in cases:
            cite = case.get("citation", {})
            if isinstance(cite, dict):
                cite_str = cite.get("cite", "")
            else:
                cite_str = str(cite)
            if target_cite in cite_str:
                matched = case
                break

        # Fallback: match by normalized name
        if not matched:
            for case in cases:
                oyez_name = normalize_case_name(
                    case.get("name", "")).lower()
                if normalized in oyez_name or oyez_name in normalized:
                    matched = case
                    break

        if not matched:
            return None, None

        # Fetch full case detail
        href = matched.get("href", "")
        if not href:
            return None, None

        time.sleep(0.3)
        detail_resp = requests.get(href, timeout=15,
            headers={"User-Agent": "LexGraph/2.0 (legal research)"})
        if detail_resp.status_code != 200:
            return None, None

        detail = detail_resp.json()
        return _format_oyez_text(detail, matched.get("name", "")), "oyez"

    except Exception as e:
        print(f"    Oyez citation fetch failed: {e}")
        return None, None

def fetch_from_oyez_by_name(case_name, year):
    """Fetch case data from Oyez by case name search."""
    try:
        normalized = normalize_case_name(case_name).lower()
        # Try ±1 year range in case year is off by one
        for try_year in [year, str(int(year)-1), str(int(year)+1)]:
            url = f"{OYEZ_BASE}/cases?filter=term:{try_year}&per_page=100"
            resp = requests.get(url, timeout=15,
                headers={"User-Agent": "LexGraph/2.0 (legal research)"})
            if resp.status_code != 200:
                continue

            cases = resp.json()
            if not isinstance(cases, list):
                continue

            # Try to match case name
            for case in cases:
                oyez_name = normalize_case_name(
                    case.get("name", "")).lower()
                # Match if normalized name is substring or vice versa
                p1 = normalized.split(" v. ")[0].strip() if " v. " in normalized else normalized
                # Check BOTH parties in the Oyez name, not just first party
                input_norm = normalize_case_name(case_name).lower()
                if " v. " in input_norm:
                    _p1 = input_norm.split(" v. ")[0].split()[0] if input_norm.split(" v. ")[0].split() else ''
                    _p2 = input_norm.split(" v. ", 1)[1].split()[0] if input_norm.split(" v. ", 1)[1].split() else ''
                    _common = {'united', 'state', 'states', 'city', 'county', 'board', 'department'}
                    _p1_ok = (_p1 in oyez_name) if _p1 not in _common else True
                    _p2_ok = (_p2 in oyez_name) if _p2 not in _common else True
                    _name_match = _p1_ok and _p2_ok
                else:
                    _name_match = p1 and p1 in oyez_name
                if _name_match:
                    href = case.get("href", "")
                    if not href:
                        continue
                    print(f"    Oyez: matched '{case.get('name')}' for term {try_year}")
                    time.sleep(0.3)
                    detail_resp = requests.get(href, timeout=15,
                        headers={"User-Agent": "LexGraph/2.0 (legal research)"})
                    if detail_resp.status_code == 200:
                        detail = detail_resp.json()
                        text = _format_oyez_text(detail, case.get("name", ""))
                        if text:
                            return text, "oyez"

        return None, None

    except Exception as e:
        print(f"    Oyez name fetch failed: {e}")
        return None, None

def _format_oyez_text(detail, case_name):
    """Format Oyez JSON detail into a readable text block for the builder."""
    if not detail:
        return None

    parts = []
    parts.append(f"Case: {detail.get('name', case_name)}")

    # Citation
    cite = detail.get("citation", {})
    if isinstance(cite, dict):
        parts.append(f"Citation: {cite.get('cite', '')}")

    # Decision date
    decided = detail.get("decided_date", "")
    if decided:
        import datetime
        try:
            dt = datetime.datetime.fromtimestamp(decided)
            parts.append(f"Decided: {dt.strftime('%B %d, %Y')}")
        except Exception:
            pass

    # Votes
    decisions = detail.get("decisions", [])
    if decisions:
        d = decisions[0]
        parts.append(f"Decision: {d.get('decision_type', '')} — "
                    f"{d.get('majority_vote', '')} to {d.get('minority_vote', '')}")
        winning = d.get("winning_party", "")
        if winning:
            parts.append(f"Winning party: {winning}")

    # Facts
    facts = detail.get("facts_of_the_case", "") or detail.get("description", "") or ""
    if facts:
        facts_clean = re.sub(r"<[^>]+>", " ", str(facts))
        facts_clean = re.sub(r"\s+", " ", facts_clean).strip()
        if facts_clean:
            parts.append(f"\nFACTS:\n{facts_clean}")

    # Conclusion
    conclusion = detail.get("conclusion", "") or ""
    if conclusion:
        conc_clean = re.sub(r"<[^>]+>", " ", str(conclusion))
        conc_clean = re.sub(r"\s+", " ", conc_clean).strip()
        if conc_clean:
            parts.append(f"\nCONCLUSION:\n{conc_clean}")

    # Fallback: add citation and name to ensure minimum identity content
    if len("\n".join(parts)) < 200:
        parts.append(f"\nThis case is {detail.get('name', '')} decided by the Supreme Court.")

    # Advocates
    advocates = detail.get("advocates", [])
    if advocates:
        adv_names = [a.get("advocate", {}).get("name", "") for a in advocates if a.get("advocate")]
        if adv_names:
            parts.append(f"\nAdvocates: {', '.join(adv_names)}")

    text = "\n".join(parts)
    return text if len(text) > 200 else None

# ─── Strategy 3: LII by Citation ───────────────────────────────────────────────

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
            # Return raw text for identity verification — caller will extract syllabus
            # This is critical: extract_syllabus_section strips the case name header
            # which contains the party names needed for identity verification
            return text, "courtlistener", cl_id

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

    def try_text(candidate_text, candidate_source, candidate_cl_id=None):
        """Run identity check on retrieved text. Returns (text, source, cl_id) or (None, None, None)."""
        verified = verify_case_identity(case_name, candidate_text, citation)
        if verified is not None:
            # Identity confirmed — now extract syllabus section from CourtListener raw text
            if candidate_source in ('courtlistener', 'courtlistener_excerpt') and len(candidate_text) > 500:
                extracted = extract_syllabus_section(candidate_text)
                if extracted and len(extracted) > 300:
                    return extracted, candidate_source, candidate_cl_id
            return candidate_text, candidate_source, candidate_cl_id
        print(f"    Identity check failed for {candidate_source} — trying next source")
        return None, None, None

    # Strategy 0: Oyez direct URL (known cases + citation-based pre-1956 lookup)
    if not text:
        t, s = fetch_oyez_direct(case_id, case_name, citation)
        if t:
            text, source, cl_id = try_text(t, s)

    # Strategy 1: Registry lookup
    if cl_headers:
        t, s = fetch_by_registry(case_id, cl_headers)
        if t:
            text, source, cl_id = try_text(t, s)

    # Strategy 2: Oyez by citation (structured, authoritative, no auth needed)
    if not text and citation and year:
        volume, page, _ = parse_citation(citation)
        print(f"    Trying Oyez citation: {volume} U.S. {page}")
        t, s = fetch_from_oyez_by_citation(volume, page, year, case_name)
        if t:
            text, source, cl_id = try_text(t, s)

    # Strategy 3: Oyez by name search
    if not text and year:
        print(f"    Trying Oyez name search: {case_name}")
        t, s = fetch_from_oyez_by_name(case_name, year)
        if t:
            text, source, cl_id = try_text(t, s)

    # Strategy 4: LII by citation
    if not text and citation:
        volume, page, _ = parse_citation(citation)
        if volume and page and year and int(year) >= LII_SYLLABUS_CUTOFF:
            t, s = fetch_from_lii(volume, page, session)
            if t:
                text, source, cl_id = try_text(t, s)

    # Strategy 5: CourtListener by citation
    if not text and citation and cl_headers:
        volume, page, _ = parse_citation(citation)
        if volume and page:
            t, s, cid = fetch_cl_by_citation(volume, page, year, cl_headers)
            if t:
                text, source, cl_id = try_text(t, s, cid)

    # Strategy 6: CourtListener by name variants
    if not text and cl_headers:
        t, s, cid = fetch_cl_by_name(case_name, year, cl_headers)
        if t:
            text, source, cl_id = try_text(t, s, cid)

    # Strategy 7: Justia
    if not text:
        volume, page, _ = parse_citation(citation)
        t, s = fetch_from_justia(volume, page, case_name)
        if t:
            text, source, cl_id = try_text(t, s)

    # Strategy 8: Google Scholar
    if not text:
        t, s = fetch_from_google_scholar(case_name, year, citation)
        if t:
            text, source, cl_id = try_text(t, s)

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
    if not text or len(text) < 400:
        # If we get here with thin content it means all strategies returned thin results
        # Save what we have with a warning rather than failing entirely
        print(f"    Warning: thin content ({len(text) if text else 0} chars) — saving anyway")
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
