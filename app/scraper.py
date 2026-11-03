"""
scraper.py — SCI portal scraper with automated CAPTCHA-solving and order extraction.

Flow per check cycle for each case:
  1. GET the case-status page → harvest hidden form fields + CAPTCHA URL
  2. Download CAPTCHA image (same session)
  3. Solve arithmetic CAPTCHA via app.captcha.solve_captcha()
  4. POST to admin-ajax.php with form fields + solution
  5. Parse search results table → extract diary number/year
  6. Query get_case_details (judgement_orders tab) → parse all PDF order URLs & dates
  7. Return list of Order(date, url, label) objects
"""

from __future__ import annotations

import json
import re
import time
import warnings
from typing import NamedTuple

warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*")
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

import requests
from bs4 import BeautifulSoup

from app.captcha import solve_captcha

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://www.sci.gov.in"
FORM_URL = f"{BASE_URL}/case-status-case-no/"
AJAX_URL = f"{BASE_URL}/wp-admin/admin-ajax.php"
CAPTCHA_URL_TEMPLATE = f"{BASE_URL}/?_siwp_captcha&id={{scid}}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_CAPTCHA_RETRIES = 6
REQUEST_TIMEOUT = 25  # seconds


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
class Order(NamedTuple):
    date: str   # e.g. "05-01-2024"
    url: str    # absolute PDF URL or unique identifier string
    label: str  # human-readable label for notifications

    def uid(self) -> str:
        """Stable unique identifier for delta-checking."""
        return f"{self.date}::{self.url}"


# ---------------------------------------------------------------------------
# Case type map
# ---------------------------------------------------------------------------
CASE_TYPES: dict[str, str] = {
    "1":  "SLP(C)",
    "2":  "SLP(Crl.)",
    "3":  "CA",
    "4":  "CrA",
    "5":  "WP(C)",
    "6":  "WP(Crl.)",
    "7":  "TP(C)",
    "8":  "TP(Crl.)",
    "9":  "RP(C)",
    "10": "RP(Crl.)",
    "11": "EP",
    "12": "SMA",
    "13": "MA",
    "14": "Contempt",
    "15": "ARB.P.",
    "16": "OA",
    "17": "LPA",
    "18": "FA",
    "19": "SA",
    "20": "Suo Motu",
}

