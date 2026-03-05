import fs from "fs";
import path from "path";
import type { Env } from "../config/env.js";

export interface TrackEvent {
  generation_id: string;
  variant_id: string;
  event_type: "view" | "click" | "conversion";
  url?: string;
  timestamp?: string;
}

interface StoredEvents {
  events: TrackEvent[];
}

function ensureDataDir(eventsFile: string): void {
  const dir = path.dirname(eventsFile);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

export function appendEvent(env: Env, event: TrackEvent): void {
  const eventsFile = env.EVENTS_FILE;
  ensureDataDir(eventsFile);
  let data: StoredEvents = { events: [] };
  if (fs.existsSync(eventsFile)) {
    const raw = fs.readFileSync(eventsFile, "utf8");
    try {
      data = JSON.parse(raw) as StoredEvents;
    } catch {
      data = { events: [] };
    }
  }
  data.events.push({
    ...event,
    timestamp: event.timestamp ?? new Date().toISOString(),
  });
  fs.writeFileSync(eventsFile, JSON.stringify(data, null, 0), "utf8");
}

export interface VariantMetrics {
  generation_id: string;
  variant_id: string;
  views: number;
  clicks: number;
  conversions: number;
  conversion_rate: number;
}

export interface PerformanceReport {
  schema_version: number;
  generated_at: string;
  variants: VariantMetrics[];
}

export function buildReport(env: Env): PerformanceReport {
  const eventsFile = env.EVENTS_FILE;
  if (!fs.existsSync(eventsFile)) {
    return { schema_version: 1, generated_at: new Date().toISOString(), variants: [] };
  }
  const raw = fs.readFileSync(eventsFile, "utf8");
  let data: StoredEvents;
  try {
    data = JSON.parse(raw) as StoredEvents;
  } catch {
    return { schema_version: 1, generated_at: new Date().toISOString(), variants: [] };
  }

  const byKey = new Map<string, { views: number; clicks: number; conversions: number }>();

  for (const e of data.events) {
    const key = `${e.generation_id}:${e.variant_id}`;
    let m = byKey.get(key);
    if (!m) {
      m = { views: 0, clicks: 0, conversions: 0 };
      byKey.set(key, m);
    }
    if (e.event_type === "view") m.views += 1;
    else if (e.event_type === "click") m.clicks += 1;
    else if (e.event_type === "conversion") m.conversions += 1;
  }

  const variants: VariantMetrics[] = [];
  for (const [key, m] of byKey) {
    const [generation_id, variant_id] = key.split(":");
    variants.push({
      generation_id,
      variant_id,
      views: m.views,
      clicks: m.clicks,
      conversions: m.conversions,
      conversion_rate: m.views > 0 ? m.conversions / m.views : 0,
    });
  }

  return {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    variants,
  };
}

export async function sendReportToGenerator(env: Env, report: PerformanceReport): Promise<boolean> {
  const url = env.GENERATOR_REPORT_URL?.trim();
  if (!url) return false;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  });
  return res.ok;
}

export function clearEventsAfterReport(env: Env): void {
  const eventsFile = env.EVENTS_FILE;
  if (fs.existsSync(eventsFile)) fs.writeFileSync(eventsFile, JSON.stringify({ events: [] }), "utf8");
}
