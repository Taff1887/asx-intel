"use client";

import { useEffect, useState } from "react";
import { format } from "date-fns";
import Link from "next/link";
import { API_BASE } from "../../lib/api";

interface Mover {
  ticker: string;
  company_name: string;
  daily_move_pct: number | null;
  close: number | null;
}

// ── Mover card ────────────────────────────────────────────────────────────────

function MoverCard({ mover, rank, up }: { mover: Mover; rank: number; up: boolean }) {
  const pct = mover.daily_move_pct ?? 0;

  return (
    <div className={`rounded-xl p-4 border ${
      up ? "bg-emerald-500/5 border-emerald-500/20" : "bg-red-500/5 border-red-500/20"
    }`}>
      <div className="flex items-center gap-3">
        <span className="text-gray-600 font-mono text-xs w-5 shrink-0 text-right">{rank}</span>
        <Link
          href={`/company/${mover.ticker}`}
          className={`font-mono font-bold text-sm w-16 shrink-0 ${
            up ? "text-emerald-400 hover:text-emerald-300" : "text-red-400 hover:text-red-300"
          }`}
        >
          {mover.ticker}
        </Link>
        <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${up ? "bg-emerald-500" : "bg-red-500"}`}
            style={{ width: `${Math.min(100, Math.abs(pct) * 3)}%` }}
          />
        </div>
        <span className={`font-mono font-bold text-sm w-20 text-right shrink-0 ${
          up ? "text-emerald-400" : "text-red-400"
        }`}>
          {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
        </span>
      </div>

      <div className="flex items-center justify-between mt-1 ml-8">
        <p className="text-xs text-gray-500 truncate">{mover.company_name}</p>
        {mover.close != null && (
          <span className="text-xs text-gray-600 font-mono shrink-0 ml-2">
            ${mover.close.toFixed(3)}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AsxPage() {
  const [gainers, setGainers] = useState<Mover[]>([]);
  const [losers, setLosers]   = useState<Mover[]>([]);
  const [asOf, setAsOf]       = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const res  = await fetch(`${API_BASE}/market/asx-movers?limit=20`);
      if (!res.ok) return;
      const data = await res.json();
      setGainers(data.gainers ?? []);
      setLosers(data.losers   ?? []);
      setAsOf(data.as_of      ?? null);
    } catch { /* offline */ }
    setLoading(false);
  }

  useEffect(() => {
    load();
    // Refresh every 5 minutes (matches cache TTL)
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">ASX Top Movers</h1>
        <p className="text-gray-500 text-sm mt-1">
          Top 20 gains · Top 20 losses · {format(new Date(), "d MMM yyyy")}
          {asOf && <span className="ml-2 text-gray-600">· {asOf}</span>}
        </p>
      </div>

      {loading ? (
        <div className="py-20 text-center text-gray-600 text-sm animate-pulse">
          Fetching market data…
        </div>
      ) : gainers.length === 0 && losers.length === 0 ? (
        <div className="card py-20 text-center">
          <p className="text-gray-500 text-sm">No price data available.</p>
          <p className="text-gray-700 text-xs mt-1">Available during trading hours · 10am–4:30pm AEST</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Top 20 Gains */}
          <div className="space-y-2">
            <h2 className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-3">
              ▲ Top 20 Gains
            </h2>
            {gainers.map((m, i) => (
              <MoverCard key={m.ticker} mover={m} rank={i + 1} up={true} />
            ))}
          </div>

          {/* Top 20 Losses */}
          <div className="space-y-2">
            <h2 className="text-xs font-bold text-red-400 uppercase tracking-widest mb-3">
              ▼ Top 20 Losses
            </h2>
            {losers.map((m, i) => (
              <MoverCard key={m.ticker} mover={m} rank={i + 1} up={false} />
            ))}
          </div>

        </div>
      )}
    </div>
  );
}
