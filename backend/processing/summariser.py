"""
LLM-powered announcement summarisation and daily report generation.
Falls back to rule-based extraction when no LLM key is set.
"""

import json
import logging
import re
from datetime import date
from typing import Any

from backend.processing import llm_client
from backend.processing.classifier import classify_announcement
from backend.processing.importance_scorer import score_importance

logger = logging.getLogger(__name__)

_SYSTEM_SUMMARISE = """\
You are an expert Australian equities analyst summarising ASX company announcements.
Your summaries must be accurate, concise, and useful to a professional investor.
Respond in valid JSON only — no markdown fences, no extra text.
"""

_USER_SUMMARISE_TMPL = """\
Ticker: {ticker}
Company: {company}
Sector: {sector}
Announcement type: {ann_type}
Title: {title}
Share price move today: {price_move}

Full announcement text:
{text}

Produce a JSON object with EXACTLY these keys (respond in JSON only):
- "business_overview": one or two plain sentences describing what {company} actually does as a business — its industry, products/services, and stage (e.g. explorer, producer, SaaS). Infer from the announcement and your own knowledge.
- "summary_short": one sentence (max 30 words) summarising what THIS announcement says.
- "summary_detailed": a JSON array of 3-5 concise key points (plain strings, NO bullet symbols) covering the key facts and numbers.
- "why_it_matters": 2 concise, plain-English sentences using simple cause-and-effect. Explain what this announcement means for investors and the most likely reason it moved the share price ({price_move}), tied to the TYPE of announcement. Reasoning-style examples: "A capital raise dilutes existing shareholders and signals the company needs cash, which weighs on the price." / "A successful acquisition could materially lift earnings, supporting the gain." / "A share consolidation simply reduces the number of shares on issue." Commit to ONE explanation that fits the actual move shown — do NOT hedge with "if it rose / if it fell", and do NOT say the move is unknown.
- "key_numbers": a JSON array of the key figures (e.g. "Revenue: $1.2B", "Grade: 2.4 g/t", "390 Wh/kg").
"""


