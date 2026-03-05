/**
 * Run npm run build on the export bundle; on failure parse errors, fix the offending files, and retry.
 * Returns the (possibly fixed) files and success, or the last error after max retries.
 */
import { spawnSync } from "child_process";
import fs from "fs";
import os from "os";
import path from "path";

const MAX_RETRIES = 5;
const NPM_INSTALL_TIMEOUT_MS = 120_000;
const NPM_BUILD_TIMEOUT_MS = 180_000;

export interface BuildWithRetryResult {
  ok: boolean;
  files?: Record<string, string>;
  error?: string;
  lastStderr?: string;
  attempts?: number;
  /** When true, automatic fixes were exhausted; caller may apply custom fixes to `files` and retry. */
  automaticFixesExhausted?: boolean;
}

/** Normalize variant TSX so it runs on Vercel: BOM strip, font names, "use client" at top */
function fixVariantTsx(content: string): string {
  let s = (content || "").replace(/\ufeff/g, "").trim();
  if (!s) return content || "";
  s = s.replace(/\bSource_Sans_Pro\b/g, "Source_Sans_3").replace(/\bNunito_Sans\b/g, "Nunito");
  const lower = s.slice(0, 30).toLowerCase();
  if (lower.includes('"use client"') || lower.includes("'use client'")) {
    const first = s.indexOf("\n");
    const rest = first >= 0 ? s.slice(first + 1).trimStart() : "";
    return '"use client";\n\n' + (rest ? rest + "\n" : "");
  }
  return '"use client";\n\n' + s;
}

/** Ensure Script import exists (for "Script is not defined" errors) */
function ensureScriptImport(content: string): string {
  if (/from\s+['"]next\/script['"]/i.test(content) || /import\s+.*Script.*next\/script/i.test(content)) return content;
  const lines = content.split("\n");
  let lastImport = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*import\s/.test(lines[i])) lastImport = i;
  }
  const scriptLine = 'import Script from "next/script";';
  if (lastImport >= 0) {
    lines.splice(lastImport + 1, 0, scriptLine);
    return lines.join("\n");
  }
  return scriptLine + "\n\n" + content;
}

/** Parse build stderr for affected file paths (e.g. ./app/variants/variant-2.tsx) */
function parseAffectedPaths(stderr: string): string[] {
  const paths: string[] = [];
  const variantMatch = stderr.matchAll(/(?:^|\s)(\.\/)?(app\/variants\/variant-\d+\.tsx)/gm);
  for (const m of variantMatch) {
    const p = m[2];
    if (p && !paths.includes(p)) paths.push(p);
  }
  if (paths.length > 0) return paths;
  const anyTsx = stderr.match(/(?:^|\s)(\.\/)?(app\/[^\s]+\.tsx)/m);
  if (anyTsx?.[2]) paths.push(anyTsx[2]);
  return paths;
}

/** Apply all fixers to a variant file */
function applyFixesToVariant(content: string, stderr: string): string {
  let s = fixVariantTsx(content);
  if (/Script\s+is\s+not\s+defined|ReferenceError.*Script/i.test(stderr)) s = ensureScriptImport(s);
  return s;
}

function writeBundle(dir: string, files: Record<string, string>): void {
  for (const [relPath, content] of Object.entries(files)) {
    const fullPath = path.join(dir, relPath);
    fs.mkdirSync(path.dirname(fullPath), { recursive: true });
    fs.writeFileSync(fullPath, content, "utf8");
  }
  if (!files["global.d.ts"]) {
    fs.writeFileSync(
      path.join(dir, "global.d.ts"),
      "declare global { interface Window { __landrightVariantId?: number; } }\nexport {};\n",
      "utf8"
    );
    const tsconfigPath = path.join(dir, "tsconfig.json");
    if (fs.existsSync(tsconfigPath)) {
      const tsconfig = JSON.parse(fs.readFileSync(tsconfigPath, "utf8"));
      tsconfig.include = [...(tsconfig.include || []), "global.d.ts"];
      fs.writeFileSync(tsconfigPath, JSON.stringify(tsconfig, null, 2), "utf8");
    }
  }
}

function runBuild(dir: string): { success: boolean; stderr: string; stdout: string; combined: string } {
  const install = spawnSync("npm", ["install"], {
    cwd: dir,
    encoding: "utf8",
    timeout: NPM_INSTALL_TIMEOUT_MS,
  });
  if (install.status !== 0) {
    const se = install.stderr || install.error?.message || "";
    const so = install.stdout || "";
    return { success: false, stderr: se, stdout: so, combined: se + "\n" + so };
  }
  const build = spawnSync("npm", ["run", "build"], {
    cwd: dir,
    encoding: "utf8",
    timeout: NPM_BUILD_TIMEOUT_MS,
  });
  const stderr = (build.stderr || build.error?.message || "").trim();
  const stdout = (build.stdout || "").trim();
  return { success: build.status === 0, stderr, stdout, combined: stderr + "\n" + stdout };
}

/**
 * Run npm run build; on failure parse errors, fix variant (or other) files, retry. Up to MAX_RETRIES attempts.
 */
export function buildVercelBundleWithRetry(files: Record<string, string>): BuildWithRetryResult {
  let currentFiles = { ...files };
  const dir = path.join(os.tmpdir(), `landright-vercel-build-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);

  try {
    fs.mkdirSync(dir, { recursive: true });
    let lastStderr = "";
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      writeBundle(dir, currentFiles);
      const result = runBuild(dir);
      const { success, combined } = result;
      lastStderr = result.stderr || result.combined;
      if (success) {
        return { ok: true, files: currentFiles, attempts: attempt };
      }
      const affected = parseAffectedPaths(combined);
      let pathsToFix = affected.length > 0 ? affected : [];
      if (pathsToFix.length === 0 && /Expected jsx identifier|Unexpected token\s+`/.test(combined)) {
        pathsToFix = Object.keys(currentFiles).filter((p) => /^app\/variants\/variant-\d+\.tsx$/.test(p));
      }
      // When no specific paths were parsed, try fixing all variant files so the caller has maximum chance of recovery
      if (pathsToFix.length === 0) {
        pathsToFix = Object.keys(currentFiles).filter((p) => /^app\/variants\/variant-\d+\.tsx$/.test(p));
      }
      let changed = false;
      for (const relPath of pathsToFix) {
        const content = currentFiles[relPath];
        if (content == null) continue;
        const isVariant = /^app\/variants\/variant-\d+\.tsx$/.test(relPath);
        const fixed = isVariant ? applyFixesToVariant(content, combined) : content;
        if (fixed !== content) {
          currentFiles = { ...currentFiles, [relPath]: fixed };
          changed = true;
        }
      }
      if (!changed) {
        return {
          ok: false,
          files: currentFiles,
          error:
            "Build failed; automatic fixes were exhausted. Use the returned files and lastStderr to apply custom fixes (e.g. edit and retry, or send to an agent).",
          lastStderr: (result.stderr || result.combined).slice(-4000),
          attempts: attempt,
          automaticFixesExhausted: true,
        };
      }
      // Next attempt will use currentFiles (with fixes applied)
    }
    return {
      ok: false,
      files: currentFiles,
      error: `Build still failing after ${MAX_RETRIES} attempts. Use the returned files and lastStderr to apply custom fixes.`,
      lastStderr: lastStderr.slice(-4000),
      attempts: MAX_RETRIES,
      automaticFixesExhausted: true,
    };
  } finally {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }
}
