"use client";

import { useCallback, useEffect, useState } from "react";

export interface TsxPreviewProps {
  tsx: string;
  className?: string;
}

/**
 * Renders TSX landing page code by compiling it on the server (/api/preview)
 * and loading the resulting HTML in an iframe.
 */
export function TsxPreview({ tsx, className = "" }: TsxPreviewProps) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (code: string) => {
    const trimmed = (code ?? "").trim();
    if (!trimmed) {
      setHtml(null);
      setError(null);
      setLoading(false);
      return;
    }
    if (!trimmed.includes("export default")) {
      setHtml(null);
      setError("No code to preview");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setHtml(null);
    try {
      const res = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tsx: trimmed }),
      });
      const text = await res.text();
      let data: { html?: string; error?: string; details?: string };
      try {
        data = text ? (JSON.parse(text) as typeof data) : {};
      } catch {
        setError(res.ok ? "Invalid preview response" : `Preview failed (${res.status})`);
        return;
      }
      if (!res.ok) {
        setError(data?.details ?? data?.error ?? `Preview failed (${res.status})`);
        return;
      }
      if (typeof data?.html !== "string" || !data.html.trim()) {
        setError("Invalid or empty preview response");
        return;
      }
      setHtml(data.html);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load preview");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(tsx);
  }, [tsx, load]);

  if (loading) {
    return (
      <div
        className={`flex min-h-[200px] items-center justify-center rounded-lg border border-orange-500/40 bg-black/80 text-sm text-white/70 ${className}`}
      >
        Loading preview…
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`flex min-h-[200px] flex-col items-center justify-center gap-2 rounded-lg border border-orange-500/40 bg-black/80 p-6 text-center text-sm text-white/90 ${className}`}
        role="alert"
      >
        <p className="font-medium">Preview could not be loaded</p>
        <p className="max-h-32 overflow-auto text-xs text-white/60 whitespace-pre-wrap">{error}</p>
      </div>
    );
  }

  if (!html) {
    return null;
  }

  return (
    <iframe
      title="Landing page preview"
      srcDoc={html}
      className={`h-full w-full min-h-0 border-0 bg-white ${className}`}
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
    />
  );
}
