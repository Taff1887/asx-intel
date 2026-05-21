"""
Real ASX announcement client.

Data source:
  ASX Today's Announcements page (HTML, scraped):
    https://www.asx.com.au/asx/v2/statistics/todayAnns.do
    https://www.asx.com.au/asx/v2/statistics/prevBusDayAnns.do

  Returns all announcements for the day in a single HTML page — no per-ticker
  looping required. Scraped with BeautifulSoup.

Company names are resolved from the ASX Listed Companies CSV:
  https://www.asx.com.au/asx/research/ASXListedCompanies.csv

*** SWAP-OUT POINT ***
  Replace fetch_announcements_for_date() to use a paid provider
  (Refinitiv, Bloomberg, Iress) without changing anything else.
"""

import csv
import io
import logging
import re
import time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

ASX_TODAY_URL = "https://www.asx.com.au/asx/v2/statistics/todayAnns.do"
ASX_PREV_URL  = "https://www.asx.com.au/asx/v2/statistics/prevBusDayAnns.do"
ASX_PDF_BASE  = "https://www.asx.com.au"
ASX_COMPANY_LIST_URL = "https://www.asx.com.au/asx/research/ASXListedCompanies.csv"

REQUEST_TIMEOUT = 30

_CACHE_DIR = Path(__file__).parent.parent.parent / "data"
_COMPANY_CACHE_FILE = _CACHE_DIR / "asx_companies_cache.csv"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.asx.com.au/",
}


# ---------------------------------------------------------------------------
# Company list (for name + sector lookup)
# ---------------------------------------------------------------------------

def get_asx_company_list(force_refresh: bool = False) -> list[dict[str, str]]:
    """Return {ticker, name, gics_group} for all ASX-listed companies. Cached daily."""
    _CACHE_DIR.mkdir(exist_ok=True)

    if not force_refresh and _COMPANY_CACHE_FILE.exists():
        mtime = datetime.fromtimestamp(_COMPANY_CACHE_FILE.stat().st_mtime).date()
        if mtime == date.today():
            return _read_company_cache()

    logger.info("Downloading ASX company list from %s", ASX_COMPANY_LIST_URL)
    try:
        with httpx.Client(timeout=30, headers=_HEADERS) as client:
            resp = client.get(ASX_COMPANY_LIST_URL)
            resp.raise_for_status()
            content = resp.text

        companies = _parse_company_csv(content)
        _write_company_cache(companies)
        logger.info("Downloaded %d ASX-listed companies", len(companies))
        return companies

    except Exception as exc:
        logger.error("Failed to download company list: %s", exc)
        if _COMPANY_CACHE_FILE.exists():
            logger.info("Falling back to cached company list")
            return _read_company_cache()
        raise


def _parse_company_csv(content: str) -> list[dict[str, str]]:
    """Parse the ASX Listed Companies CSV.

    Format: Company name (col 0), ASX code (col 1), GICS industry group (col 2)
    """
    companies = []
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    # Find the header row — look for the row containing "ASX code"
    header_idx = 0
    name_col, ticker_col, gics_col = 0, 1, 2

    for i, row in enumerate(rows):
        if not row:
            continue
        cols = [c.strip().lower() for c in row]
        if "asx code" in cols:
            header_idx = i
            ticker_col = cols.index("asx code")
            name_col = cols.index("company name") if "company name" in cols else (1 - ticker_col)
            gics_col = next((j for j, c in enumerate(cols) if "gics" in c), 2)
            break

    for row in rows[header_idx + 1:]:
        if len(row) <= ticker_col or not row[ticker_col].strip():
            continue
        companies.append({
            "ticker": row[ticker_col].strip().upper(),
            "name": row[name_col].strip() if len(row) > name_col else "",
            "gics_group": row[gics_col].strip() if len(row) > gics_col else "",
        })

    return companies


