import { format } from "date-fns";
import Link from "next/link";
import { api } from "../lib/api";
import { API_BASE } from "../lib/api";

interface MarketIndex {
  label: string;
  price: number;
  change_pct: number | null;
}

interface MarketOverview {
  asx200: MarketIndex | null;
  sp500:  MarketIndex | null;
  audusd: MarketIndex | null;
  as_of:  string;
}

async function getData() {
  const today = format(new Date(), "yyyy-MM-dd");
  const [annsResult, marketResult] = await Promise.allSettled([
    api.announcements({ date: today, limit: "300" }),
    fetch(`${API_BASE}/market/overview`, { cache: "no-store" }).then((r) => r.json()),
  ]);
  return {
    announcements: annsResult.status === "fulfilled" ? annsResult.value : [],
    market: marketResult.status === "fulfilled" ? (marketResult.value as MarketOverview) : null,
    today,
  };
}

function IndexCard({ data, subtitle }: { data: MarketIndex | null; subtitle: string }) {
  if (!data) return (
    <div className="card text-center opacity-40">
      <div className="text-2xl font-bold text-gray-500">—</div>
      <div className="text-xs text-gray-600 mt-1">{subtitle}</div>
    </div>
  );
  const up = (data.change_pct ?? 0) >= 0;
  return (
    <div className="card text-center">
      <div className={`text-2xl font-bold font-mono ${up ? "text-emerald-400" : "text-red-400"}`}>
        {data.change_pct != null
          ? `${up ? "+" : ""}${data.change_pct.toFixed(2)}%`
          : data.price.toLocaleString()}
      </div>
      <div className="text-xs text-gray-400 mt-1 font-medium">{data.label}</div>
      <div className="text-xs text-gray-600 mt-0.5">{subtitle}</div>
      {data.change_pct != null && (
        <div className="text-xs text-gray-600 mt-0.5 font-mono">
          {data.label === "AUD/USD" ? data.price.toFixed(4) : data.price.toLocaleString()}
        </div>
      )}
    </div>
  );
}

export default async function HomePage() {
  const { announcements, market, today } = await getData();

  const totalAnn = announcements.length;
  const withMoves = announcements.filter((a) => a.price_move_pct != null);
  const topGainer = withMoves.length > 0
    ? withMoves.reduce((b, a) => a.price_move_pct! > b.price_move_pct! ? a : b)
    : null;
  const topLoser = withMoves.length > 0
    ? withMoves.reduce((b, a) => a.price_move_pct! < b.price_move_pct! ? a : b)
    : null;

  return (
    <div className="max-w-4xl mx-auto space-y-6 py-6">

      {/* Date + title */}
      <div>
        <h1 className="text-2xl font-bold text-white">ASX Intel</h1>
        <p className="text-gray-500 text-sm mt-1">
          {format(new Date(), "EEEE, d MMMM yyyy")}
          {market?.as_of && <span className="ml-2 text-gray-600">· {market.as_of}</span>}
        </p>
      </div>

      {/* Market indices */}
      <div>
        <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Markets</h2>
        <div className="grid grid-cols-3 gap-3">
          <IndexCard data={market?.asx200 ?? null} subtitle="Today" />
          <IndexCard data={market?.sp500  ?? null} subtitle="Overnight" />
          <IndexCard data={market?.audusd ?? null} subtitle="AUD/USD" />
        </div>
      </div>

      {/* Announcements today */}
      <div>
        <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Today's Announcements</h2>
        <div className="grid grid-cols-3 gap-3">
          <div className="card text-center">
            <div className="text-3xl font-bold text-white">{totalAnn}</div>
            <div className="text-xs text-gray-500 mt-1">Total announcements</div>
          </div>
          <div className="card text-center">
            {topGainer ? (
              <>
                <div className="text-2xl font-bold text-emerald-400 font-mono">
                  +{topGainer.price_move_pct!.toFixed(1)}%
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Top gainer
                </div>
                <div className="text-xs text-emerald-400 font-mono font-bold mt-0.5">{topGainer.ticker}</div>
              </>
            ) : (
              <>
                <div className="text-2xl font-bold text-gray-600">—</div>
                <div className="text-xs text-gray-500 mt-1">Top gainer</div>
              </>
            )}
          </div>
          <div className="card text-center">
            {topLoser ? (
              <>
                <div className="text-2xl font-bold text-red-400 font-mono">
                  {topLoser.price_move_pct!.toFixed(1)}%
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Top loser
                </div>
                <div className="text-xs text-red-400 font-mono font-bold mt-0.5">{topLoser.ticker}</div>
              </>
            ) : (
              <>
                <div className="text-2xl font-bold text-gray-600">—</div>
                <div className="text-xs text-gray-500 mt-1">Top loser</div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* CTA */}
      <Link
        href="/announcements"
        className="flex items-center justify-between w-full card hover:bg-gray-800 transition-colors group cursor-pointer border border-gray-700/50 hover:border-emerald-500/30"
      >
        <div>
          <div className="text-sm font-semibold text-white">View Today's Announcements</div>
          <div className="text-xs text-gray-500 mt-0.5">Top 10 · biggest movers · full table with filters</div>
        </div>
        <span className="text-emerald-400 group-hover:translate-x-1 transition-transform text-lg">→</span>
      </Link>

    </div>
  );
}
