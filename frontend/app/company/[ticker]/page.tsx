import { format } from "date-fns";
import Link from "next/link";
import { api } from "../../../lib/api";
import ImportanceBadge from "../../../components/ImportanceBadge";
import PriceMove from "../../../components/PriceMove";
import AnnouncementTypeBadge from "../../../components/AnnouncementTypeBadge";

export default async function CompanyPage({ params }: { params: { ticker: string } }) {
  const ticker = params.ticker.toUpperCase();

  const [anns, prices] = await Promise.allSettled([
    api.companyAnnouncements(ticker),
    api.companyPrices(ticker),
  ]);

  const announcements = anns.status === "fulfilled" ? anns.value : [];
  const priceHistory = prices.status === "fulfilled" ? prices.value : [];
  const latest = priceHistory[0];

  return (
    <div className="space-y-5 max-w-5xl">
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <Link href="/announcements" className="hover:text-gray-200">Announcements</Link>
        <span>/</span>
        <span className="text-emerald-400">{ticker}</span>
      </div>

      {/* Company header */}
      <div className="card">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">{ticker}</h1>
            {announcements[0] && (
              <p className="text-gray-400 mt-0.5">{announcements[0].company_name}</p>
            )}
            {announcements[0]?.sector && (
              <span className="badge bg-gray-700 text-gray-300 mt-2">{announcements[0].sector}</span>
            )}
          </div>
          {latest && (
            <div className="text-right">
              <div className="text-2xl font-mono font-bold text-white">
                ${latest.close?.toFixed(3)}
              </div>
              <PriceMove pct={latest.daily_move_pct} />
              <div className="text-xs text-gray-500 mt-1">
                Vol: {latest.volume_spike_ratio !== null ? `${latest.volume_spike_ratio?.toFixed(1)}× avg` : "—"}
              </div>
              <div className="text-xs text-gray-500">
                {format(new Date(latest.date), "d MMM yyyy")}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Price history mini-chart placeholder */}
      {priceHistory.length > 1 && (
        <div className="card">
          <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-3">Recent Price History</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="px-2 pb-1.5">Date</th>
                  <th className="px-2 pb-1.5 text-right">Close</th>
                  <th className="px-2 pb-1.5 text-right">Move</th>
                  <th className="px-2 pb-1.5 text-right">Vol spike</th>
                </tr>
              </thead>
              <tbody>
                {priceHistory.slice(0, 20).map((p) => (
                  <tr key={p.id} className="border-b border-gray-800 hover:bg-gray-800/30">
                    <td className="px-2 py-1.5 text-gray-400">{format(new Date(p.date), "d MMM yy")}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-gray-200">${p.close?.toFixed(3)}</td>
                    <td className="px-2 py-1.5 text-right"><PriceMove pct={p.daily_move_pct} /></td>
                    <td className="px-2 py-1.5 text-right text-gray-400">
                      {p.volume_spike_ratio ? `${p.volume_spike_ratio.toFixed(1)}×` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Announcements */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-3">
          Announcements ({announcements.length})
        </h2>
        {announcements.length === 0 ? (
          <p className="text-gray-500 text-sm">No announcements found for {ticker}.</p>
        ) : (
          <div className="space-y-2">
            {announcements.map((ann) => (
              <Link
                key={ann.id}
                href={`/announcement/${ann.id}`}
                className="flex items-start gap-3 p-3 rounded-lg hover:bg-gray-800 transition-colors group"
              >
                <div className="flex flex-col items-center gap-1 shrink-0 w-12">
                  <ImportanceBadge score={ann.importance_score} />
                  <span className="text-xs text-gray-500">{format(new Date(ann.announcement_datetime), "d MMM")}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <AnnouncementTypeBadge type={ann.announcement_type} />
                  </div>
                  <p className="text-sm text-gray-200 group-hover:text-white line-clamp-1">{ann.title}</p>
                  {ann.summary_short && (
                    <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{ann.summary_short}</p>
                  )}
                </div>
                <PriceMove pct={ann.price_move_pct} />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
