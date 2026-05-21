import Link from "next/link";
import { api } from "../../lib/api";

export default async function SectorsPage() {
  let sectors: { id: number; name: string; description: string | null }[] = [];
  try {
    sectors = await api.sectors();
  } catch {}

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-white">Sectors</h1>
      {sectors.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-gray-400">No sectors yet. Run ingestion first.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sectors.map((s) => (
            <Link
              key={s.id}
              href={`/sector/${encodeURIComponent(s.name)}`}
              className="card hover:border-emerald-500/40 transition-colors group"
            >
              <h2 className="text-lg font-semibold text-white group-hover:text-emerald-400 transition-colors">
                {s.name}
              </h2>
              {s.description && <p className="text-sm text-gray-400 mt-1">{s.description}</p>}
              <p className="text-xs text-gray-500 mt-2">View announcements →</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