def _write_company_cache(companies: list[dict[str, str]]) -> None:
    with open(_COMPANY_CACHE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker", "name", "gics_group"])
        writer.writeheader()
        writer.writerows(companies)


def _read_company_cache() -> list[dict[str, str]]:
    companies = []
    with open(_COMPANY_CACHE_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append(dict(row))
    return companies


# ---------------------------------------------------------------------------
# Announcement fetching — single bulk HTML page
# ---------------------------------------------------------------------------

def fetch_announcements_for_date(target_date: date) -> list[dict[str, Any]]:
    """
    Fetch all ASX announcements for a given date by scraping the bulk
    today/prevBusDay HTML page. Returns list of announcement dicts.
    """
    import pytz
    AEST = pytz.timezone("Australia/Sydney")
    today_aest = datetime.now(AEST).date()

    # Build a ticker→name lookup from the company list
    try:
        companies = get_asx_company_list()
        name_map = {c["ticker"]: c["name"] for c in companies}
        sector_map = {c["ticker"]: c["gics_group"] for c in companies}
    except Exception:
        name_map = {}
        sector_map = {}

    # Choose the right URL
    if target_date == today_aest:
        url = ASX_TODAY_URL
    elif target_date == _prev_trading_day(today_aest):
        url = ASX_PREV_URL
    else:
        # For older dates fall back to the search page
        url = f"https://www.asx.com.au/asx/v2/statistics/announcements.do?by=date&fromDate={target_date.strftime('%d/%m/%Y')}&toDate={target_date.strftime('%d/%m/%Y')}"

    logger.info("Fetching announcements from %s", url)

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.error("Failed to fetch announcements page: %s", exc)
        return []

    announcements = _parse_announcements_html(html, target_date, name_map, sector_map)
    logger.info("Parsed %d announcements for %s", len(announcements), target_date)
    return announcements


def _prev_trading_day(d: date) -> date:
    """Return the previous weekday (simple — doesn't account for holidays)."""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


def _parse_announcements_html(
    html: str,
    target_date: date,
    name_map: dict[str, str],
    sector_map: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Parse the ASX todayAnns.do HTML table.

    Actual column structure (verified from live HTML):
      td[0] = ticker         e.g. "POL"
      td[1] = date + time    "14/05/2026<br/><span class='dates-time'>7:31 pm</span>"
      td[2] = price sens     empty td OR td.pricesens with <img>
      td[3] = headline       <a href="...">Title<br/><img/><span class='page'>3 pages</span></a>
    """
    soup = BeautifulSoup(html, "lxml")
    results = []

    table = soup.find("table")
    if not table:
        logger.warning("No table found in ASX announcements HTML")
        return []

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        ticker = cells[0].get_text(strip=True).upper()
        if not ticker or len(ticker) > 5 or not ticker.isalpha():
            continue

        # Date cell: get the plain date text and time separately
        date_part = cells[1].contents[0].strip() if cells[1].contents else ""
        time_span = cells[1].find("span", class_="dates-time")
        time_part = time_span.get_text(strip=True) if time_span else ""
        ann_dt = _parse_asx_datetime(f"{date_part} {time_part}".strip())
        if ann_dt is None or ann_dt.date() != target_date:
            continue

        # Price sensitivity: pricesens class or img with title="price sensitive"
        price_sensitive = "pricesens" in cells[2].get("class", []) or bool(
            cells[2].find("img", title=lambda t: t and "price" in t.lower())
        )

        # Headline: first text node in the <a> tag (before the <br/>)
        link = cells[3].find("a")
        if not link:
            continue
        # Get just the announcement title — first NavigableString child of <a>
        title = ""
        for child in link.children:
            from bs4 import NavigableString
            if isinstance(child, NavigableString):
                t = child.strip()
                if t:
                    title = t
                    break
        if not title:
            title = link.get_text(" ", strip=True).split("  ")[0].strip()

        href = link.get("href", "")
        source_url = (ASX_PDF_BASE + href) if href.startswith("/") else href

        # Page count from <span class="page">3 pages</span>
        page_count = None
        page_span = link.find("span", class_="page")
        if page_span:
            try:
                page_count = int(page_span.get_text(strip=True).split()[0])
            except (ValueError, IndexError):
                pass

        if not title:
            continue

        results.append({
            "ticker": ticker,
            "company_name": name_map.get(ticker, ticker),
            "sector": sector_map.get(ticker, ""),
            "title": title,
            "announcement_datetime": ann_dt,
            "announcement_type": None,
            "source_url": source_url,
            "page_count": page_count,
            "market_sensitive": price_sensitive,
            "raw_text": "",
        })

    return results


def _parse_asx_datetime(dt_str: str) -> datetime | None:
    """Parse ASX datetime strings like '14/05/2026 7:31 pm'."""
    if not dt_str:
        return None
    import pytz
    AEST = pytz.timezone("Australia/Sydney")
    for fmt in ("%d/%m/%Y %I:%M %p", "%d/%m/%Y %H:%M"):
        try:
            naive = datetime.strptime(dt_str, fmt)
            return AEST.localize(naive)
        except ValueError:
            continue
    return None


def _extract_real_pdf_url(html: str) -> str | None:
    """
    The ASX displayAnnouncement.do URL returns a terms-acceptance page, not the
    PDF. That page embeds the real PDF location in a hidden field:
        <input name="pdfURL" value="https://announcements.asx.com.au/.../x.pdf">
    Pull it out so we can fetch the actual document.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
        inp = soup.find("input", attrs={"name": "pdfURL"})
        if inp and inp.get("value"):
            return inp["value"].strip()
    except Exception:
        pass
    # Regex fallback
    m = re.search(r'name=["\']pdfURL["\']\s+value=["\']([^"\']+)["\']', html, re.I)
    if not m:
        m = re.search(r'value=["\']([^"\']+\.pdf)["\']', html, re.I)
    return m.group(1).strip() if m else None


def fetch_announcement_document(source_url: str) -> bytes | None:
    """
    Download the raw PDF bytes of an announcement. Returns None on failure.

    ASX serves announcement PDFs behind a terms-acceptance page: the
    displayAnnouncement.do URL returns HTML (the "Agree and proceed" page) with
    the real PDF URL in a hidden 'pdfURL' field. We detect that and follow
    through to fetch the actual PDF.
    """
    if not source_url:
        return None
    try:
        with httpx.Client(timeout=30, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(source_url)
            resp.raise_for_status()
            content = resp.content

            # Direct PDF — done
            if content[:5] == b"%PDF":
                return content

            # Terms-acceptance HTML page — extract the real PDF URL and fetch it
            ctype = resp.headers.get("content-type", "").lower()
            looks_html = "html" in ctype or content[:64].lstrip().lower().startswith(b"<html")
            if looks_html:
                real_url = _extract_real_pdf_url(resp.text)
                if real_url:
                    logger.info("Following ASX terms page → real PDF: %s", real_url)
                    pdf_resp = client.get(real_url)
                    pdf_resp.raise_for_status()
                    return pdf_resp.content

            # Fallback — return whatever we got (HTML parser will try its best)
            return content
    except Exception as exc:
        logger.warning("Failed to download %s: %s", source_url, exc)
        return None
