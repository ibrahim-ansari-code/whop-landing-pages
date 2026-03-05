"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import { GENERATE_API_BASE } from "@/lib/config";

/** Max screenshot size (base64 data URL length). Vision APIs often limit to ~5MB; keep under 4MB. */
const MAX_SCREENSHOT_LENGTH = 4 * 1024 * 1024;
const MAX_DIMENSION = 1920;

/**
 * Compress image data URL to fit under MAX_SCREENSHOT_LENGTH (resize + JPEG). Resolves with the
 * (possibly compressed) data URL.
 */
function compressImageIfNeeded(dataUrl: string): Promise<string> {
  if (dataUrl.length <= MAX_SCREENSHOT_LENGTH) return Promise.resolve(dataUrl);
  return new Promise((resolve, reject) => {
    const img = new window.Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Canvas not supported"));
        return;
      }
      let w = img.width;
      let h = img.height;
      if (w > MAX_DIMENSION || h > MAX_DIMENSION) {
        if (w > h) {
          h = Math.round((h * MAX_DIMENSION) / w);
          w = MAX_DIMENSION;
        } else {
          w = Math.round((w * MAX_DIMENSION) / h);
          h = MAX_DIMENSION;
        }
      }
      const qualities = [0.9, 0.75, 0.6, 0.45, 0.3];
      for (const q of qualities) {
        canvas.width = w;
        canvas.height = h;
        ctx.drawImage(img, 0, 0, w, h);
        const jpeg = canvas.toDataURL("image/jpeg", q);
        if (jpeg.length <= MAX_SCREENSHOT_LENGTH) {
          resolve(jpeg);
          return;
        }
      }
      while (w > 400 || h > 300) {
        w = Math.max(400, Math.round(w * 0.7));
        h = Math.max(300, Math.round(h * 0.7));
        canvas.width = w;
        canvas.height = h;
        ctx.drawImage(img, 0, 0, w, h);
        const jpeg = canvas.toDataURL("image/jpeg", 0.5);
        if (jpeg.length <= MAX_SCREENSHOT_LENGTH) {
          resolve(jpeg);
          return;
        }
      }
      reject(new Error("Image too large to compress to limit"));
    };
    img.onerror = () => reject(new Error("Failed to load image"));
    img.src = dataUrl;
  });
}

type InspirationData = Record<string, unknown>;

interface InspirationPanelProps {
  onInspirationChange: (data: InspirationData | null) => void;
}

