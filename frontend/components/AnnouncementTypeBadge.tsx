import clsx from "clsx";

const TYPE_COLORS: Record<string, string> = {
  "Guidance Upgrade": "bg-emerald-500/20 text-emerald-300",
  "Guidance Downgrade": "bg-red-500/20 text-red-300",
  "M&A / Takeover": "bg-purple-500/20 text-purple-300",
  "Capital Raising": "bg-blue-500/20 text-blue-300",
  "Earnings / Trading Update": "bg-sky-500/20 text-sky-300",
  "Contract Win": "bg-teal-500/20 text-teal-300",
  "Asset Sale / Acquisition": "bg-indigo-500/20 text-indigo-300",
  "Dividend / Buyback": "bg-amber-500/20 text-amber-300",
  "Management Change": "bg-orange-500/20 text-orange-300",
  "Exploration / Drilling Results": "bg-lime-500/20 text-lime-300",
  "Regulatory / Legal": "bg-rose-500/20 text-rose-300",
  "Investor Presentation": "bg-gray-500/20 text-gray-400",
  "Appendix / Administrative": "bg-gray-700/50 text-gray-500",
  Other: "bg-gray-700/50 text-gray-500",
};

export default function AnnouncementTypeBadge({ type }: { type: string | null }) {
  const t = type ?? "Other";
  return (
    <span className={clsx("badge border border-white/5", TYPE_COLORS[t] ?? TYPE_COLORS.Other)}>
      {t}
    </span>
  );
}
