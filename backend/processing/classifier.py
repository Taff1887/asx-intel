"""
Announcement type classification — rules-based with optional LLM refinement.
"""

import re
import logging
from typing import Any

from backend.processing import llm_client

logger = logging.getLogger(__name__)

ANNOUNCEMENT_TYPES = [
    "Earnings / Trading Update",
    "Guidance Upgrade",
    "Guidance Downgrade",
    "Capital Raising",
    "M&A / Takeover",
    "Asset Sale / Acquisition",
    "Contract Win",
    "Regulatory / Legal",
    "Management Change",
    "Exploration / Drilling Results",
    "Investor Presentation",
    "Appendix / Administrative",
    "Dividend / Buyback",
    "Other",
]

# Simple keyword → type mapping for rules-based pass
_KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["guidance upgrade", "raises guidance", "upgraded guidance", "increases guidance"], "Guidance Upgrade"),
    (["guidance downgrade", "lowers guidance", "revised lower", "reduces guidance", "downgrade"], "Guidance Downgrade"),
    (["placement", "entitlement offer", "capital raising", "share purchase plan", "spp", "rights issue", "equity raise"], "Capital Raising"),
    (["takeover", "scheme of arrangement", "binding agreement to acquire", "merger", "m&a", "off-market takeover bid"], "M&A / Takeover"),
    (["asset sale", "divest", "disposal", "sells its", "binding agreement to sell"], "Asset Sale / Acquisition"),
    (["contract win", "awarded contract", "binding agreement", "mandate awarded", "awarded the", "purchase order"], "Contract Win"),
    (["regulatory", "legal proceedings", "class action", "investigation", "asic", "accc", "compliance", "breach"], "Regulatory / Legal"),
    (["ceo resignation", "ceo appointment", "managing director appointment", "director appointment", "change of ceo", "new ceo", "appointed as"], "Management Change"),
    (["drilling results", "assay results", "exploration update", "mineral resource", "ore reserve", "scoping study"], "Exploration / Drilling Results"),
    (["investor presentation", "investor day", "roadshow"], "Investor Presentation"),
    (["appendix 3y", "appendix 3g", "appendix 2a", "appendix 3b", "change of registered office", "cleansing notice", "director interest notice"], "Appendix / Administrative"),
    (["dividend", "buy-back", "buyback", "special dividend", "interim dividend", "final dividend"], "Dividend / Buyback"),
    (["quarterly report", "q1", "q2", "q3", "q4", "half year", "half-year", "full year", "annual results", "trading update", "operational review"], "Earnings / Trading Update"),
]


def classify_by_rules(title: str, text: str) -> str:
    """Fast keyword-based classification."""
    combined = (title + " " + text).lower()
    for keywords, ann_type in _KEYWORD_RULES:
        if any(kw in combined for kw in keywords):
            return ann_type
    return "Other"


def classify_announcement(text: str, metadata: dict[str, Any], use_llm: bool = True) -> str:
    """
    Classify announcement type.
    Uses rules first; falls back to LLM if result is 'Other' and LLM is available.

    use_llm=False skips the LLM fallback entirely (rules only) — used by the bulk
    pipeline so it stays fast and never rate-limits.
    """
    title = metadata.get("title", "")
    rules_result = classify_by_rules(title, text)

    if rules_result != "Other" or not use_llm:
        return rules_result

    # Try LLM for ambiguous cases
    system = (
        "You are an expert in ASX company announcements. "
        "Classify the announcement into exactly one of these types:\n"
        + "\n".join(f"- {t}" for t in ANNOUNCEMENT_TYPES)
        + "\n\nRespond with only the type name, nothing else."
    )
    user = f"Announcement title: {title}\n\nText excerpt:\n{text[:1500]}"

    result = llm_client.complete(system, user, max_tokens=50)
    result = result.strip()

    if result in ANNOUNCEMENT_TYPES:
        return result

    logger.debug("LLM returned unrecognised type '%s', defaulting to 'Other'", result)
    return "Other"