export function InspirationPanel({ onInspirationChange }: InspirationPanelProps) {
  const [screenshotDataUrl, setScreenshotDataUrl] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [scanned, setScanned] = useState(false);
  const [palette, setPalette] = useState<string[]>([]);
  const [conversionDrivers, setConversionDrivers] = useState<string[]>([]);
  const [themeOverrides, setThemeOverrides] = useState<Record<string, unknown> | null>(null);
  const [scanSummary, setScanSummary] = useState<{ sections: number; triggers: number; elements: number }>({ sections: 0, triggers: 0, elements: 0 });
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function clearScreenshot() {
    setScreenshotDataUrl(null);
    setScanned(false);
    setWarning(null);
    onInspirationChange(null);
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith("image/")) return;
    setError(null);
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      compressImageIfNeeded(dataUrl)
        .then((url) => {
          setScreenshotDataUrl(url);
          setScanned(false);
          onInspirationChange(null);
        })
        .catch(() => setError("Could not process image. Try a different file."));
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  }

  function onPaste(e: React.ClipboardEvent) {
    const item = e.clipboardData?.items?.[0];
    if (!item || item.kind !== "file" || !item.type.startsWith("image/")) return;
    const file = item.getAsFile();
    if (!file) return;
    setError(null);
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      compressImageIfNeeded(dataUrl)
        .then((url) => {
          setScreenshotDataUrl(url);
          setScanned(false);
          onInspirationChange(null);
        })
        .catch(() => setError("Could not process image. Try a different file."));
    };
    reader.readAsDataURL(file);
  }

  function handleCancelScan() {
    if (abortRef.current) {
      abortRef.current.abort();
    }
  }

  async function handleExtract() {
    if (!screenshotDataUrl) return;
    if (!GENERATE_API_BASE) { setError("Backend URL not configured"); return; }
    abortRef.current = new AbortController();
    setExtracting(true);
    setError(null);
    setWarning(null);
    setScanned(false);
    try {
      const payload = await compressImageIfNeeded(screenshotDataUrl);
      const res = await fetch(`${GENERATE_API_BASE}/extract-design-spec`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ screenshot: payload }),
        signal: abortRef.current.signal,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof data?.detail === "string" ? data.detail : "";
        const isScreenshotSizeOrFormat =
          /too large|invalid.*image|unsupported.*format/i.test(detail);
        setError(
          isScreenshotSizeOrFormat
            ? "Image may be too large or in an unsupported format. Try a smaller screenshot (under 4 MB)."
            : detail || "Extraction failed"
        );
        return;
      }
      const inspiration = (data.inspiration ?? {}) as InspirationData;

      // Ghost Processing: the raw checklist is NOT shown to the user.
      // theme_overrides + design_system are auto-mapped by the backend.
      const ghostTheme = (data.themeOverrides ?? {}) as Record<string, unknown>;
      setThemeOverrides(ghostTheme);

      // Extract palette from ghost theme
      const pal = (ghostTheme.palette ?? []) as string[];
      setPalette(pal);

      // Conversion Drivers from backend
      const drivers = (data.conversionDrivers ?? []) as string[];
      setConversionDrivers(drivers);

      // Compute scan summary stats (ghost: user sees counts, not raw items)
      const sections = Array.isArray(inspiration.sections) ? (inspiration.sections as unknown[]).length : 0;
      const diction = (inspiration.diction ?? {}) as Record<string, unknown>;
      const triggers = Array.isArray(diction.triggers) ? (diction.triggers as unknown[]).length : 0;
      let elements = 0;
      if (Array.isArray(inspiration.sections)) {
        for (const s of inspiration.sections as Record<string, unknown>[]) {
          elements += (Array.isArray(s.elements) ? s.elements.length : 0);
          elements += (Array.isArray(s.highlights) ? s.highlights.length : 0);
        }
      }
      setScanSummary({ sections, triggers, elements });

      // Pass the full inspiration (with ghost theme_overrides) to parent
      onInspirationChange({ ...inspiration, theme_overrides: ghostTheme });
      setScanned(true);

      if (data.warnings) {
        const msg = Array.isArray(data.warnings) ? (data.warnings as string[]).join("; ") : String(data.warnings);
        setWarning(msg);
      }
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") {
        setError(null);
      } else {
        setError(e instanceof Error ? e.message : "Extraction failed");
      }
    } finally {
      setExtracting(false);
      abortRef.current = null;
    }
  }

  return (
    <div className="mt-8">
      <h3 className="text-sm font-medium text-zinc-300">Inspiration (optional)</h3>
      <p className="mt-1 text-xs text-zinc-500">
        Upload or paste a screenshot of a landing page. We&apos;ll extract the design DNA to fuel your variants.
      </p>
      <div
        className="mt-2 rounded-lg border border-dashed border-zinc-600 bg-zinc-800/50 p-4"
        onPaste={onPaste}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={onFileChange}
          className="hidden"
          key="screenshot-file"
        />
        {!screenshotDataUrl ? (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-full rounded border border-zinc-600 py-3 text-sm text-zinc-400 hover:border-zinc-500 hover:text-zinc-300 transition"
          >
            Choose image or paste (Ctrl+V)
          </button>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="relative flex items-start gap-3">
              <div className="relative h-24 w-40 shrink-0 overflow-hidden rounded border border-zinc-700 bg-zinc-900">
                <Image
                  src={screenshotDataUrl as string}
                  alt="Screenshot preview"
                  fill
                  className="object-contain"
                  unoptimized
                />
              </div>
              <div className="flex flex-1 flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-lg border border-zinc-600 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-300"
                >
                  Replace
                </button>
                <button
                  type="button"
                  onClick={clearScreenshot}
                  className="rounded-lg border border-zinc-600 px-3 py-1.5 text-xs font-medium text-red-400 hover:text-red-300"
                >
                  Remove
                </button>
                <button
                  type="button"
                  disabled={extracting}
                  onClick={handleExtract}
                  className="rounded-lg bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-100 hover:bg-zinc-600 disabled:opacity-50 transition"
                >
                  {extracting ? "Scanning…" : "Scan for inspiration"}
                </button>
                {extracting && (
                  <button
                    type="button"
                    onClick={handleCancelScan}
                    className="rounded-lg border border-zinc-600 px-4 py-2 text-sm font-medium text-zinc-400 hover:text-zinc-300"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      {warning && <p className="mt-2 text-xs text-amber-400">{warning}</p>}

      {/* Magical UI Summary: replaces raw checklist */}
      {scanned && (
        <div className="mt-4 rounded-xl border border-orange-500/30 bg-gradient-to-br from-zinc-900 to-zinc-950 p-4 space-y-4">
          {/* Scan stats */}
          <div className="flex items-center gap-3">
            <span className="text-orange-400 text-lg">&#9889;</span>
            <div>
              <p className="text-sm font-medium text-zinc-200">Design DNA captured</p>
              <p className="text-xs text-zinc-500">
                {scanSummary.sections} sections &middot; {scanSummary.elements} elements &middot; {scanSummary.triggers} persuasion triggers
              </p>
            </div>
          </div>

          {/* Palette */}
          {palette.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-zinc-500">Palette:</span>
              {palette.map((c, i) => (
                <span key={i} className="inline-block h-6 w-6 rounded-md border border-zinc-600 shadow-sm" style={{ backgroundColor: c }} title={c} />
              ))}
            </div>
          )}

          {/* Theme overrides summary */}
          {themeOverrides && (
            <div className="flex flex-wrap gap-2">
              {themeOverrides.border_radius != null ? (
                <span className="text-xs bg-zinc-800 border border-zinc-700 rounded-full px-2.5 py-1 text-zinc-300">
                  {String(themeOverrides.border_radius)}
                </span>
              ) : null}
              {themeOverrides.button_style != null ? (
                <span className="text-xs bg-zinc-800 border border-zinc-700 rounded-full px-2.5 py-1 text-zinc-300">
                  {String(themeOverrides.button_style)}
                </span>
              ) : null}
              {themeOverrides.shadow_depths != null ? (
                <span className="text-xs bg-zinc-800 border border-zinc-700 rounded-full px-2.5 py-1 text-zinc-300">
                  {String(themeOverrides.shadow_depths)}
                </span>
              ) : null}
              {themeOverrides.animation_style != null ? (
                <span className="text-xs bg-zinc-800 border border-zinc-700 rounded-full px-2.5 py-1 text-zinc-300">
                  {String(themeOverrides.animation_style)}
                </span>
              ) : null}
            </div>
          )}

          {/* Top Conversion Drivers */}
          {conversionDrivers.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-orange-300/80 uppercase tracking-wider">Top Conversion Drivers</p>
              <div className="space-y-1.5">
                {conversionDrivers.slice(0, 3).map((driver, i) => (
                  <div key={i} className="flex items-center gap-2.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-orange-500/20 text-[10px] font-bold text-orange-400">
                      {i + 1}
                    </span>
                    <span className="text-sm text-zinc-200">{driver}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-[10px] text-zinc-600 leading-tight">
            Theme overrides, design tokens, and persuasion triggers have been auto-applied. Your 4 variants will synthesize these patterns.
          </p>
        </div>
      )}
    </div>
  );
}
