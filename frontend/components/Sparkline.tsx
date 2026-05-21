"use client";

import { useEffect, useState } from "react";
import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";
import { API_BASE } from "../lib/api";

interface Props {
  ticker: string;
  positive: boolean;
}

export default function Sparkline({ ticker, positive }: Props) {
  const [data, setData] = useState<{ price: number }[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(
          `${API_BASE}/companies/${ticker}/intraday?interval=5m`
        );
        if (!res.ok) return;
        const json = await res.json();
        const bars = (json.bars ?? []) as { close: number | null }[];
        const pts = bars
          .filter((b) => b.close !== null)
          .map((b) => ({ price: b.close as number }));
        if (!cancelled) setData(pts);
      } catch {
        // silently skip — sparkline is decorative
      }
    }
    load();
    const id = setInterval(load, 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [ticker]);

  if (data.length < 2) {
    return (
      <div className="w-24 h-10 flex items-center justify-center">
        <span className="text-gray-600 text-xs">—</span>
      </div>
    );
  }

  return (
    <div className="w-24 h-10">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <YAxis domain={["auto", "auto"]} hide />
          <Line
            type="monotone"
            dataKey="price"
            stroke={positive ? "#10B981" : "#EF4444"}
            strokeWidth={1.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
