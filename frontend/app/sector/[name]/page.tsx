import { format } from "date-fns";
import Link from "next/link";
import { api, Announcement } from "../../../lib/api";
import ImportanceBadge from "../../../components/ImportanceBadge";
import PriceMove from "../../../components/PriceMove";
import AnnouncementTypeBadge from "../../../components/AnnouncementTypeBadge";

export default async function SectorPage({ params }: { params: { name: string } }) {
  const name = decodeURIComponent(params.name);
  let anns: Announcement[] = [];
  try {
    anns = await api.sectorAnnouncements(name);
  } catch {
    anns = [];
  }

  // Group by announcement type
  const byType = anns.reduce<Record<string, typeof anns>>((acc, a) => {
    const t = a.announcement_type ?? "Other";
    (acc[t] ??= []).push(a);
    return acc;
  }, {});

  return (
    <div className="space-y-5 max-w-5xl">
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <Link href="/sectors" className="hover:text-gray-200">Sectors</Link>
        <span>/</span>
        <span className="text-emerald-400">{name}</span>
      </div>

      <div className="card">
        <h1 className="text-2xl font-bold text-white">{name}</h1>
        <p className="text-gray-400 text-sm mt-1">{anns.length} announcements</p>
      </div>

      {/* Group by type */}
      {Object.entries(byType)
        .sort(([, a], [, b]) => b.length - a.length)
        .map(([type, items]) => (
          <div key={type} className="card">
            <div className="flex items-center gap-3 mb-3">
              <AnnouncementTypeBadge type={type} />
              <span className="text-xs text-gray-500">{items.length} announcement{items.length !== 1 ? "s" : ""}</span>
            </div>
            <div className="space-y-2">
              {items.slice(0, 10).map((ann) => (
                <Link
                  key={ann.id}
                  href={`/announcement/${ann.id}`}
                  className="flex items-start gap-3 p-2 rounded-lg hover:bg-gray-800 group transition-colors"
                >
                  <ImportanceBadge score={ann.importance_score} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Link href={`/company/${ann.ticker}`} className="font-mono text-xs font-bold text-emerald-400 hover:text-emerald-300" onClick={(e) => e.stopPropagation()}>
                        {ann.ticker}
                      </Link>
                      <span className="text-xs text-gray-500">{format(new Date(ann.announcement_datetime), "d MMM")}</span>
                    </div>
                    <p className="text-sm text-gray-200 group-hover:text-white line-clamp-1 mt-0.5">{ann.title}</p>
                    {ann.summary_short && (
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{ann.summary_short}</p>
                    )}
                  </div>
                  <PriceMove pct={ann.price_move_pct} />
                </Link>
              ))}
            </div>
          </div>
        ))}

      {anns.length === 0 && (
        <div className="card text-center py-12">
          <p className="text-gray-400">No announcements for {name} yet.</p>
        </div>
      )}
    </div>
  );
}
