"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { API_BASE } from "../lib/api";
import clsx from "clsx";

const links = [
  { href: "/",              label: "Home" },
  { href: "/announcements", label: "Announcements" },
];

interface ScheduleStatus {
  aest_now: string;
  market_open: boolean;
  next_run: string;
}

export default function NavBar() {
  const pathname = usePathname();
  const [status, setStatus] = useState<ScheduleStatus | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/schedule/status`);
        if (res.ok) setStatus(await res.json());
      } catch { /* backend offline */ }
    }
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/90 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 flex items-center gap-6 h-12">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <span className="text-lg">📈</span>
          <span className="font-bold text-white text-sm tracking-tight">ASX Intel</span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                pathname === l.href
                  ? "bg-emerald-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              )}
            >
              {l.label}
            </Link>
          ))}
        </div>

        {/* Market status */}
        <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
          {status ? (
            <>
              <span
                className={clsx(
                  "inline-flex items-center gap-1.5 px-2 py-1 rounded-full font-medium",
                  status.market_open
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-gray-800 text-gray-500"
                )}
              >
                <span className={clsx("w-1.5 h-1.5 rounded-full", status.market_open ? "bg-emerald-400 animate-pulse" : "bg-gray-600")} />
                {status.market_open ? "Market Open" : "Market Closed"}
              </span>
              <span className="hidden sm:block">Next run: {status.next_run}</span>
            </>
          ) : (
            <span className="text-gray-700">—</span>
          )}
        </div>
      </div>
    </nav>
  );
}
