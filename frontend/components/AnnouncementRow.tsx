import Link from "next/link";
import { format } from "date-fns";
import { Announcement } from "../lib/api";
import ImportanceBadge from "./ImportanceBadge";
import PriceMove from "./PriceMove";
import AnnouncementTypeBadge from "./AnnouncementTypeBadge";

export default function AnnouncementRow({ ann }: { ann: Announcement }) {
  return (
    <tr className="border-b border-gray-800 hover:bg-gray-800/40 transition-colors">
      <td className="px-3 py-3 text-xs text-gray-400 whitespace-nowrap">
        {format(new Date(ann.announcement_datetime), "HH:mm")}
      </td>
      <td className="px-3 py-3">
        <Link href={`/company/${ann.ticker}`} className="font-mono font-bold text-emerald-400 hover:text-emerald-300">
          {ann.ticker}
        </Link>
      </td>
      <td className="px-3 py-3 text-sm text-gray-300 hidden md:table-cell">{ann.company_name}</td>
      <td className="px-3 py-3 max-w-xs">
        <Link href={`/announcement/${ann.id}`} className="text-sm text-gray-100 hover:text-white line-clamp-2">
          {ann.title}
        </Link>
        {ann.summary_short && (
          <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{ann.summary_short}</p>
        )}
      </td>
      <td className="px-3 py-3 hidden lg:table-cell">
        <AnnouncementTypeBadge type={ann.announcement_type} />
      </td>
      <td className="px-3 py-3 text-center">
        <ImportanceBadge score={ann.importance_score} />
      </td>
      <td className="px-3 py-3 text-right">
        <PriceMove pct={ann.price_move_pct} />
      </td>
    </tr>
  );
}
