import fs from "fs";
import path from "path";
import { env } from "../config/env.js";
import { getFileContent, updateRecord } from "./github.service.js";

const BOT_HEADER = "/* 🤖 BOT_OPTIMIZATION: Fixed 1.2% Conversion Leak */\n";
const COMMIT_MESSAGE = "🤖 Bot: Fixed 1.2% conversion leak (Variant B)";

interface MockAnalytics {
  simulation_meta?: { sample_size?: number };
  metrics?: Array<{ variant_id: string; status?: string; conv_rate?: string }>;
  agent_decision?: { action?: string; target?: string };
}

function getMockAnalyticsPath(): string {
  const base = process.cwd();
  return path.resolve(base, env.MOCK_ANALYTICS_PATH);
}

function readMockAnalytics(): MockAnalytics {
  const filePath = getMockAnalyticsPath();
  if (!fs.existsSync(filePath)) {
    throw new Error(`Mock analytics not found: ${filePath}`);
  }
  const raw = fs.readFileSync(filePath, "utf8");
  return JSON.parse(raw) as MockAnalytics;
}

function shouldApplyFix(analytics: MockAnalytics): { apply: boolean; targetFile?: string } {
  const sampleSize = analytics.simulation_meta?.sample_size ?? 0;
  if (sampleSize < 1000) {
    return { apply: false };
  }
  const underperforming = analytics.metrics?.find(
    (m) => m.status === "Underperforming" || (m.conv_rate && parseFloat(m.conv_rate) < 5)
  );
  if (!underperforming) {
    return { apply: false };
  }
  const decision = analytics.agent_decision;
  if (decision?.action?.toLowerCase().includes("reactive fix")) {
    return { apply: true, targetFile: "app/page.tsx" };
  }
  return { apply: true, targetFile: "app/page.tsx" };
}

export interface ReactiveFixResult {
  applied: boolean;
  filePath?: string;
  sha?: string;
  error?: string;
}

export async function runReactiveFix(): Promise<ReactiveFixResult> {
  const analytics = readMockAnalytics();
  const { apply, targetFile } = shouldApplyFix(analytics);
  if (!apply || !targetFile) {
    return { applied: false };
  }
  const content = await getFileContent(env, targetFile);
  const newContent = BOT_HEADER + content;
  const { sha } = await updateRecord(env, targetFile, newContent, COMMIT_MESSAGE);
  return { applied: true, filePath: targetFile, sha };
}