CASE_TYPE_NAMES: dict[str, str] = {
    "1":  "SPECIAL LEAVE PETITION (CIVIL)",
    "2":  "SPECIAL LEAVE PETITION (CRIMINAL)",
    "3":  "CIVIL APPEAL",
    "4":  "CRIMINAL APPEAL",
    "5":  "WRIT PETITION (CIVIL)",
    "6":  "WRIT PETITION (CRIMINAL)",
    "7":  "TRANSFER PETITION (CIVIL)",
    "8":  "TRANSFER PETITION (CRIMINAL)",
    "9":  "REVIEW PETITION (CIVIL)",
    "10": "REVIEW PETITION (CRIMINAL)",
    "11": "ELECTION PETITION",
    "12": "SPECIAL MISCELLANEOUS APPLICATION",
    "13": "MISCELLANEOUS APPLICATION",
    "14": "CONTEMPT PETITION",
    "15": "ARBITRATION PETITION",
    "16": "ORIGINAL APPLICATION",
    "17": "LETTER PATENT APPEAL",
    "18": "FIRST APPEAL",
    "19": "SECOND APPEAL",
    "20": "SUO MOTU",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _scrape_form_fields(session: requests.Session) -> dict[str, str]:
    """Harvest hidden form inputs and CAPTCHA scid."""
    resp = session.get(FORM_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    html = resp.text

    fields: dict[str, str] = {}

    for m in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.IGNORECASE):
        inp = m.group(0)
        name_m = re.search(r'name=["\']([^"\']+)', inp)
        val_m = re.search(r'value=["\']([^"\']*)', inp)
        if name_m:
            fields[name_m.group(1)] = val_m.group(1) if val_m else ""

    cap_m = re.search(r'\?_siwp_captcha(?:&amp;|&)id=([a-f0-9]+)', html, re.IGNORECASE)
    if cap_m:
        fields["_captcha_scid"] = cap_m.group(1)

    return fields


def _download_captcha(session: requests.Session, scid: str) -> bytes:
    url = CAPTCHA_URL_TEMPLATE.format(scid=scid)
    resp = session.get(
        url,
        headers={"Referer": FORM_URL},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.content


def _post_form(
    session: requests.Session,
    case_type: str,
    case_no: str,
    year: str,
    captcha_value: str,
    form_fields: dict[str, str],
) -> str:
    """Submit case search form via AJAX and return raw response text."""
    payload: dict[str, str] = {}
    for k, v in form_fields.items():
        if not k.startswith("_captcha_"):
            payload[k] = v

    payload["case_type"] = case_type
    payload["case_no"] = case_no
    payload["year"] = year
    payload["siwp_captcha_value"] = captcha_value
    payload.setdefault("es_ajax_request", "1")
    payload["action"] = "get_case_status_case_no"

    resp = session.post(
        AJAX_URL,
        data=payload,
        headers={"Referer": FORM_URL, "X-Requested-With": "XMLHttpRequest"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.text


def _check_captcha_failure(response_text: str) -> bool:
    """Check if the server response indicates a rejected CAPTCHA."""
    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, dict):
            # If server explicitly returned success: true, it's not a captcha failure
            if parsed.get("success") is True:
                return False
            # If success: false, check message
            if parsed.get("success") is False:
                data_val = parsed.get("data", "")
                if isinstance(data_val, str) and "captcha" in data_val.lower():
                    return True
                if isinstance(data_val, dict) and "captcha" in str(data_val).lower():
                    return True
                # Any false response from captcha submission is treated as retryable
                return True
    except Exception:
        pass

    lower = response_text.lower()
    return any(p in lower for p in [
        "incorrect captcha", "invalid captcha", "captcha code entered was incorrect",
        "wrong captcha", "captcha mismatch"
    ])


def _fetch_case_orders(
    session: requests.Session,
    diary_no: str,
    diary_year: str,
) -> list[Order]:
    """
    Fetch the judgement_orders tab for a specific diary number & year.
    Returns list of parsed Order objects.
    """
    orders: list[Order] = []

    # 1. Main get_case_details request to initialize session state
    try:
        session.get(
            AJAX_URL,
            params={
                "action": "get_case_details",
                "diary_no": diary_no,
                "diary_year": diary_year,
                "tab_name": "",
                "es_ajax_request": "1",
            },
            headers={"Referer": FORM_URL, "X-Requested-With": "XMLHttpRequest"},
            timeout=REQUEST_TIMEOUT,
        )
    except Exception:
        pass

    # 2. Query judgement_orders tab
    try:
        resp = session.get(
            AJAX_URL,
            params={
                "action": "get_case_details",
                "diary_no": diary_no,
                "diary_year": diary_year,
                "tab_name": "judgement_orders",
                "es_ajax_request": "1",
            },
            headers={"Referer": FORM_URL, "X-Requested-With": "XMLHttpRequest"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            parsed = json.loads(resp.text)
            orders_html = parsed.get("data", "") if isinstance(parsed, dict) else resp.text
            soup = BeautifulSoup(orders_html, "lxml")

            # Parse each link in the orders table
            for row in soup.find_all("tr"):
                links = row.find_all("a", href=True)
                for a in links:
                    href = a["href"].strip()
                    if ".pdf" in href.lower() or "order" in href.lower() or "judgement" in href.lower():
                        date_str = a.get_text(strip=True)
                        row_text = row.get_text(separator=" ", strip=True)
                        label = f"Order dated {date_str}" if date_str else href.split("/")[-1]
                        if "[" in row_text and "]" in row_text:
                            # e.g. [Judgement - of Main Case ]
                            sub_note = row_text[row_text.find("["):row_text.find("]") + 1]
                            label = f"{label} {sub_note}"
                        orders.append(Order(date=date_str, url=href, label=label))
    except Exception:
        pass

    return orders


def _parse_orders(response_text: str, session: requests.Session | None = None) -> list[Order]:
    """
    Parse AJAX response: extracts diary number and fetches real order PDFs.
    """
    orders: list[Order] = []
    raw_html = response_text

    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, dict):
            data = parsed.get("data", {})
            if isinstance(data, dict):
                raw_html = data.get("resultsHtml", "")
            elif isinstance(data, str):
                raw_html = data
    except Exception:
        pass

    soup = BeautifulSoup(raw_html, "lxml")

    # 1. Look for diary_no and diary_year attributes in table rows
    if session is not None:
        for tr in soup.find_all("tr"):
            d_no = tr.get("data-diary-no")
            d_yr = tr.get("data-diary-year")
            if d_no and d_yr:
                case_orders = _fetch_case_orders(session, str(d_no), str(d_yr))
                orders.extend(case_orders)

    # 2. Check for direct PDF links in resultsHtml as fallback
    if not orders:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().endswith(".pdf"):
                if not href.startswith("http"):
                    href = BASE_URL.rstrip("/") + "/" + href.lstrip("/")
                label = a.get_text(strip=True) or href.split("/")[-1]
                orders.append(Order(date="", url=href, label=label))

    # Deduplicate orders by UID
    seen_uids = set()
    unique: list[Order] = []
    for o in orders:
        if o.uid() not in seen_uids:
            seen_uids.add(o.uid())
            unique.append(o)

    return unique


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_case(
    case_type: str,
    case_no: str,
    year: str,
    log_fn=None,
) -> list[Order]:
    """
    Run one full check cycle for a case.
    Retries CAPTCHA up to MAX_CAPTCHA_RETRIES times.
    """
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    for attempt in range(1, MAX_CAPTCHA_RETRIES + 1):
        session = _make_session()
        try:
            _log(f"    [attempt {attempt}] Fetching form + CAPTCHA…")
            form_fields = _scrape_form_fields(session)
            scid = form_fields.get("_captcha_scid", form_fields.get("scid", ""))

            if not scid:
                _log("    ⚠ Could not retrieve CAPTCHA token. Retrying…")
                time.sleep(2)
                continue

            captcha_bytes = _download_captcha(session, scid)
            captcha_value = solve_captcha(captcha_bytes)

            if not captcha_value:
                _log(f"    ⚠ OCR returned empty answer on attempt {attempt}. Retrying…")
                time.sleep(1)
                continue

            _log(f"    OCR solved: '{captcha_value}'")
            response_text = _post_form(
                session, case_type, case_no, year, captcha_value, form_fields
            )

            if _check_captcha_failure(response_text):
                _log(f"    ⚠ CAPTCHA rejected by portal on attempt {attempt}. Retrying…")
                time.sleep(2)
                continue

            # Parse orders using the active session
            orders = _parse_orders(response_text, session=session)
            _log(f"    ✓ Search accepted. Found {len(orders)} order(s).")
            return orders

        except requests.exceptions.RequestException as exc:
            _log(f"    ✗ Network error on attempt {attempt}: {exc}")
            time.sleep(2)
        except Exception as exc:
            _log(f"    ✗ Unexpected error on attempt {attempt}: {exc}")
            time.sleep(2)

    _log("    ✗ All CAPTCHA attempts exhausted. Will retry next cycle.")
    return []
