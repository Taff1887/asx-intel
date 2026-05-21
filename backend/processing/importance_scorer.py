"""
Importance scoring — 1 (noise) to 10 (market-moving).

Scoring philosophy:
  Price move is the PRIMARY signal — the market votes with money.
  Announcement type is the SECONDARY signal — context for the move.
  Administrative noise is penalised hard.
"""

import logging
import re
from typing import Any

from backend.processing import llm_client

logger = logging.getLogger(__name__)

# Announcement types with score bonuses (secondary to price move)
_TYPE_BONUS = {
    "Guidance Upgrade":           3.0,
    "Guidance Downgrade":         3.5,
    "M&A / Takeover":             4.0,
    "Capital Raising":            1.5,
    "Asset Sale / Acquisition":   2.0,
    "Contract Win":               1.5,
    "Regulatory / Legal":         1.5,
    "Management Change":          1.0,
    "Earnings / Trading Update":  1.5,
    "Exploration / Drilling Results": 1.5,
    "Dividend / Buyback":         1.0,
    "Investor Presentation":      -0.5,
    "Appendix / Administrative":  -3.0,
}

# Keywords that amplify score
_BOOST_KEYWORDS = [
    "guidance upgrade", "guidance downgrade", "material",
    "strategic review", "placement", "capital raising",
    "takeover", "binding agreement", "scheme of arrangement",
    "administration", "insolvency", "suspension", "class action",
    "trading halt", "solvency", "major contract", "transformative",
    "acquisition", "merger", "divest", "asset sale",
]

# Keywords that reduce score
_NOISE_KEYWORDS = [
    "appendix 3y", "appendix 3g", "appendix 2a", "appendix 3b",
    "cleansing notice", "change of registered office", "change of address",
    "director's interest notice", "director interest notice",
    "no change", "in line with",
]


def score_by_rules(text: str, metadata: dict[str, Any], price_move_pct: float | None = None) -> float:
    """
    Compute a rules-based importance score in [1, 10].

    Price move is the primary driver — a 20% move outranks a routine
    capital raise regardless of announcement type.
    """
    ann_type: str = metadata.get("announcement_type", "Other")
    title: str = metadata.get("title", "")
    page_count: int | None = metadata.get("page_count")
    combined = (title + " " + text).lower()

    # ── 1. Price move (primary signal, 0–6 pts) ─────────────────────────
    if price_move_pct is not None:
        move = abs(price_move_pct)
        if move >= 25:
            price_score = 6.0
        elif move >= 15:
            price_score = 5.0
        elif move >= 10:
            price_score = 3.5
        elif move >= 5:
            price_score = 2.0
        elif move >= 2:
            price_score = 0.8
        else:
            price_score = 0.0
    else:
        # No price data yet — start neutral so content signals can rank
        price_score = 0.0

    # ── 2. Announcement type (secondary, −3 to +4 pts) ──────────────────
    type_score = _TYPE_BONUS.get(ann_type, 0.0)

    # ── 3. Keyword scan ──────────────────────────────────────────────────
    kw_score = 0.0
    for kw in _BOOST_KEYWORDS:
        if kw in combined:
            kw_score += 0.4
    for kw in _NOISE_KEYWORDS:
        if kw in combined:
            kw_score -= 0.8

    # ── 4. Page length (longer PDFs tend to be more material) ────────────
    page_score = 0.0
    if page_count:
        if page_count >= 20:
            page_score = 0.5
        elif page_count >= 10:
            page_score = 0.3
        elif page_count <= 1:
            page_score = -0.3

    # ── Combine: baseline 3.0 + all signals ─────────────────────────────
    score = 3.0 + price_score + type_score + kw_score + page_score
    return max(1.0, min(10.0, round(score, 1)))


def score_importance(
    text: str,
    metadata: dict[str, Any],
    price_data: dict[str, Any] | None = None,
    use_llm: bool = True,
) -> tuple[float, str]:
    """
    Return (importance_score, importance_reason).
    Price move is the primary ranking signal.

    use_llm=False forces the fast rule-based score — used by the bulk pipeline.
    The rule-based score is price-driven (exactly the ranking signal we want), so
    skipping the LLM here costs almost nothing but avoids ~800 rate-limited calls
    per pipeline run (score + re-score for every announcement).
    """
    price_move = price_data.get("daily_move_pct") if price_data else None
    rules_score = score_by_rules(text, metadata, price_move)

    if use_llm:
        system = (
            "You are a senior Australian equities analyst. "
            "Score the importance of this ASX announcement from 1 (irrelevant noise) to 10 (major market mover). "
            "The share price move on the day is the most important signal — weight it heavily. "
            "Respond in JSON with exactly two keys: 'score' (number 1-10) and 'reason' (one sentence max). "
            'Example: {"score": 8, "reason": "Stock surged 22% on material guidance upgrade."}'
        )
        price_context = f"\nShare price move today: {price_move:+.1f}%" if price_move is not None else ""
        user = (
            f"Ticker: {metadata.get('ticker')}\n"
            f"Title: {metadata.get('title')}\n"
            f"Type: {metadata.get('announcement_type')}\n"
            f"Sector: {metadata.get('sector')}{price_context}\n\n"
            f"Announcement text (excerpt):\n{text[:2000]}"
        )

        llm_result = llm_client.complete(system, user, max_tokens=150)

        if llm_result:
            import json
            try:
                parsed = json.loads(llm_result)
                score = float(parsed.get("score", rules_score))
                reason = str(parsed.get("reason", ""))
                score = max(1.0, min(10.0, score))
                return round(score, 1), reason
            except Exception:
                logger.debug("Could not parse LLM score response: %s", llm_result)

    # Rules-based fallback reason
    ann_type = metadata.get("announcement_type", "Other")
    if price_move and abs(price_move) >= 10:
        direction = "surged" if price_move > 0 else "fell"
        reason = f"Stock {direction} {abs(price_move):.1f}% — high market impact."
    elif rules_score >= 8:
        reason = f"High-impact {ann_type} with material indicators."
    elif rules_score >= 6:
        reason = f"Moderately important {ann_type}."
    elif rules_score <= 3:
        reason = "Routine administrative announcement with minimal market relevance."
    else:
        reason = f"Standard {ann_type} — monitor for follow-up."

    return rules_score, reason
