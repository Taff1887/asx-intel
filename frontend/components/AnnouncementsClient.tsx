"use client";

import { useState, useEffect, useCallback, useMemo, Fragment } from "react";
import Link from "next/link";
import { format } from "date-fns";
import { Announcement, API_BASE } from "../lib/api";
import ImportanceBadge from "./ImportanceBadge";
import AnnouncementTypeBadge from "./AnnouncementTypeBadge";
import LivePriceChart from "./LivePriceChart";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Mover {
  ticker: string;
  company_name: string;
  daily_move_pct: number | null;
  open: number | null;
  close: number | null;
}

interface Props {
  allAnnouncements: Announcement[];
  today: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function MoveChip({ pct, large }: { pct: number | null | undefined; large?: boolean }) {
  if (pct == null) return <span className="text-gray-600 font-mono text-xs">—</span>;
  const up = pct >= 0;
  return (
    <span className={`font-mono font-bold ${large ? "text-2xl" : "text-sm"} ${up ? "text-emerald-400" : "text-red-400"}`}>
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

function shortLabel(type: string | null | undefined, title: string): string {
  const MAP: Record<string, string> = {
    "Earnings / Trading Update":      "Earnings",
    "Guidance Upgrade":               "Guidance ▲",
    "Guidance Downgrade":             "Guidance ▼",
    "Capital Raising":                "Capital Raise",
    "M&A / Takeover":                 "M&A",
    "Asset Sale / Acquisition":       "Acquisition",
    "Contract Win":                   "Contract",
    "Regulatory / Legal":             "Regulatory",
    "Management Change":              "Management",
    "Exploration / Drilling Results": "Drilling",
    "Investor Presentation":          "Presentation",
    "Appendix / Administrative":      "Admin",
    "Dividend / Buyback":             "Dividend",
  };
  if (type && MAP[type]) return MAP[type];
  const t = title.toLowerCase();
  if (/agm|general meeting/.test(t))               return "AGM";
  if (/quarterly|activity report/.test(t))         return "Quarterly";
  if (/half.?year|interim/.test(t))                return "Half Year";
  if (/full.?year|annual results|fy\d{2}/.test(t)) return "Full Year";
  if (/director|ceo|cfo|chairman/.test(t))         return "Board";
  if (/placement|entitlement|capital raise/.test(t)) return "Capital Raise";
  if (/merger|acqui|takeover/.test(t))             return "M&A";
  if (/contract|agreement|supply/.test(t))         return "Contract";
  if (/drill|assay|intercept|mineral/.test(t))     return "Drilling";
  if (/divid/.test(t))                             return "Dividend";
  if (/trading halt|suspension/.test(t))           return "Halt";
  return "Announcement";
}

const ANN_TYPES = [
  "All Types",
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
];

// ── Mover card — compact, fixed height, purely visual highlight ───────────────

function MoverCard({
  mover, rank, up, selected, onSelect,
}: {
  mover: Mover; rank: number; up: boolean; selected: boolean; onSelect: () => void;
}) {
  const pct = mover.daily_move_pct ?? 0;

  return (
    <div
      onClick={onSelect}
      className={`rounded-xl p-3 cursor-pointer transition-all border ${
        selected
          ? up
            ? "bg-emerald-500/10 border-emerald-500/50 ring-1 ring-emerald-500/30"
            : "bg-red-500/10  border-red-500/50  ring-1 ring-red-500/30"
          : up
            ? "bg-emerald-500/5 border-emerald-500/15 hover:border-emerald-500/40"
            : "bg-red-500/5  border-red-500/15  hover:border-red-500/40"
      }`}
    >
      {/* rank · ticker · bar · move% — all on one line */}
      <div className="flex items-center gap-2">
        <span className="text-gray-600 font-mono text-xs w-4 shrink-0 text-right">{rank}</span>
        <span className={`font-mono font-bold text-sm w-12 shrink-0 ${up ? "text-emerald-400" : "text-red-400"}`}>
          {mover.ticker}
        </span>
        <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${up ? "bg-emerald-500" : "bg-red-500"}`}
            style={{ width: `${Math.min(100, Math.abs(pct) * 4)}%` }}
          />
        </div>
        <span className={`font-mono font-bold text-xs w-16 text-right shrink-0 ${up ? "text-emerald-400" : "text-red-400"}`}>
          {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
        </span>
      </div>

      {/* company · price */}
      <div className="flex items-center justify-between mt-0.5 ml-6">
        <p className="text-[10px] text-gray-500 truncate">{mover.company_name}</p>
        {mover.close != null && (
          <span className="text-[10px] text-gray-600 font-mono shrink-0 ml-2">
            ${mover.close.toFixed(3)}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Announcement summary panel ────────────────────────────────────────────────

function parseBullets(s: string | null | undefined): string[] {
  return s
    ? s.split("\n").map((l) => l.replace(/^\s*(?:[•\-*]|â€¢)\s*/, "").trim()).filter((l) => l.length > 0)
    : [];
}

function AnnouncementSummary({
  ticker, announcements, livePct,
}: {
  ticker: string;
  announcements: Announcement[];
  livePct?: number | null;
}) {
  // AI summary is generated ONLY when the user clicks the button — never on load.
  const [aiData, setAiData] = useState<Announcement | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState(false);

  // Highest-importance announcement for this ticker
  const base = useMemo(() => {
    const matches = announcements.filter((a) => a.ticker === ticker);
    if (!matches.length) return null;
    return matches.reduce((best, cur) =>
      (cur.importance_score ?? 0) > (best.importance_score ?? 0) ? cur : best
    );
  }, [ticker, announcements]);

  // Reset AI state when the selected ticker changes
  useEffect(() => {
    setAiData(null);
    setGenerating(false);
    setGenError(false);
  }, [ticker]);

  if (!base) return null;

  // Freshest record (post-generation if available) for type/score/AI fields
  const rec = aiData ?? base;

  const displayPct = livePct !== undefined && livePct !== null ? livePct : base.price_move_pct;
  const up = (displayPct ?? 0) >= 0;
  const label = shortLabel(rec.announcement_type, rec.title);

  // The "original" dot points that come with the announcement
  const originalBullets = parseBullets(base.summary_detailed);

  // The on-demand AI summary (freshly generated, or already cached on the record)
  const aiOverview = aiData?.ai_business_overview ?? base.ai_business_overview;
  const aiSummary  = aiData?.ai_summary       ?? base.ai_summary;
  const aiShort    = aiData?.ai_summary_short ?? base.ai_summary_short;
  const aiWhy      = aiData?.ai_why_it_matters ?? base.ai_why_it_matters;
  const aiBullets  = parseBullets(aiSummary);
  const hasAi      = aiBullets.length > 0 || !!aiShort;
  // Don't repeat the headline if it's identical to the first bullet (rule-based fallback)
  const showShort  = !!aiShort && aiShort.trim().toLowerCase() !== (aiBullets[0] ?? "").trim().toLowerCase();

  async function generateAI() {
    setGenerating(true);
    setGenError(false);
    // Pass the live move so the AI can explain the actual market reaction
    const q = displayPct != null ? `?move=${encodeURIComponent(displayPct)}` : "";
    const url = `${API_BASE}/announcements/${base!.id}/enrich${q}`;
    // Render's free tier spins down when idle — the first request can fail or
    // time out while it cold-starts (~30-60s). Retry a few times so the wake-up
    // request kicks it off and a later attempt succeeds.
    const delays = [0, 5000, 8000, 12000];
    for (let attempt = 0; attempt < delays.length; attempt++) {
      if (delays[attempt]) await new Promise((r) => setTimeout(r, delays[attempt]));
      try {
        const res = await fetch(url, { method: "POST" });
        if (res.ok) {
          setAiData((await res.json()) as Announcement);
          setGenerating(false);
          return;
        }
      } catch { /* network / cold-start — retry */ }
    }
    setGenError(true);
    setGenerating(false);
  }

  return (
    <div className="card space-y-4">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded ${
            up ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"
          }`}>
            {label}
          </span>
          <span className="text-gray-600 text-xs">{rec.company_name}</span>
          {rec.importance_score != null && <ImportanceBadge score={rec.importance_score} />}
        </div>
        <MoveChip pct={displayPct} large />
      </div>

      {/* Title */}
      <h3 className="text-white font-semibold text-base leading-snug">
        {base.source_url ? (
          <a href={base.source_url} target="_blank" rel="noopener noreferrer"
            className="hover:text-emerald-300 transition-colors">
            {base.title}
          </a>
        ) : base.title}
      </h3>

      {/* Original dot points (the summary that comes with the announcement) */}
      {originalBullets.length > 0 && (
        <ul className="space-y-1.5">
          {originalBullets.map((b, i) => (
            <li key={i} className="flex gap-2 text-sm text-gray-300 leading-relaxed">
              <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${up ? "bg-emerald-500" : "bg-red-500"}`} />
              {b}
            </li>
          ))}
        </ul>
      )}

      {/* ── AI summary: button → on-demand generation ── (directly below dots) */}
      <div>
        {hasAi ? (
          <div className={`rounded-lg px-4 py-3 border ${
            up ? "bg-emerald-500/5 border-emerald-500/25" : "bg-red-500/5 border-red-500/25"
          }`}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400">
                ✨ AI Summary
                <span className="ml-1 text-gray-600 font-normal normal-case tracking-normal">· Llama 3.3 70B</span>
              </p>
              <button
                onClick={generateAI}
                className="text-[10px] text-gray-500 hover:text-emerald-400 transition-colors"
                title="Regenerate this summary"
              >
                ↻ Regenerate
              </button>
            </div>

            {/* What the company does */}
            {aiOverview && (
              <div className="mb-3 pb-3 border-b border-gray-800">
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-1">About the company</p>
                <p className="text-xs text-gray-400 leading-relaxed">{aiOverview}</p>
              </div>
            )}

            {showShort && <p className="text-sm text-gray-100 leading-relaxed mb-2 font-medium">{aiShort}</p>}
            {aiBullets.length > 0 && (
              <ul className="space-y-1.5">
                {aiBullets.map((b, i) => (
                  <li key={i} className="flex gap-2 text-sm text-gray-300 leading-relaxed">
                    <span className="mt-1.5 w-1 h-1 rounded-full shrink-0 bg-emerald-400" />
                    {b}
                  </li>
                ))}
              </ul>
            )}
            {aiWhy && (
              <div className="mt-2.5 pt-2.5 border-t border-gray-800">
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-1">
                  Why it matters &amp; market reaction
                </p>
                <p className="text-xs text-gray-300 leading-relaxed">{aiWhy}</p>
              </div>
            )}
          </div>
        ) : generating ? (
          <div className="rounded-lg px-4 py-3 border border-emerald-500/25 bg-emerald-500/5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 mb-2 animate-pulse">
              ✨ Generating AI summary…
            </p>
            <ul className="space-y-2">
              {[80, 100, 65].map((w, i) => (
                <li key={i} className="flex gap-2 items-center">
                  <span className="w-1 h-1 rounded-full bg-gray-700 shrink-0 animate-pulse" />
                  <div className="h-3 bg-gray-800 rounded animate-pulse" style={{ width: `${w}%` }} />
                </li>
              ))}
            </ul>
            <p className="text-[10px] text-gray-600 mt-2">
              Reading the announcement PDF… the first summary can take up to a minute while the server wakes up.
            </p>
          </div>
        ) : (
          <button
            onClick={generateAI}
            className="w-full py-2.5 text-xs font-semibold text-emerald-400 border border-emerald-500/30 hover:border-emerald-500/60 hover:bg-emerald-500/10 rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            ✨ Generate AI Summary
            <span className="text-gray-600 font-normal">· reads the full PDF</span>
          </button>
        )}
        {genError && (
          <p className="text-[10px] text-red-400/80 mt-1.5">
            Couldn’t generate the summary — the server may be waking up. Click Generate again in a moment.
          </p>
        )}
      </div>

      {/* Footer: time + link */}
      <div className="flex items-center justify-between pt-1 border-t border-gray-800">
        <span className="text-[10px] text-gray-600">
          {format(new Date(base.announcement_datetime), "h:mm a")} AEST
        </span>
        <div className="flex items-center gap-3">
          {base.source_url && (
            <a href={base.source_url} target="_blank" rel="noopener noreferrer"
              className="text-[10px] text-gray-500 hover:text-white transition-colors">
              View announcement ↗
            </a>
          )}
          <Link href={`/announcement/${base.id}`}
            className="text-[10px] text-gray-500 hover:text-emerald-400 transition-colors">
            Full detail →
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function AnnouncementsClient({ allAnnouncements, today }: Props) {
  const [selectedTicker, setSelectedTicker] = useState("");
  const [movers, setMovers]       = useState<{ gainers: Mover[]; losers: Mover[] }>({ gainers: [], losers: [] });
  const [moversLoading, setMoversLoading] = useState(true);

  // Announcements: seed from the server-rendered prop, but ALSO refetch client-side.
  // The server render can be empty (Render cold-start during SSR) or stale (Vercel
  // page cache), so the client fetch is the source of truth once it lands.
  const [announcements, setAnnouncements] = useState<Announcement[]>(allAnnouncements);

  const [showMoreGainers, setShowMoreGainers] = useState(false);
  const [showMoreLosers,  setShowMoreLosers]  = useState(false);

  const [filterType,    setFilterType]    = useState("All Types");
  const [filterMinMove, setFilterMinMove] = useState("");
  const [filterDir,     setFilterDir]     = useState<"all" | "up" | "down">("all");
  const [filterSearch,  setFilterSearch]  = useState("");
  const [sortBy,        setSortBy]        = useState<"time" | "score" | "move">("score");
  const [sortDir,       setSortDir]       = useState<"desc" | "asc">("desc");

  // ── Fetch movers ───────────────────────────────────────────────────────────

  const fetchMovers = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/prices/movers?date=${today}&limit=20`);
      if (!res.ok) return;
      const data = await res.json();
      const g: Mover[] = data.gainers ?? [];
      const l: Mover[] = data.losers  ?? [];
      setMovers({ gainers: g, losers: l });
      setSelectedTicker((prev) => prev || g[0]?.ticker || l[0]?.ticker || "");
    } catch { /* offline */ }
    setMoversLoading(false);
  }, [today]);

  useEffect(() => {
    fetchMovers();
    const id = setInterval(fetchMovers, 120_000);
    return () => clearInterval(id);
  }, [fetchMovers]);

  // ── Fetch announcements client-side (resilient to SSR cold-start / page cache) ─

  const fetchAnnouncements = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/announcements?date=${today}&limit=500`);
      if (!res.ok) return;
      const data: Announcement[] = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        data.sort((a, b) => (b.importance_score ?? 0) - (a.importance_score ?? 0));
        setAnnouncements(data);
      }
    } catch { /* offline — keep whatever we have */ }
  }, [today]);

  useEffect(() => {
    fetchAnnouncements();
    const id = setInterval(fetchAnnouncements, 120_000);
    return () => clearInterval(id);
  }, [fetchAnnouncements]);

  // ── Filtered + sorted table ────────────────────────────────────────────────

  const filtered = useMemo(() => {
    const rows = announcements.filter((ann) => {
      if (filterType !== "All Types" && ann.announcement_type !== filterType) return false;
      const move = ann.price_move_pct;
      if (filterDir === "up"   && (move == null || move <= 0)) return false;
      if (filterDir === "down" && (move == null || move >= 0)) return false;
      if (filterMinMove && (move == null || Math.abs(move) < parseFloat(filterMinMove))) return false;
      if (filterSearch) {
        const q = filterSearch.toLowerCase();
        if (
          !ann.ticker.toLowerCase().includes(q) &&
          !ann.title.toLowerCase().includes(q) &&
          !(ann.company_name ?? "").toLowerCase().includes(q)
        ) return false;
      }
      return true;
    });

    rows.sort((a, b) => {
      let av = 0, bv = 0;
      if (sortBy === "score") {
        av = a.importance_score ?? 0; bv = b.importance_score ?? 0;
      } else if (sortBy === "move") {
        av = Math.abs(a.price_move_pct ?? 0); bv = Math.abs(b.price_move_pct ?? 0);
      } else {
        av = new Date(a.announcement_datetime).getTime();
        bv = new Date(b.announcement_datetime).getTime();
      }
      return sortDir === "desc" ? bv - av : av - bv;
    });

    return rows;
  }, [announcements, filterType, filterDir, filterMinMove, filterSearch, sortBy, sortDir]);

  // Group the (already-sorted) rows by ticker, preserving order. A stock with
  // several announcements becomes ONE group: the move is shown once, the
  // announcements are listed underneath.
  const grouped = useMemo(() => {
    const map = new Map<string, Announcement[]>();
    for (const a of filtered) {
      const arr = map.get(a.ticker);
      if (arr) arr.push(a);
      else map.set(a.ticker, [a]);
    }
    return Array.from(map.values());
  }, [filtered]);

  function toggleSort(col: "time" | "score" | "move") {
    if (sortBy === col) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortBy(col); setSortDir("desc"); }
  }

  function SortIcon({ col }: { col: "time" | "score" | "move" }) {
    if (sortBy !== col) return <span className="ml-1 text-gray-700">⇅</span>;
    return <span className="ml-1 text-emerald-400">{sortDir === "desc" ? "↓" : "↑"}</span>;
  }

  const anyFilter = filterType !== "All Types" || filterDir !== "all" || filterMinMove || filterSearch;
  const visibleGainers = movers.gainers.slice(0, showMoreGainers ? 20 : 10);
  const visibleLosers  = movers.losers.slice(0,  showMoreLosers  ? 20 : 10);

  // Live price for selected ticker — kept in sync with the movers fetch (every 2 min)
  const selectedMoverPct = useMemo(() => {
    const all = [...movers.gainers, ...movers.losers];
    return all.find((m) => m.ticker === selectedTicker)?.daily_move_pct ?? null;
  }, [movers, selectedTicker]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">

      {/* ══ SECTION 1: INTRADAY CHART ════════════════════════════════════════ */}
      {selectedTicker ? (
        <div className="card">
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Intraday</h2>
            <Link
              href={`/company/${selectedTicker}`}
              className="font-mono font-bold text-emerald-400 hover:text-emerald-300 text-xl"
            >
              {selectedTicker}
            </Link>
            <span className="text-xs text-gray-700">· click any stock below to switch</span>
          </div>
          <LivePriceChart key={selectedTicker} ticker={selectedTicker} refreshSeconds={60} />
        </div>
      ) : moversLoading ? (
        <div className="card py-10 text-center text-gray-600 text-sm animate-pulse">
          Loading market data…
        </div>
      ) : null}

      {/* ══ SECTION 2: ANNOUNCEMENT SUMMARY ══════════════════════════════════ */}
      {selectedTicker && (
        <AnnouncementSummary
          ticker={selectedTicker}
          announcements={announcements}
          livePct={selectedMoverPct}
        />
      )}

      {/* ══ SECTION 3: TOP GAINS + LOSSES ════════════════════════════════════ */}
      {!moversLoading && (movers.gainers.length > 0 || movers.losers.length > 0) && (
        <div>
          <p className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">
            Biggest Movers Today
            <span className="ml-2 font-normal text-gray-700 normal-case tracking-normal">
              announcement-attributed
            </span>
          </p>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Gainers */}
            <div className="space-y-1.5">
              <p className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-2">▲ Top Gains</p>
              {visibleGainers.map((m, i) => (
                <MoverCard
                  key={m.ticker} mover={m} rank={i + 1} up={true}
                  selected={selectedTicker === m.ticker}
                  onSelect={() => setSelectedTicker(m.ticker)}
                />
              ))}
              {movers.gainers.length > 10 && (
                <button
                  onClick={() => setShowMoreGainers((v) => !v)}
                  className="w-full py-2 text-xs text-gray-600 hover:text-emerald-400 border border-gray-800 hover:border-emerald-500/30 rounded-lg transition-colors"
                >
                  {showMoreGainers ? "Show less ▴" : "Show 10 more ▾"}
                </button>
              )}
            </div>

            {/* Losers */}
            <div className="space-y-1.5">
              <p className="text-xs font-bold text-red-400 uppercase tracking-widest mb-2">▼ Top Losses</p>
              {visibleLosers.map((m, i) => (
                <MoverCard
                  key={m.ticker} mover={m} rank={i + 1} up={false}
                  selected={selectedTicker === m.ticker}
                  onSelect={() => setSelectedTicker(m.ticker)}
                />
              ))}
              {movers.losers.length > 10 && (
                <button
                  onClick={() => setShowMoreLosers((v) => !v)}
                  className="w-full py-2 text-xs text-gray-600 hover:text-red-400 border border-gray-800 hover:border-red-500/30 rounded-lg transition-colors"
                >
                  {showMoreLosers ? "Show less ▴" : "Show 10 more ▾"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ══ SECTION 4: ALL ANNOUNCEMENTS TABLE ═══════════════════════════════ */}
      <div className="card">
        <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
          <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest">
            All Announcements
            <span className="ml-2 font-normal text-gray-700 normal-case tracking-normal">
              {filtered.length}
              {filtered.length !== announcements.length ? ` of ${announcements.length}` : ""}
              {grouped.length !== filtered.length ? ` · ${grouped.length} stocks` : ""}
            </span>
          </h2>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-end gap-3 mb-5 pb-5 border-b border-gray-800">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-gray-600 uppercase tracking-wide">Type</label>
            <select
              value={filterType} onChange={(e) => setFilterType(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-emerald-500 min-w-[180px]"
            >
              {ANN_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-gray-600 uppercase tracking-wide">Direction</label>
            <div className="flex rounded-lg overflow-hidden border border-gray-700 text-xs">
              {([["all", "All"], ["up", "▲ Gains"], ["down", "▼ Losses"]] as const).map(([val, lbl]) => (
                <button
                  key={val} onClick={() => setFilterDir(val)}
                  className={`px-3 py-1.5 transition-colors ${
                    filterDir === val
                      ? val === "up"   ? "bg-emerald-500/20 text-emerald-400"
                      : val === "down" ? "bg-red-500/20 text-red-400"
                      : "bg-gray-700 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  }`}
                >
                  {lbl}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-gray-600 uppercase tracking-wide">Min Move</label>
            <select
              value={filterMinMove} onChange={(e) => setFilterMinMove(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-emerald-500"
            >
              <option value="">Any</option>
              <option value="2">2%+</option>
              <option value="5">5%+</option>
              <option value="10">10%+</option>
              <option value="20">20%+</option>
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-gray-600 uppercase tracking-wide">Search</label>
            <input
              type="text" placeholder="ticker, company or keyword…"
              value={filterSearch} onChange={(e) => setFilterSearch(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-gray-200 w-48 focus:outline-none focus:border-emerald-500"
            />
          </div>

          {anyFilter && (
            <button
              onClick={() => { setFilterType("All Types"); setFilterDir("all"); setFilterMinMove(""); setFilterSearch(""); }}
              className="text-xs text-gray-500 hover:text-white px-3 py-1.5 rounded-lg border border-gray-800 hover:bg-gray-800 transition-colors"
            >
              ✕ Clear
            </button>
          )}
        </div>

        {/* Table */}
        {announcements.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-gray-500 text-sm">No announcements loaded yet.</p>
            <p className="text-gray-700 text-xs mt-1">The pipeline runs hourly during trading hours.</p>
          </div>
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-gray-500 text-sm">No announcements match these filters.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-[10px] text-gray-500 uppercase tracking-wide border-b border-gray-800">
                  <th className="px-3 pb-3">
                    <button onClick={() => toggleSort("time")} className="hover:text-white transition-colors flex items-center">
                      Time <SortIcon col="time" />
                    </button>
                  </th>
                  <th className="px-3 pb-3">Stock</th>
                  <th className="px-3 pb-3 hidden md:table-cell">Announcement</th>
                  <th className="px-3 pb-3 hidden lg:table-cell">Type</th>
                  <th className="px-3 pb-3 text-center">
                    <button onClick={() => toggleSort("score")} className="hover:text-white transition-colors flex items-center mx-auto">
                      Score <SortIcon col="score" />
                    </button>
                  </th>
                  <th className="px-3 pb-3 text-right">
                    <button onClick={() => toggleSort("move")} className="hover:text-white transition-colors flex items-center ml-auto">
                      Move <SortIcon col="move" />
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {grouped.map((items) => {
                  const top = items[0];
                  const rest = items.slice(1);
                  const move = top.price_move_pct;
                  const up = (move ?? 0) >= 0;
                  const isSelected = top.ticker === selectedTicker;
                  const tickerColor =
                    move != null && up ? "text-emerald-400"
                    : move != null ? "text-red-400"
                    : "text-gray-300";
                  const showWhy = (ann: Announcement) =>
                    (ann.why_it_matters || ann.summary_short) &&
                    !ann.why_it_matters?.toLowerCase().includes("monitoring this") &&
                    !ann.summary_short?.toLowerCase().includes("has released an announcement");

                  return (
                    <Fragment key={top.ticker}>
                      {/* Main row — ticker + move shown once per stock */}
                      <tr
                        onClick={() => setSelectedTicker(top.ticker)}
                        className={`cursor-pointer transition-colors border-t border-gray-800 ${
                          isSelected ? "bg-gray-800/60" : "hover:bg-gray-800/40"
                        }`}
                      >
                        <td className="px-3 py-3 text-xs text-gray-500 whitespace-nowrap align-top">
                          {format(new Date(top.announcement_datetime), "HH:mm")}
                        </td>
                        <td className="px-3 py-3 align-top">
                          <span className={`font-mono font-bold text-sm ${tickerColor}`}>{top.ticker}</span>
                          <p className="text-[10px] text-gray-600 mt-0.5 hidden sm:block truncate max-w-[80px]">
                            {top.company_name}
                          </p>
                          {rest.length > 0 && (
                            <span className="text-[10px] text-emerald-500/70">{items.length} announcements</span>
                          )}
                        </td>
                        <td className="px-3 py-3 hidden md:table-cell max-w-sm align-top">
                          <span className="text-gray-200 line-clamp-1 font-medium">{top.title}</span>
                          {showWhy(top) && (
                            <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">
                              {top.why_it_matters || top.summary_short}
                            </p>
                          )}
                        </td>
                        <td className="px-3 py-3 hidden lg:table-cell align-top">
                          <AnnouncementTypeBadge type={top.announcement_type} />
                        </td>
                        <td className="px-3 py-3 text-center align-top">
                          <ImportanceBadge score={top.importance_score} />
                        </td>
                        <td className="px-3 py-3 text-right align-top">
                          <MoveChip pct={move} />
                        </td>
                      </tr>

                      {/* Sub rows — the stock's other announcements (move not repeated) */}
                      {rest.map((ann) => (
                        <tr
                          key={ann.id}
                          onClick={() => setSelectedTicker(ann.ticker)}
                          className={`cursor-pointer transition-colors ${
                            isSelected ? "bg-gray-800/40" : "hover:bg-gray-800/30"
                          }`}
                        >
                          <td className="px-3 py-2 text-xs text-gray-600 whitespace-nowrap align-top">
                            {format(new Date(ann.announcement_datetime), "HH:mm")}
                          </td>
                          <td className="px-3 py-2" />
                          <td className="px-3 py-2 hidden md:table-cell max-w-sm align-top">
                            <span className="flex gap-1.5 text-gray-400 text-xs">
                              <span className="text-gray-700">↳</span>
                              <span className="line-clamp-1">{ann.title}</span>
                            </span>
                          </td>
                          <td className="px-3 py-2 hidden lg:table-cell align-top">
                            <AnnouncementTypeBadge type={ann.announcement_type} />
                          </td>
                          <td className="px-3 py-2 text-center align-top">
                            <ImportanceBadge score={ann.importance_score} />
                          </td>
                          <td className="px-3 py-2" />
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
