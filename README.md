# ASX Intel

Daily ASX announcement intelligence platform. Ingests, summarises, classifies, and ranks ASX company announcements every trading day. Links announcements to share price movements and produces a daily written market wrap.

---

## Project structure

```
asx_intel/
├── backend/
│   ├── main.py                      # FastAPI app
│   ├── database.py                  # SQLite via SQLAlchemy
│   ├── models.py                    # ORM: announcements, companies, sectors, prices, reports
│   ├── schemas.py                   # Pydantic response schemas
│   ├── api/
│   │   ├── announcements.py         # GET /announcements, GET /announcements/{id}
│   │   ├── companies.py             # GET /companies, GET /companies/{ticker}
│   │   ├── sectors.py               # GET /sectors, GET /sectors/{name}/announcements
│   │   └── reports.py               # POST /ingest, /summarise, /fetch-prices, /generate-daily-report
│   ├── ingestion/
│   │   ├── asx_client.py            # *** PLUG-IN POINT for real ASX data source ***
│   │   ├── announcement_ingestor.py # Orchestrates fetch → parse → save
│   │   ├── pdf_parser.py            # PDF/HTML text extraction
│   │   └── mock_data.py             # 10 realistic demo announcements
│   ├── processing/
│   │   ├── llm_client.py            # OpenAI / Anthropic wrapper
│   │   ├── classifier.py            # Rules + LLM announcement type classification
│   │   ├── importance_scorer.py     # Rules + LLM importance score (1–10)
│   │   └── summariser.py            # LLM summaries + daily report generator
│   └── market/
│       └── price_fetcher.py         # yfinance OHLCV + volume spike + benchmark
├── frontend/                        # Next.js 14 + Tailwind CSS
│   ├── app/
│   │   ├── page.tsx                 # Daily dashboard
│   │   ├── announcements/page.tsx   # Searchable/filterable table
│   │   ├── announcement/[id]/       # Full announcement detail
│   │   ├── company/[ticker]/        # Company page + price history
│   │   ├── sector/[name]/           # Sector page grouped by type
│   │   └── sectors/page.tsx         # Sectors index
│   ├── components/                  # ImportanceBadge, PriceMove, TypeBadge, NavBar
│   └── lib/api.ts                   # Typed API client
├── scripts/
│   ├── run_daily_ingestion.py       # Full daily pipeline (CLI)
│   └── backfill.py                  # Historical backfill across date range
├── data/                            # SQLite database (gitignored)
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Install backend dependencies

```bash
cd asx-intel

# With pip
pip install -r requirements.txt

# Or with uv (recommended in this repo)
uv pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — add your OPENAI_API_KEY or ANTHROPIC_API_KEY
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## Running locally

### Backend (port 8000)

```bash
# From the repo root (asx-intel/)
uvicorn backend.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend (port 3001)

```bash
cd frontend
npm run dev
```

Dashboard: http://localhost:3001

---

## Daily ingestion

### One command to run everything (ingest → prices → summarise → report):

```bash
# Today's data with mock announcements (works without ASX source wired in)
python scripts/run_daily_ingestion.py --mock

# Specific date
python scripts/run_daily_ingestion.py --date 2026-05-14 --mock

# When real ASX source is wired in:
python scripts/run_daily_ingestion.py --date 2026-05-14
```

### Backfill a date range:

```bash
python scripts/backfill.py --start 2026-01-01 --end 2026-05-14 --mock
```

### Via API (after starting the backend):

```bash
# Ingest
curl -X POST "http://localhost:8000/ingest?mock=true"

# Fetch prices
curl -X POST "http://localhost:8000/fetch-prices"

# Summarise
curl -X POST "http://localhost:8000/summarise"

# Generate daily report
curl -X POST "http://localhost:8000/generate-daily-report"
```

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/announcements` | List announcements (filters: date, ticker, sector, type, importance, search) |
| GET | `/announcements/{id}` | Full announcement detail |
| GET | `/daily-report?date=YYYY-MM-DD` | Daily report |
| GET | `/companies` | List companies |
| GET | `/companies/{ticker}` | Company detail |
| GET | `/companies/{ticker}/announcements` | Company announcements |
| GET | `/companies/{ticker}/prices` | Company price history |
| GET | `/sectors` | List sectors |
| GET | `/sectors/{name}/announcements` | Sector announcements |
| POST | `/ingest?date=&mock=` | Trigger announcement ingestion |
| POST | `/fetch-prices?date=` | Fetch + save share prices |
| POST | `/summarise?date=` | Run LLM summarisation |
| POST | `/generate-daily-report?date=` | Generate daily market wrap |

---

## What is mocked / placeheld

| Component | Status | Notes |
|-----------|--------|-------|
| ASX announcement source | **Placeholder** | `backend/ingestion/asx_client.py` — raises `NotImplementedError`, falls back to mock data |
| Mock announcements | Working | 10 realistic ASX companies with real text, in `mock_data.py` |
| PDF parsing | Working | PyMuPDF → pdfminer fallback. Works once real PDFs are downloaded |
| LLM summarisation | Working | Degrades gracefully to rule-based if no API key set |
| Price fetcher | Working | yfinance via `.AX` suffix — requires internet + market to be open |
| Importance scoring | Working | Rules-based always runs; LLM scoring added when key is set |
| Frontend | Working | All 5 pages functional with mock data |

---

## Wiring in a real ASX data source

Edit `backend/ingestion/asx_client.py` and implement:

```python
def fetch_announcements_for_date(target_date: date) -> list[dict]:
    # Return list of dicts with: ticker, company_name, title,
    # announcement_datetime, announcement_type, source_url, page_count
    ...
```

The rest of the pipeline (ingestor, summariser, price fetcher, API, frontend) works unchanged.

See the module docstring in `asx_client.py` for a list of data provider options.

---

## Importance scoring reference

| Score | Meaning | Examples |
|-------|---------|---------|
| 9–10 | Major market mover | Takeover bid, insolvency, massive guidance cut |
| 7–8 | High impact | Capital raising, significant guidance change, M&A |
| 5–6 | Moderate | Earnings update, contract win, management change |
| 3–4 | Low | Investor presentation, minor update |
| 1–2 | Noise | Appendix 3Y, change of office, cleansing notice |

---

## Deploying later

- **Backend**: Deploy with `uvicorn` behind Nginx, or push to Railway / Render / Fly.io. Swap SQLite for PostgreSQL by changing the `DATABASE_URL` env var.
- **Frontend**: `npm run build` → deploy to Vercel (add `NEXT_PUBLIC_API_URL` env var pointing to your deployed backend).
- **Scheduling**: Use cron, GitHub Actions, or a task queue (Celery + Redis) to run `run_daily_ingestion.py` at market close (~4:30pm AEST).