def summarise_announcement(
    text: str,
    metadata: dict[str, Any],
    price_data: dict[str, Any] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Return a dict with: summary_short, summary_detailed, why_it_matters,
    market_impact, key_numbers, risks_caveats.

    use_llm=False forces the fast rule-based path — used by the bulk pipeline so
    it never rate-limits. The real Gemini summaries are generated lazily on click
    via the /announcements/{id}/enrich endpoint (which also downloads the PDF).
    """
    if not use_llm:
        return _rule_based_summary(text, metadata)

    price_move = price_data.get("daily_move_pct") if price_data else None
    price_str = f"{price_move:+.1f}%" if price_move is not None else "unknown"

    user = _USER_SUMMARISE_TMPL.format(
        ticker=metadata.get("ticker", ""),
        company=metadata.get("company_name", ""),
        sector=metadata.get("sector", ""),
        ann_type=metadata.get("announcement_type", ""),
        title=metadata.get("title", ""),
        price_move=price_str,
        text=text[:12000],
    )

    raw = llm_client.complete(_SYSTEM_SUMMARISE, user, max_tokens=1500)

    if raw:
        try:
            return _normalise_summary(json.loads(_strip_fences(raw)))
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON for %s — attempting extraction", metadata.get("ticker"))
            partial = _extract_partial(raw)
            # If we couldn't salvage anything useful, use the rule-based summary
            if partial.get("summary_detailed") or partial.get("summary_short"):
                return _normalise_summary(partial)
            return _rule_based_summary(text, metadata)

    # Fallback — rule-based stub from raw text
    return _rule_based_summary(text, metadata)


def _strip_fences(raw: str) -> str:
    """Strip markdown code fences (```json … ```) that LLMs often add despite instructions."""
    s = raw.strip()
    if s.startswith("```"):
        # Remove opening fence (``` or ```json) and closing fence
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _fix_mojibake(s: str) -> str:
    """Repair UTF-8-decoded-as-latin1 bullet artefacts (e.g. 'â€¢' → '•')."""
    if not isinstance(s, str):
        return s
    if "â€" in s or "Ã" in s:
        try:
            s = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


def _clean_point(s: str) -> str:
    """Strip leading bullet symbols/mojibake and whitespace from a single point."""
    s = _fix_mojibake(str(s)).strip()
    s = re.sub(r"^\s*(?:[•\-\*•]|â€¢)\s*", "", s)
    return s.strip()


def _normalise_summary(d: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise an LLM summary dict so downstream code/UI always gets the expected
    shapes: summary_detailed as a newline-joined bullet string, key_numbers as a
    list, all strings de-mojibaked.
    """
    if not isinstance(d, dict):
        return d

    # summary_detailed: LLMs may return a list of points or a single string
    sd = d.get("summary_detailed")
    if isinstance(sd, list):
        points = [_clean_point(p) for p in sd if str(p).strip()]
        d["summary_detailed"] = "\n".join(f"• {p}" for p in points if p)
    elif isinstance(sd, str):
        lines = [_clean_point(ln) for ln in sd.split("\n") if ln.strip()]
        d["summary_detailed"] = "\n".join(f"• {ln}" for ln in lines if ln)

    # key_numbers: prefer a list
    kn = d.get("key_numbers")
    if isinstance(kn, str):
        d["key_numbers"] = [_fix_mojibake(x.strip()) for x in re.split(r"[;,\n]", kn) if x.strip()]
    elif isinstance(kn, list):
        d["key_numbers"] = [_fix_mojibake(str(x).strip()) for x in kn if str(x).strip()]

    # Scalar prose fields — if the model returned a list of sentences, join with
    # a space (not "; ") so it reads as flowing prose, not "sentence.; sentence".
    for k in ("summary_short", "business_overview", "why_it_matters", "market_impact", "risks_caveats"):
        if isinstance(d.get(k), str):
            d[k] = _fix_mojibake(d[k]).strip()
        elif isinstance(d.get(k), list):
            d[k] = " ".join(_fix_mojibake(str(x).strip()) for x in d[k] if str(x).strip())

    return d


def _extract_partial(raw: str) -> dict[str, Any]:
    """Try to salvage partial JSON or key-value pairs from a malformed LLM response."""
    result: dict[str, Any] = {}
    for key in ["summary_short", "summary_detailed", "why_it_matters", "market_impact", "key_numbers", "risks_caveats"]:
        match = re.search(rf'"{key}"\s*:\s*"([^"]+)"', raw)
        if match:
            result[key] = match.group(1)
    return result


def _rule_based_summary(text: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Rule-based summary. When PDF text is available this produces genuinely useful
    output — pulling real sentences and numbers from the document. Without text it
    falls back to a structured template derived from type + title.
    """
    title    = metadata.get("title", "")
    ticker   = metadata.get("ticker", "")
    company  = metadata.get("company_name", ticker)
    ann_type = metadata.get("announcement_type", "Other")
    sector   = metadata.get("sector", "")

    # ── Extract numbers from title + text ─────────────────────────────────────
    numbers = re.findall(
        r"\$[\d,]+\.?\d*\s*(?:billion|million|bn|m\b)?"
        r"|[\d,]+\.?\d+\s*(?:billion|million|bn|%|per\s?cent|percent|x)",
        title + " " + text[:2000], re.IGNORECASE,
    )
    key_numbers = list(dict.fromkeys(n.strip() for n in numbers[:10] if len(n.strip()) > 1))
    amount_str  = numbers[0] if numbers else ""

    # ── Junk patterns — comprehensive ASX legal/disclaimer/footer text ───────────
    # These sentences come from the standard ASX PDF wrapper and website T&Cs,
    # NOT from the actual announcement content. Any sentence matching is skipped.
    _JUNK = re.compile(
        r"("
        # ASX website / access conditions
        r"general.conditions|asx\.com\.au|constitutes your agreement|"
        r"express written authority|access to (this site|the site)|"
        r"private and personal use|"
        # "You are a member / employed / engaged" — ASX legal category clauses
        r"participating organisation|accessing or aggregating|"
        r"furnishing (that )?information to third|approved representative|"
        r"associated person of the foregoing|"
        r"insurance company, fund or asset manager|"
        r"functions related to trading or investment|"
        # Third-party website disclaimer
        r"embedded hyperlinks|third.party websites?|"
        r"not (under the control of|responsible for the content)|"
        r"licensees or contractors|"
        # General financial/legal boilerplate
        r"commercial purpose|professional or commercial|"
        r"not financial advice|not investment advice|"
        r"forward.looking statement|safe harbour|"
        r"past performance|seek (professional|independent)|consult.*adviser|"
        r"all rights reserved|privacy policy|no reliance|"
        r"information (only|purposes only)|"
        r"this document (is|contains|has been prepared)|"
        r"ABN\s*\d|ACN\s*\d|AFSL\s*\d"
        r")",
        re.IGNORECASE,
    )
    # Sentences starting with these patterns are almost always boilerplate
    _JUNK_START = re.compile(
        r"^("
        r"page\s*\d|"
        r"asx\s|"                                # "ASX announcement …"
        r"you are |"                              # "You are engaged / a member / employed …"
        r"should you wish|"                       # "Should you wish to access …"
        r"company announcements and related|"     # ASX website footer
        r"third.party|"                           # "Third Party Websites …"
        r"real.?time company announcements|"      # ASX website boilerplate
        r"for\s+the\s|"
        r"the\s+information\s+in\s+this|"
        r"this\s+announcement\s+is|"
        r"note\s*:|caution\s*:|"
        r"and\s+|a\s+|an\s+"
        r")",
        re.IGNORECASE,
    )

    # ── Build bullet points from PDF text (if present) ─────────────────────────
    bullets: list[str] = []
    if text and len(text.strip()) > 100:
        # ── Step 1: Find the actual announcement body ──────────────────────────
        # ASX PDFs have a header block (company, date, ASX code) before the
        # announcement title, and sometimes a legal footer after it.
        # Strategy: find where the title appears in the text and take content
        # from there — the body always follows the heading.
        clean_text = text
        if title and len(title) > 10:
            # Match the FULL title with flexible whitespace so line breaks in the
            # PDF don't break the match — and so .end() lands exactly after it
            # (truncating the title would leak the tail of the heading into the body).
            title_pattern = r"\s+".join(re.escape(w) for w in title.split())
            title_match = re.search(title_pattern, text, re.IGNORECASE)
            if title_match:
                clean_text = text[title_match.end():]

        # If title wasn't found (or left us with nothing), skip the first
        # ~15% of the document which is typically the header/disclaimer block
        if len(clean_text.strip()) < 150 and len(text) > 500:
            skip = max(300, len(text) // 7)
            clean_text = text[skip:]

        # ── Step 2: Cut before any trailing ASX disclaimer block ──────────────
        _DISCLAIMER_START = re.compile(
            r"(third.party websites?|asx\.com\.au/legal|general_conditions|"
            r"constitutes your agreement|access to this site|"
            r"this (information|announcement) (has been|is) authorised)",
            re.IGNORECASE,
        )
        cutoff = _DISCLAIMER_START.search(clean_text)
        if cutoff:
            clean_text = clean_text[: cutoff.start()]

        raw_sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", clean_text).strip())
        candidates: list[str] = []
        seen: set[str] = set()
        for s in raw_sentences:
            s = s.strip()
            if (
                35 < len(s) < 400       # not too short (noise) or too long (legal run-on)
                and s not in seen
                and not _JUNK_START.match(s)
                and not _JUNK.search(s)
                and not re.match(r"^\d+\s*$", s)
            ):
                candidates.append(s)
                seen.add(s)

        # Rank candidates by centrality (TextRank) and keep the 5 most
        # representative sentences — far better than just the first 5.
        from backend.processing.extractive import textrank
        bullets = textrank(candidates, top_n=5)

    # ── Short summary ──────────────────────────────────────────────────────────
    if bullets:
        short = bullets[0][:300]
    else:
        templates = {
            "Capital Raising": (
                f"{company} is raising capital" + (f" of {amount_str}" if amount_str else "") + f". {title}."
            ),
            "Earnings / Trading Update": f"{company} has released a trading update: {title}.",
            "Dividend / Buyback":        f"{company} has announced a dividend or share buyback: {title}.",
            "M&A / Takeover":            f"{company} has announced M&A activity" + (f" of {amount_str}" if amount_str else "") + f": {title}.",
            "Exploration / Drilling Results": f"{company} has released exploration/drilling results: {title}.",
            "Management Change":         f"{company} has announced a management change: {title}.",
            "Guidance Downgrade":        f"{company} has revised guidance downward: {title}.",
            "Guidance Upgrade":          f"{company} has upgraded guidance: {title}.",
            "Contract Win":              f"{company} has won a contract" + (f" worth {amount_str}" if amount_str else "") + f": {title}.",
            "Regulatory / Legal":        f"{company} has a regulatory or legal update: {title}.",
        }
        short = templates.get(ann_type, f"{company} ({ticker}): {title}.")[:300]

    # ── Detailed bullets ───────────────────────────────────────────────────────
    if bullets:
        detailed = "\n".join(f"• {b}" for b in bullets)
    else:
        # At minimum give type + sector context
        detailed = f"• {title}"
        if ann_type and ann_type != "Other":
            detailed += f"\n• Announcement type: {ann_type}"
        if sector:
            detailed += f"\n• Sector: {sector}"
        if key_numbers:
            detailed += f"\n• Key figures: {', '.join(key_numbers[:4])}"

    # ── Why it matters ─────────────────────────────────────────────────────────
    why_map = {
        "Capital Raising":              f"New capital may fund growth but dilutes existing shareholders in {company}.",
        "Earnings / Trading Update":    f"Financial performance directly drives {company}'s valuation and market expectations.",
        "M&A / Takeover":               f"M&A activity is a major catalyst — investors will reassess {company}'s strategic direction.",
        "Exploration / Drilling Results": f"Drill results are critical value catalysts for resource companies like {company}.",
        "Guidance Downgrade":           f"Lowered guidance from {company} signals weaker-than-expected performance ahead.",
        "Guidance Upgrade":             f"Upgraded guidance from {company} signals stronger earnings momentum.",
        "Contract Win":                 f"New contract revenue adds earnings visibility and de-risks {company}'s outlook.",
        "Dividend / Buyback":           f"Capital returns signal management confidence in {company}'s balance sheet.",
        "Regulatory / Legal":           f"Regulatory outcomes can materially affect {company}'s operations and risk profile.",
        "Management Change":            f"Leadership changes can shift strategic direction and investor confidence in {company}.",
    }
    why = why_map.get(ann_type, f"{company} ({ticker}) made this announcement — monitor for follow-up market reaction.")

    return {
        "summary_short":    short,
        "summary_detailed": detailed,
        "why_it_matters":   why,
        "market_impact":    "",
        "key_numbers":      key_numbers,
        "risks_caveats":    "",
    }


_SYSTEM_DAILY_REPORT = """\
You are a senior Australian equities strategist writing a daily market wrap for a professional hedge fund.
Be analytical, specific, and concise. Respond in valid JSON only.
"""


def generate_daily_report(
    report_date: date,
    announcements: list[dict[str, Any]],
    price_movers: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Generate the daily market intelligence report.

    announcements: list of dicts with announcement metadata + summary fields
    price_movers: list of {ticker, company_name, daily_move_pct, sector, ...}
    """
    ann_summary = json.dumps(
        [
            {
                "ticker": a.get("ticker"),
                "company": a.get("company_name"),
                "type": a.get("announcement_type"),
                "importance": a.get("importance_score"),
                "title": a.get("title"),
                "summary": a.get("summary_short"),
                "why_it_matters": a.get("why_it_matters"),
                "price_move": a.get("price_move_pct"),
            }
            for a in announcements[:30]
        ],
        indent=2,
    )

    movers_summary = json.dumps(
        [
            {
                "ticker": m.get("ticker"),
                "company": m.get("company_name"),
                "move_pct": m.get("daily_move_pct"),
                "sector": m.get("sector"),
            }
            for m in price_movers[:20]
        ],
        indent=2,
    )

    user = f"""\
Date: {report_date.strftime("%A, %d %B %Y")}

Top announcements (sorted by importance):
{ann_summary}

Top price movers:
{movers_summary}

Produce a JSON object with these keys:
- "executive_summary": 2-3 paragraph narrative of today's most important market developments
- "top_announcements": list of 5 most important items, each with "ticker", "headline", "why_it_matters"
- "sector_themes": dict mapping sector names to 1-2 sentence theme descriptions
- "unusual_moves": describe any large price moves without obvious announcements
- "watchlist_tomorrow": list of 3-5 tickers/themes to watch tomorrow and why
"""

    raw = llm_client.complete(_SYSTEM_DAILY_REPORT, user, max_tokens=1500)

    if raw:
        try:
            return json.loads(_strip_fences(raw))
        except json.JSONDecodeError:
            logger.warning("Daily report LLM response not valid JSON — returning raw text")
            return {"full_report_text": raw}

    # Fallback — structured stub
    top5 = sorted(announcements, key=lambda x: x.get("importance_score") or 0, reverse=True)[:5]
    top_movers_str = ", ".join(
        f"{m['ticker']} ({m['daily_move_pct']:+.1f}%)"
        for m in price_movers[:5]
        if m.get("daily_move_pct") is not None
    )

    return {
        "executive_summary": (
            f"Daily ASX market wrap for {report_date.strftime('%d %B %Y')}. "
            f"Top price movers: {top_movers_str or 'data not yet available'}. "
            "Configure LLM (OPENAI_API_KEY or ANTHROPIC_API_KEY) for full narrative."
        ),
        "top_announcements": [
            {"ticker": a["ticker"], "headline": a["title"], "why_it_matters": a.get("why_it_matters", "")}
            for a in top5
        ],
        "sector_themes": {},
        "unusual_moves": "LLM not configured.",
        "watchlist_tomorrow": [],
    }
