import clsx from "clsx";

export default function PriceMove({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-gray-500 text-xs">—</span>;
  const positive = pct >= 0;
  return (
    <span className={clsx("font-mono text-sm font-medium", positive ? "text-emerald-400" : "text-red-400")}>
      {positive ? "+" : ""}{pct.toFixed(2)}%
    </span>
  );
}
