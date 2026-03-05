"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { COPY } from "@/lib/copy";
import { STORAGE_KEYS, GENERATE_API_BASE } from "@/lib/config";

type DashboardVariant = {
  variant_id: string;
  layer?: string;
  cta_clicks: number;
  share_percent: number;
  rank?: number;
};

type DashboardEvent = {
  id?: string;
  variant_id?: string;
  cta_label?: string;
  cta_id?: string;
  occurred_at?: string;
};

type DashboardData = {
  variants: DashboardVariant[];
  totalClicks: number;
  topVariantId: string | null;
  events: DashboardEvent[];
  error?: string;
};

type VariantAnalysis = {
  sections: string[];
  ctas: string[];
  tailwindColors: string[];
  fontImports: string[];
  responsive: boolean;
  animated: boolean;
  lineCount: number;
};

function timeAgo(iso: string): string {
  try {
    const d = new Date(iso);
    const now = Date.now();
    const sec = Math.floor((now - d.getTime()) / 1000);
    if (sec < 60) return "just now";
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min} min ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr} hr ago`;
    const day = Math.floor(hr / 24);
    return `${day} day${day !== 1 ? "s" : ""} ago`;
  } catch {
    return "";
  }
}

export default function DashboardPage() {
  const [repo, setRepo] = useState("");
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [analyses, setAnalyses] = useState<VariantAnalysis[]>([]);
  const [structureLoading, setStructureLoading] = useState(false);

  const fetchDashboard = useCallback(async () => {
    const r = repo.trim();
    if (!r || !GENERATE_API_BASE) {
      setData(r ? null : { variants: [], totalClicks: 0, topVariantId: null, events: [] });
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(
        `${GENERATE_API_BASE}/dashboard-data?repo=${encodeURIComponent(r)}`
      );
      const json = (await res.json()) as DashboardData;
      setData(json);
    } catch (e) {
      setData({
        variants: [],
        totalClicks: 0,
        topVariantId: null,
        events: [],
        error: String(e),
      });
    } finally {
      setLoading(false);
    }
  }, [repo]);

  useEffect(() => {
    if (!repo.trim() || !autoRefresh) return;
    const t = setInterval(fetchDashboard, 30_000);
    return () => clearInterval(t);
  }, [repo, autoRefresh, fetchDashboard]);

  useEffect(() => {
    if (!repo.trim()) return;
    fetchDashboard();
  }, [repo, fetchDashboard]);

  const fetchStructure = useCallback(async () => {
    if (typeof window === "undefined" || !GENERATE_API_BASE) return;
    const raw = sessionStorage.getItem(STORAGE_KEYS.VARIANTS);
    let variants: string[] = [];
    try {
      if (raw) variants = JSON.parse(raw) as string[];
    } catch {
      setAnalyses([]);
      return;
    }
    if (!variants.length) {
      setAnalyses([]);
      return;
    }
    setStructureLoading(true);
    try {
      const res = await fetch(`${GENERATE_API_BASE}/analyze-variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ variants }),
      });
      const json = (await res.json()) as { analyses?: VariantAnalysis[] };
      setAnalyses(json.analyses ?? []);
    } catch {
      setAnalyses([]);
    } finally {
      setStructureLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStructure();
  }, [fetchStructure, data?.variants?.length]);

  const hasRepo = !!repo.trim();
  const variants = data?.variants ?? [];
  const totalClicks = data?.totalClicks ?? 0;
  const topVariantId = data?.topVariantId ?? null;
  const events = data?.events ?? [];
  const maxClicks = Math.max(1, ...variants.map((v) => v.cta_clicks));

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 bg-zinc-900/50 px-4 py-3">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <Link href="/" className="text-sm font-medium text-zinc-300 hover:text-white">
            ← Home
          </Link>
          <h1 className="text-lg font-semibold">{COPY.DASHBOARD.TITLE}</h1>
          <span className="w-12" />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-zinc-400">
            {COPY.DASHBOARD.REPO_LABEL}
            <input
              type="text"
              placeholder={COPY.DASHBOARD.REPO_PLACEHOLDER}
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              className="w-48 rounded border border-zinc-600 bg-zinc-900 px-3 py-2 text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
            />
          </label>
          <button
            type="button"
            onClick={() => fetchDashboard()}
            disabled={!hasRepo || loading}
            className="rounded bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-50"
          >
            {loading ? "Loading…" : COPY.DASHBOARD.REFRESH}
          </button>
          <label className="flex items-center gap-2 text-sm text-zinc-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-600 bg-zinc-800"
            />
            {COPY.DASHBOARD.AUTO_REFRESH}
          </label>
        </div>

        {!hasRepo && (
          <p className="mb-6 text-sm text-zinc-500">{COPY.DASHBOARD.EMPTY_ENTER_REPO}</p>
        )}

        <section className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-lg border border-orange-500/30 bg-orange-950/20 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-orange-400/90">
              {COPY.DASHBOARD.KPI_TOTAL_CLICKS}
            </p>
            <p className="mt-1 text-2xl font-semibold text-orange-200">{totalClicks}</p>
          </div>
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-emerald-400/90">
              {COPY.DASHBOARD.KPI_TOP_VARIANT}
            </p>
            <p className="mt-1 truncate text-2xl font-semibold text-emerald-200">
              {topVariantId ?? "—"}
            </p>
          </div>
          <div className="rounded-lg border border-blue-500/30 bg-blue-950/20 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-blue-400/90">
              {COPY.DASHBOARD.KPI_VARIANTS_TRACKED}
            </p>
            <p className="mt-1 text-2xl font-semibold text-blue-200">{variants.length}</p>
          </div>
          <div className="rounded-lg border border-violet-500/30 bg-violet-950/20 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-violet-400/90">
              {COPY.DASHBOARD.KPI_AGENT_EVENTS}
            </p>
            <p className="mt-1 text-2xl font-semibold text-violet-200">{events.length}</p>
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-4">
            <h2 className="mb-3 text-sm font-semibold text-zinc-200">
              {COPY.DASHBOARD.PANEL_CTA_PERFORMANCE}
            </h2>
            {variants.length === 0 ? (
              <p className="text-sm text-zinc-500">{COPY.DASHBOARD.EMPTY_ENTER_REPO}</p>
            ) : (
              <div className="space-y-3">
                {variants.map((v, i) => (
                  <div key={v.variant_id ?? i}>
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-zinc-300">
                        {v.variant_id ?? `Variant ${i + 1}`}
                      </span>
                      <span className="text-zinc-500">
                        {v.cta_clicks} clicks · {v.share_percent}%
                      </span>
                    </div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className="h-full rounded-full bg-amber-500/80"
                        style={{ width: `${(v.cta_clicks / maxClicks) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-4">
            <h2 className="mb-3 text-sm font-semibold text-zinc-200">
              {COPY.DASHBOARD.PANEL_WIN_RATES}
            </h2>
            {variants.length === 0 ? (
              <p className="text-sm text-zinc-500">{COPY.DASHBOARD.EMPTY_ENTER_REPO}</p>
            ) : (
              <div className="space-y-2">
                {variants.map((v, i) => (
                  <div
                    key={v.variant_id ?? i}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2 ${
                      v.rank === 1 ? "bg-emerald-900/30 ring-1 ring-emerald-500/40" : "bg-zinc-800/50"
                    }`}
                  >
                    <span
                      className={`text-sm font-bold ${
                        v.rank === 1 ? "text-emerald-400" : "text-zinc-500"
                      }`}
                    >
                      #{v.rank ?? i + 1}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-zinc-300">
                      {v.variant_id ?? `Variant ${i + 1}`}
                    </span>
                    <span className="text-sm text-zinc-400">{v.cta_clicks} clicks</span>
                    <div className="w-20 overflow-hidden rounded-full bg-zinc-700">
                      <div
                        className="h-2 rounded-full bg-emerald-500"
                        style={{ width: `${(v.cta_clicks / maxClicks) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-4">
            <h2 className="mb-3 text-sm font-semibold text-zinc-200">
              {COPY.DASHBOARD.PANEL_STRUCTURE}
            </h2>
            <p className="mb-2 text-xs text-zinc-500">From your last Generate session (browser storage).</p>
            {structureLoading ? (
              <p className="text-sm text-zinc-500">Analyzing variants…</p>
            ) : analyses.length === 0 ? (
              <p className="text-sm text-zinc-500">{COPY.DASHBOARD.EMPTY_NO_VARIANTS}</p>
            ) : (
              <div className="space-y-4">
                {analyses.map((a, i) => (
                  <div key={i} className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
                    <p className="mb-2 text-xs font-medium text-zinc-400">Variant {i + 1}</p>
                    <div className="flex flex-wrap gap-1">
                      {a.sections.map((s) => (
                        <span
                          key={s}
                          className="rounded bg-zinc-700 px-2 py-0.5 text-xs text-zinc-300"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                    {a.ctas.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {a.ctas.slice(0, 8).map((c) => (
                          <span
                            key={c}
                            className="rounded bg-amber-900/50 px-2 py-0.5 text-xs text-amber-200"
                          >
                            {c}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-500">
                      {a.tailwindColors.slice(0, 5).map((c) => (
                        <span key={c}>{c}</span>
                      ))}
                      {a.fontImports.length > 0 && (
                        <span className="text-zinc-400">Fonts: {a.fontImports.join(", ")}</span>
                      )}
                      {a.responsive && (
                        <span className="rounded bg-blue-900/40 px-1.5 py-0.5 text-blue-300">
                          Responsive
                        </span>
                      )}
                      {a.animated && (
                        <span className="rounded bg-violet-900/40 px-1.5 py-0.5 text-violet-300">
                          Animated
                        </span>
                      )}
                      <span>{a.lineCount} lines</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-zinc-700 bg-zinc-900/50 p-4">
            <h2 className="mb-3 text-sm font-semibold text-zinc-200">
              {COPY.DASHBOARD.PANEL_AGENT_LOG}
            </h2>
            {events.length === 0 ? (
              <p className="text-sm text-zinc-500">{COPY.DASHBOARD.EMPTY_NO_EVENTS}</p>
            ) : (
              <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                {events.map((ev, i) => (
                  <div
                    key={ev.id ?? i}
                    className="flex items-start gap-2 rounded-lg border border-zinc-700/80 bg-zinc-800/50 px-3 py-2"
                  >
                    <span
                      className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-violet-400"
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1 text-sm">
                      <span className="text-zinc-300">
                        {ev.cta_label ?? ev.variant_id ?? "CTA click"}
                      </span>
                      {ev.variant_id && (
                        <span className="ml-1 text-zinc-500">· {ev.variant_id}</span>
                      )}
                      {ev.occurred_at && (
                        <p className="mt-0.5 text-xs text-zinc-500">
                          {timeAgo(ev.occurred_at)}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
