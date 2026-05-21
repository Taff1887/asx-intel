"""
Realistic mock ASX announcements for local development and testing.
Used automatically when the real ASX client is not yet wired in.
"""

from datetime import date, datetime, timedelta
from typing import Any


MOCK_ANNOUNCEMENTS: list[dict[str, Any]] = [
    {
        "ticker": "BHP",
        "company_name": "BHP Group Limited",
        "title": "BHP Q3 FY2026 Operational Review",
        "announcement_datetime": None,  # filled at runtime
        "announcement_type": "Earnings / Trading Update",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_bhp_q3.pdf",
        "page_count": 24,
        "raw_text": (
            "BHP Group Limited Q3 FY2026 Operational Review. "
            "Iron ore production of 68.4Mt for the quarter was 4% above the prior corresponding period. "
            "Copper production of 473kt was in line with guidance. "
            "FY2026 iron ore production guidance maintained at 255-265Mt. "
            "Unit costs remain well-controlled. The Board reaffirmed its commitment to the progressive dividend policy. "
            "CEO Mike Henry commented: 'Our operations continue to deliver reliable, low-cost production.'"
        ),
    },
    {
        "ticker": "CBA",
        "company_name": "Commonwealth Bank of Australia",
        "title": "CBA announces $2.0 billion off-market share buy-back",
        "announcement_datetime": None,
        "announcement_type": "Dividend / Buyback",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_cba_buyback.pdf",
        "page_count": 8,
        "raw_text": (
            "Commonwealth Bank of Australia announces a $2.0 billion off-market share buy-back. "
            "The buy-back will be conducted at a 14% discount to the market price. "
            "Shareholders with fewer than 200 shares are not eligible. "
            "The buy-back represents approximately 0.9% of shares on issue. "
            "CBA's CET1 ratio of 12.4% remains well above APRA's minimum requirements. "
            "The buy-back reflects CBA's strong capital position and commitment to returning excess capital."
        ),
    },
    {
        "ticker": "PLS",
        "company_name": "Pilbara Minerals Limited",
        "title": "Guidance downgrade — FY2026 spodumene production revised lower",
        "announcement_datetime": None,
        "announcement_type": "Guidance Downgrade",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_pls_guidance.pdf",
        "page_count": 5,
        "raw_text": (
            "Pilbara Minerals revises FY2026 spodumene concentrate production guidance to 620,000-660,000 dmt, "
            "down from 680,000-720,000 dmt previously. "
            "The revision reflects slower-than-expected ramp-up at the P680 expansion project. "
            "Unit operating costs are expected to be at the upper end of guidance of A$640-680/dmt. "
            "Realised prices remain under pressure given weak lithium market conditions. "
            "The company maintains a strong balance sheet with A$1.2 billion in cash. "
            "CEO Dale Henderson noted the market environment remains challenging."
        ),
    },
    {
        "ticker": "WDS",
        "company_name": "Woodside Energy Group Ltd",
        "title": "Woodside enters binding agreement to acquire Louisiana LNG project stake",
        "announcement_datetime": None,
        "announcement_type": "M&A / Takeover",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_wds_acquisition.pdf",
        "page_count": 32,
        "raw_text": (
            "Woodside Energy Group has entered into a binding agreement to acquire a 40% working interest "
            "in the Louisiana LNG project from Venture Global LNG for a consideration of US$2.35 billion. "
            "The transaction is subject to customary regulatory approvals and is expected to close in Q4 2026. "
            "The acquisition will add approximately 2.5 mtpa of LNG capacity to Woodside's global portfolio. "
            "The project has secured long-term offtake agreements with major Asian buyers. "
            "Woodside will fund the acquisition through existing liquidity and new debt facilities. "
            "CEO Meg O'Neill described the deal as 'strategically transformative for Woodside's LNG growth strategy.'"
        ),
    },
    {
        "ticker": "FMG",
        "company_name": "Fortescue Ltd",
        "title": "Fortescue announces strategic review of green energy division",
        "announcement_datetime": None,
        "announcement_type": "Earnings / Trading Update",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_fmg_review.pdf",
        "page_count": 12,
        "raw_text": (
            "Fortescue announces a strategic review of its Fortescue Energy green energy division. "
            "The review will assess all options for the division including potential asset sales, "
            "joint ventures, and restructuring. The company has engaged Goldman Sachs as financial adviser. "
            "Fortescue Energy has invested approximately US$4 billion since inception with limited revenue. "
            "Iron ore shipments for Q3 FY2026 were 47.8Mt, 2% below guidance. "
            "All-in cash cost was US$18.92/wmt, slightly above guidance of US$18.50-19.50/wmt. "
            "The Board is targeting significant cost reductions across the business."
        ),
    },
    {
        "ticker": "REA",
        "company_name": "REA Group Ltd",
        "title": "REA Group — FY2026 Q3 Operational Update",
        "announcement_datetime": None,
        "announcement_type": "Earnings / Trading Update",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_rea_update.pdf",
        "page_count": 10,
        "raw_text": (
            "REA Group Q3 FY2026 operational update. "
            "Australian residential listings grew 9% year-on-year in Q3. "
            "Core digital revenue increased 16% driven by depth product upgrades. "
            "India operations (PropTiger/Housing.com) contributed A$48M revenue, up 21%. "
            "FY2026 guidance reaffirmed for double-digit revenue and EBITDA growth. "
            "CEO Owen Wilson commented the property market remains resilient despite interest rate uncertainty."
        ),
    },
    {
        "ticker": "NXT",
        "company_name": "NEXTDC Limited",
        "title": "NEXTDC raises $1.0 billion via institutional placement",
        "announcement_datetime": None,
        "announcement_type": "Capital Raising",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_nxt_placement.pdf",
        "page_count": 15,
        "raw_text": (
            "NEXTDC Limited announces a $1.0 billion fully underwritten institutional placement "
            "at $16.50 per share, representing a 7.2% discount to the last close of $17.78. "
            "Proceeds will be used to fund expansion of S4 Sydney and M3 Melbourne data centres "
            "and to strengthen the balance sheet for future growth opportunities. "
            "The company also announces a $100 million share purchase plan for retail shareholders at the same price. "
            "Total data centre capacity will increase to 450MW on completion of current development pipeline. "
            "CEO Craig Scroggie noted strong demand from hyperscale and enterprise customers."
        ),
    },
    {
        "ticker": "TWE",
        "company_name": "Treasury Wine Estates Ltd",
        "title": "Change of CEO — effective 1 July 2026",
        "announcement_datetime": None,
        "announcement_type": "Management Change",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_twe_ceo.pdf",
        "page_count": 3,
        "raw_text": (
            "Treasury Wine Estates announces that CEO Tim Ford will retire on 30 June 2026 after 14 years with the company. "
            "The Board has appointed Sarah Mitchell as CEO effective 1 July 2026. "
            "Ms Mitchell joins from Diageo plc where she served as President, North America. "
            "Tim Ford will assist with the transition until 31 August 2026. "
            "Chairman Paul Rayner thanked Tim Ford for his outstanding contribution to the company."
        ),
    },
    {
        "ticker": "MIN",
        "company_name": "Mineral Resources Limited",
        "title": "Appendix 3Y — Change of Director's Interest Notice",
        "announcement_datetime": None,
        "announcement_type": "Appendix / Administrative",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_min_3y.pdf",
        "page_count": 2,
        "raw_text": (
            "Appendix 3Y — Change of Director's Interest Notice. "
            "Director: Chris Ellison. "
            "Date of change: 13 May 2026. "
            "Nature of change: On-market purchase of 50,000 ordinary shares at $34.20 per share. "
            "Total shares held (direct): 145,200,000. Total shares held (indirect): 22,500,000."
        ),
    },
    {
        "ticker": "RIO",
        "company_name": "Rio Tinto Limited",
        "title": "Rio Tinto wins binding contract to supply lithium to Toyota battery JV",
        "announcement_datetime": None,
        "announcement_type": "Contract Win",
        "source_url": "https://www.asx.com.au/asxpdf/20260514/pdf/example_rio_contract.pdf",
        "page_count": 7,
        "raw_text": (
            "Rio Tinto has entered into a binding long-term supply agreement with Prime Planet Energy & Solutions (PPES), "
            "a joint venture between Toyota and Panasonic, to supply battery-grade lithium carbonate from the "
            "Rincon lithium project in Argentina. "
            "The agreement covers supply of up to 10,000 tonnes per annum of lithium carbonate equivalent "
            "commencing in calendar year 2027. "
            "The contract represents a material revenue opportunity and validates Rincon's strategic importance. "
            "CEO Jakob Stausholm described the agreement as a key milestone in Rio Tinto's battery materials strategy."
        ),
    },
]


def get_mock_announcements(target_date: date) -> list[dict[str, Any]]:
    """Return mock announcements with datetimes set to the target date."""
    results = []
    base_time = datetime(target_date.year, target_date.month, target_date.day, 9, 0, 0)

    for i, ann in enumerate(MOCK_ANNOUNCEMENTS):
        entry = ann.copy()
        # Spread announcements across the trading day (9am – 4pm AEST)
        entry["announcement_datetime"] = base_time + timedelta(minutes=i * 40)
        results.append(entry)

    return results
