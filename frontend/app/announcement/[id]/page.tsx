import { format } from "date-fns";
import Link from "next/link";
import { api } from "../../../lib/api";
import ImportanceBadge from "../../../components/ImportanceBadge";
import PriceMove from "../../../components/PriceMove";
import AnnouncementTypeBadge from "../../../components/AnnouncementTypeBadge";

export default async function AnnouncementDetailPage({ params }: { params: { id: string } }) {
  let ann;
  try {
    ann = await api.announcement(Number(params.id));
  } catch {
    return (
      <div className="card text-center py-16">
        <p className="text-gray-400">Announcement not found.</p>
        <Link href="/announcements" className="text-emerald-400 text-sm mt-2 inline-block">← Back</Link>
      </div>
    );
  }

  const keyNumbers = ann.key_numbers ? JSON.parse(ann.key_numbers) : [];

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <Link href="/announcements" className="hover:text-gray-200">Announcements</Link>
        <span>/</span>
        <Link href={`/company/${ann.ticker}`} className="text-emerald-400 hover:text-emerald-300">{ann.ticker}</Link>
        <span>/</span>
        <span className="text-gray-300 truncate">{ann.title}</span>
      </div>

      <div className="card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 flex-wrap mb-2">
              <Link href={`/company/${ann.ticker}`} className="font-mono text-xl font-bold text-emerald-400 hover:text-emerald-300">
                {ann.ticker}
              </Link>
              <AnnouncementTypeBadge type={ann.announcement_type} />
              <ImportanceBadge score={ann.importance_score} />
            </div>
            <h1 className="text-xl font-semibold text-white leading-snug">{ann.title}</h1>
            <div className="flex items-center gap-4 mt-2 text-sm text-gray-400">
              <span>{ann.company_name}</span>
              {ann.sector && <span className="text-gray-500">· {ann.sector}</span>}
              <span>· {format(new Date(ann.announcement_datetime), "d MMM yyyy, HH:mm")}</span>
              {ann.page_count && <span>· {ann.page_count}pp</span>}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-xs text-gray-500 mb-1">Price move</div>
            <PriceMove pct={ann.price_move_pct} />
            {ann.abnormal_move_pct !== null && (
              <div className="text-xs text-gray-500 mt-1">vs market: <PriceMove pct={ann.abnormal_move_pct} /></div>
            )}
          </div>
        </div>
      </div>

      {/* One-sentence summary */}
      {ann.summary_short && (
        <div className="card border-l-4 border-l-emerald-500">
          <p className="text-gray-100 font-medium">{ann.summary_short}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Detailed summary */}
        {ann.summary_detailed && (
          <div className="card">
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Summary</h2>
            <div className="text-sm text-gray-200 whitespace-pre-line leading-relaxed">{ann.summary_detailed}</div>
          </div>
        )}

        {/* Why it matters */}
        {ann.why_it_matters && (
          <div className="card">
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Why It Matters</h2>
            <p className="text-sm text-gray-200">{ann.why_it_matters}</p>
            {ann.importance_reason && (
              <p className="text-xs text-gray-500 mt-2 italic">{ann.importance_reason}</p>
            )}
          </div>
        )}

        {/* Market impact */}
        {ann.market_impact && (
          <div className="card">
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Likely Market Impact</h2>
            <p className="text-sm text-gray-200">{ann.market_impact}</p>
          </div>
        )}

        {/* Key numbers */}
        {keyNumbers.length > 0 && (
          <div className="card">
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Key Numbers</h2>
            <ul className="space-y-1">
              {keyNumbers.map((n: string, i: number) => (
                <li key={i} className="text-sm text-gray-200 font-mono">{n}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Risks */}
        {ann.risks_caveats && (
          <div className="card">
            <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Risks &amp; Caveats</h2>
            <p className="text-sm text-gray-300">{ann.risks_caveats}</p>
          </div>
        )}
      </div>

      {/* Source link */}
      {ann.source_url && (
        <div className="card flex items-center justify-between">
          <span className="text-sm text-gray-400">Original announcement</span>
          <a
            href={ann.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-400 hover:text-blue-300"
          >
            Open PDF / Source →
          </a>
        </div>
      )}

      {/* Raw text */}
      {ann.cleaned_text && (
        <details className="card">
          <summary className="text-sm text-gray-400 cursor-pointer hover:text-gray-200">
            Full announcement text
          </summary>
          <pre className="mt-3 text-xs text-gray-400 whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
            {ann.cleaned_text}
          </pre>
        </details>
      )}
    </div>
  );
}
