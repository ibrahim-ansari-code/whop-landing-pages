import fs from "fs";
import path from "path";
import * as cheerio from "cheerio";
import type { Env } from "../config/env.js";
import type { DeployFile } from "./github.service.js";

const TRACKING_SCRIPT = (baseUrl: string) => `
(function() {
  var base = "${baseUrl.replace(/\/$/, "")}";
  var gen = document.querySelector('meta[name="generation_id"]')?.getAttribute('content') || document.documentElement.getAttribute('data-generation-id') || '';
  var variant = document.querySelector('meta[name="variant_id"]')?.getAttribute('content') || document.documentElement.getAttribute('data-variant-id') || '';
  function send(eventType) {
    if (!gen || !variant) return;
    fetch(base + '/api/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ generation_id: gen, variant_id: variant, event_type: eventType, url: location.href, timestamp: new Date().toISOString() })
    }).catch(function() {});
  }
  document.addEventListener('DOMContentLoaded', function() { send('view'); });
  document.body.addEventListener('click', function(e) {
    var t = e.target.closest('a, button');
    if (!t) return;
    var eventType = (t.classList.contains('btn-buy') || t.getAttribute('data-action') === 'purchase') ? 'conversion' : 'click';
    send(eventType);
  });
})();
`;

export function getHtmlFiles(dir: string): string[] {
  const results: string[] = [];
  if (!fs.existsSync(dir)) return results;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const ent of entries) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) results.push(...getHtmlFiles(full));
    else if (ent.isFile() && ent.name.toLowerCase().endsWith(".html")) results.push(full);
  }
  return results;
}

export function instrumentHtml(htmlPath: string, htmlContent: string, agentBaseUrl: string): string {
  const $ = cheerio.load(htmlContent);
  const script = TRACKING_SCRIPT(agentBaseUrl);
  $("body").append(`<script>${script}</script>`);
  return $.html();
}

export function instrumentAll(env: Env): DeployFile[] {
  const dir = path.resolve(env.GENERATOR_OUTPUT_PATH);
  const htmlFiles = getHtmlFiles(dir);
  const baseLen = dir.length + (dir.endsWith(path.sep) ? 0 : 1);
  const out: DeployFile[] = [];

  for (const fullPath of htmlFiles) {
    const content = fs.readFileSync(fullPath, "utf8");
    const instrumented = instrumentHtml(fullPath, content, env.AGENT_BASE_URL);
    const relativePath = path.relative(dir, fullPath).replace(/\\/g, "/");
    out.push({ path: relativePath, content: instrumented });
  }

  return out;
}
