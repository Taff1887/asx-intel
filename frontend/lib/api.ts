export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BASE = API_BASE;

export interface Announcement {
  id: number;
  ticker: string;
  company_name: string;
  sector: string | null;
  title: string;
  announcement_type: string | null;
  announcement_datetime: string;
  source_url: string | null;
  page_count: number | null;
  summary_short: string | null;
  summary_detailed: string | null;
  why_it_matters: string | null;
  market_impact: string | null;
  key_numbers: string | null;
  risks_caveats: string | null;
  ai_business_overview: string | null;
  ai_summary: string | null;
  ai_summary_short: string | null;
  ai_why_it_matters: string | null;
  importance_score: number | null;
  importance_reason: string | null;
  price_move_pct: number | null;
  abnormal_move_pct: number | null;
  created_at: string;
}

export interface AnnouncementDetail extends Announcement {
  raw_text: string | null;
  cleaned_text: string | null;
}

export interface PriceData {
  id: number;
  ticker: string;
  date: string;
  open: number | null;
  close: number | null;
  prev_close: number | null;
  volume: number | null;
  daily_move_pct: number | null;
  volume_spike_ratio: number | null;
}

export interface DailyReport {
  id: number;
  date: string;
  executive_summary: string | null;
  top_announcements_json: string | null;
  top_movers_json: string | null;
  sector_themes: string | null;
  unusual_moves: string | null;
  watchlist_tomorrow: string | null;
  full_report_text: string | null;
  created_at: string;
}

export interface Sector {
  id: number;
  name: string;
  description: string | null;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

export const api = {
  announcements: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return get<Announcement[]>(`/announcements${qs}`);
  },
  announcement: (id: number) => get<AnnouncementDetail>(`/announcements/${id}`),
  dailyReport: (date?: string) =>
    get<DailyReport>(`/daily-report${date ? `?date=${date}` : ""}`),
  companyAnnouncements: (ticker: string) =>
    get<Announcement[]>(`/companies/${ticker}/announcements`),
  companyPrices: (ticker: string) =>
    get<PriceData[]>(`/companies/${ticker}/prices`),
  sectors: () => get<Sector[]>("/sectors"),
  sectorAnnouncements: (name: string) =>
    get<Announcement[]>(`/sectors/${encodeURIComponent(name)}/announcements`),

  // Mutations
  ingest: (date?: string, mock = false) =>
    fetch(`${BASE}/ingest?${date ? `date=${date}&` : ""}mock=${mock}`, { method: "POST" }).then((r) => r.json()),
  summarise: (date?: string) =>
    fetch(`${BASE}/summarise${date ? `?date=${date}` : ""}`, { method: "POST" }).then((r) => r.json()),
  generateReport: (date?: string) =>
    fetch(`${BASE}/generate-daily-report${date ? `?date=${date}` : ""}`, { method: "POST" }).then((r) => r.json()),
  fetchPrices: (date?: string) =>
    fetch(`${BASE}/fetch-prices${date ? `?date=${date}` : ""}`, { method: "POST" }).then((r) => r.json()),
};
