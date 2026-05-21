"use client";

import { useEffect, useState, useCallback } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  TooltipProps,
} from "recharts";
import { format } from "date-fns";
import { API_BASE } from "../lib/api";

interface Bar {
  time: string;
  open: number | null;
  close: number | null;
}

interface Props {
  ticker: string;
  refreshSeconds?: number;
}

function fmtTime(iso: string) {
  try { return format(new Date(iso), "h:mma"); } catch { return iso.slice(11, 16); }
}

function fmtPrice(v: number) {
  // Adaptive decimals: small stocks need more
  if (v < 0.1) return `$${v.toFixed(4)}`;
  if (v < 1)   return `$${v.toFixed(3)}`;
  return `$${v.toFixed(2)}`;
}

function pctFromRef(price: number, ref: number) {
  if (!ref) return null;
  return ((price - ref) / ref) * 100;
}

// Custom tooltip showing time, price, and % change from prev close
function ChartTooltip({
  active, payload, label, prevClose, colour,
}: TooltipProps<number, string> & { prevClose: number | null; colour: string }) {
  if (!active || !payload?.length) return null;
  const price = payload[0]?.value as number | undefined;
  if (price == null) return null;

  const pct = prevClose ? pctFromRef(price, prevClose) : null;
  const isUp = (pct ?? 0) >= 0;

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 shadow-xl text-xs">
      <p className="text-gray-400 mb-1">{label}</p>
      <p className="font-mono font-bold text-white text-sm">{fmtPrice(price)}</p>
      {pct != null && (
        <p className={`font-mono font-bold mt-0.5 ${isUp ? "text-emerald-400" : "text-red-400"}`}>
          {isUp ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}% vs prev close
        </p>
      )}
      {prevClose != null && (
        <p className="text-gray-600 mt-0.5">Prev close: {fmtPrice(prevClose)}</p>
      )}
    </div>
  );
}

export default function LivePriceChart({ ticker, refreshSeconds = 60 }: Props) {
  const [bars, setBars] = useState<Bar[]>([]);
  const [prevClose, setPrevClose] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/companies/${ticker}/intraday?interval=5m`);
      if (!res.ok) return;
      const data = await res.json();
      setBars(data.bars ?? []);
      if (data.prev_close != null) setPrevClose(data.prev_close);
      setLastUpdated(new Date());
    } catch { /* market closed or offline */ }
    finally { setLoading(false); }
  }, [ticker]);

  useEffect(() => {
    load();
    const id = setInterval(load, refreshSeconds * 1000);
    return () => clearInterval(id);
  }, [load, refreshSeconds]);

  if (loading) {
    return <div className="h-56 flex items-center justify-center text-gray-500 text-sm animate-pulse">Loading…</div>;
  }

  if (bars.length === 0) {
    return (
      <div className="h-56 flex flex-col items-center justify-center text-gray-500 text-sm gap-1">
        <span className="text-2xl">📉</span>
        <span>No intraday data — market may be closed</span>
        <span className="text-xs text-gray-600">ASX trades Mon–Fri, 10am–4pm AEST</span>
      </div>
    );
  }

  const openPrice   = bars[0]?.open ?? bars[0]?.close ?? 0;
  const currentPrice = bars[bars.length - 1]?.close ?? 0;

  // Primary reference: prev close (vs yesterday). Fallback: today's open.
  const ref = prevClose ?? openPrice;
  const changePct = ref ? pctFromRef(currentPrice, ref) ?? 0 : 0;
  const changeAbs = currentPrice - ref;
  const isUp = changePct >= 0;

  const prices = bars.map(b => b.close).filter((p): p is number => p !== null);
  const allPrices = prevClose ? [...prices, prevClose] : prices;
  const minP = Math.min(...allPrices);
  const maxP = Math.max(...allPrices);
  const pad = (maxP - minP) * 0.15 || openPrice * 0.05 || 0.001;

  const labelEvery = Math.max(1, Math.floor(bars.length / 6));

  const chartData = bars.map((b, i) => ({
    time: fmtTime(b.time),
    price: b.close,
    showLabel: i === 0 || i === bars.length - 1 || i % labelEvery === 0,
  }));

  const colour    = isUp ? "#10B981" : "#EF4444";
  const colourFade = isUp ? "#10B98120" : "#EF444420";

  return (
    <div className="space-y-4">
      {/* Price header */}
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div className="flex items-end gap-4">
          <div>
            <div className="text-xs text-gray-500 mb-1">Current price</div>
            <div className="text-4xl font-bold font-mono text-white tracking-tight">
              {fmtPrice(currentPrice)}
            </div>
          </div>
          <div className={`text-xl font-bold font-mono mb-1 ${isUp ? "text-emerald-400" : "text-red-400"}`}>
            {isUp ? "▲" : "▼"} {Math.abs(changePct).toFixed(1)}%
            <span className="text-sm font-normal ml-1 opacity-70">
              ({isUp ? "+" : ""}{fmtPrice(changeAbs)})
            </span>
            {prevClose && (
              <span className="text-xs text-gray-500 font-normal ml-2 block">
                vs prev close {fmtPrice(prevClose)}
              </span>
            )}
          </div>
        </div>
        <div className="text-right text-xs text-gray-500 space-y-0.5">
          <div>Open: <span className="text-gray-300 font-mono">{fmtPrice(openPrice)}</span></div>
          <div>
            High: <span className="text-emerald-400 font-mono">{fmtPrice(Math.max(...prices))}</span>
            {"  "}Low: <span className="text-red-400 font-mono">{fmtPrice(Math.min(...prices))}</span>
          </div>
          {lastUpdated && <div className="mt-0.5">Live · {format(lastUpdated, "HH:mm:ss")} · refreshes {refreshSeconds}s</div>}
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={chartData} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`grad-${ticker}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colour} stopOpacity={0.3} />
              <stop offset="100%" stopColor={colour} stopOpacity={0} />
            </linearGradient>
          </defs>

          {/* Prev close reference line — the most important visual anchor */}
          {prevClose != null && (
            <ReferenceLine
              y={prevClose}
              stroke="#F59E0B"
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{
                value: `Prev close ${fmtPrice(prevClose)}`,
                position: "insideTopRight",
                fill: "#F59E0B",
                fontSize: 10,
              }}
            />
          )}

          {/* Today's open — secondary reference */}
          {openPrice !== prevClose && (
            <ReferenceLine
              y={openPrice}
              stroke="#4B5563"
              strokeDasharray="3 3"
              strokeWidth={1}
              label={{
                value: `Open ${fmtPrice(openPrice)}`,
                position: "insideBottomRight",
                fill: "#6B7280",
                fontSize: 9,
              }}
            />
          )}

          <XAxis
            dataKey="time"
            tick={{ fill: "#6B7280", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval={labelEvery - 1}
          />
          <YAxis
            domain={[minP - pad, maxP + pad]}
            tick={{ fill: "#6B7280", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => fmtPrice(Number(v))}
            width={60}
          />
          <Tooltip
            content={<ChartTooltip prevClose={prevClose} colour={colour} />}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke={colour}
            strokeWidth={2}
            fill={`url(#grad-${ticker})`}
            dot={false}
            activeDot={{ r: 4, fill: colour, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>

      <div className="text-xs text-gray-600 text-center">
        Intraday 5-min bars · {bars.length} bars today · Data via Yahoo Finance
      </div>
    </div>
  );
}
