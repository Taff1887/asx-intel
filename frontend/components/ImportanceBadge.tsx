import clsx from "clsx";

export default function ImportanceBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-gray-500 text-xs">—</span>;
  const s = Math.round(score);
  const color =
    s >= 8 ? "bg-red-500/20 text-red-400 border border-red-500/30" :
    s >= 6 ? "bg-orange-500/20 text-orange-400 border border-orange-500/30" :
    s >= 4 ? "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30" :
    "bg-gray-700 text-gray-400";
  return (
    <span className={clsx("badge font-mono text-xs", color)}>
      {score.toFixed(1)}
    </span>
  );
}
