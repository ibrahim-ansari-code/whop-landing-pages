/**
 * Shared compile and validation for TSX landing pages.
 * Used by /api/preview and /api/validate-tsx, and by tests.
 */
import * as esbuild from "esbuild";
import * as ts from "typescript";
import { transformTsxForPreview, stripTypesForJsx, PREVIEW_FONT_STUB } from "@/lib/preview-transform";

const PREVIEW_ENTRY = `
import React from 'react';
import ReactDOM from 'react-dom/client';
import Page from 'preview-page';
var root = document.getElementById('root');
if (root) ReactDOM.createRoot(root).render(React.createElement(Page));
`;

export function looksLikeTsx(code: string): boolean {
  const t = (code ?? "").trim();
  return t.length > 0 && t.includes("export default") && !t.startsWith("<!DOCTYPE") && !t.startsWith("<html");
}

/** Check if TSX uses Tailwind responsive prefixes (mobile-friendly signal). */
export function hasResponsiveClasses(tsx: string): boolean {
  return /sm:|md:|lg:|xl:|min-|max-|viewport|@media/i.test(tsx);
}

const PREVIEW_PAGE_VIRTUAL = "preview-page.tsx";

/**
 * Early syntax check to catch "Unterminated string literal" and other parse errors
 * before esbuild runs. Returns a user-friendly error message so we can fail fast.
 */
export function checkTsxSyntax(tsx: string): { ok: true } | { ok: false; message: string } {
  const sourceFile = ts.createSourceFile(
    PREVIEW_PAGE_VIRTUAL,
    tsx,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX
  );
  const compilerHost: ts.CompilerHost = {
    getSourceFile: (fileName) =>
      fileName === PREVIEW_PAGE_VIRTUAL ? sourceFile : undefined,
    getCurrentDirectory: () => "/",
    getCanonicalFileName: (f) => f,
    useCaseSensitiveFileNames: () => true,
    getNewLine: () => "\n",
    fileExists: (f) => f === PREVIEW_PAGE_VIRTUAL,
    readFile: () => "",
    getDefaultLibFileName: () => "lib.d.ts",
    writeFile: () => {},
  };
  const program = ts.createProgram([PREVIEW_PAGE_VIRTUAL], {}, compilerHost);
  const diagnostics = program.getSyntacticDiagnostics(sourceFile);
  const first = diagnostics[0];
  if (!first) return { ok: true };
  const message = ts.flattenDiagnosticMessageText(first.messageText, "\n");
  if (/unterminated\s+string\s+literal/i.test(message)) {
    return {
      ok: false,
      message:
        "Unterminated string literal in your code. Check that every string and JSX attribute value is properly closed (matching \" or ').",
    };
  }
  return { ok: false, message };
}

/** Check for browser-unsafe patterns that would break in standalone run. */
export function hasBrowserUnsafePatterns(tsx: string): boolean {
  return /require\s*\(|process\.env|import\s+.*from\s+['"]node:|from\s+['"]path['"]/i.test(tsx);
}

/** Extract href and data-url string literal URLs from TSX (for same-buttons check). */
export function extractHrefUrls(tsx: string): string[] {
  const urls: string[] = [];
  // href="...", href='...', href={"..."}, href={'...'}, href={"..."/>
  const hrefRe = /href\s*=\s*\{?\s*["']([^"']+)["']\s*\}?/g;
  let m: RegExpExecArray | null;
  while ((m = hrefRe.exec(tsx)) !== null) {
    urls.push(m[1].trim());
  }
  // data-url="..." (e.g. Calendly)
  const dataUrlRe = /data-url\s*=\s*\{?\s*["']([^"']+)["']\s*\}?/g;
  while ((m = dataUrlRe.exec(tsx)) !== null) {
    urls.push(m[1].trim());
  }
  return urls;
}

/** Check that TSX uses exactly the same CTA URLs as the spec (no extra, no missing). contact_form has no href so we skip it. */
export function checkSameButtons(
  tsx: string,
  spec: { ctaEntries?: Array<{ url: string; type?: string }> } | null
): boolean {
  const entries = spec?.ctaEntries;
  if (!entries || entries.length === 0) return true;
  const specUrls = new Set(
    entries
      .filter((e) => e.type !== "contact_form")
      .map((e) => (e.url || "").trim())
      .filter((u) => u && u !== "#")
  );
  const found = extractHrefUrls(tsx);
  const foundSet = new Set(found.filter((u) => u && u !== "#"));
  if (specUrls.size !== foundSet.size) return false;
  for (const u of foundSet) {
    if (!specUrls.has(u)) return false;
  }
  return true;
}

export interface CompileResult {
  ok: true;
  html: string;
}
export interface CompileError {
  ok: false;
  error: string;
}

export async function compileTsxToHtml(tsx: string): Promise<CompileResult | CompileError> {
  if (!looksLikeTsx(tsx)) {
    return { ok: false, error: "Invalid tsx: expected a component with export default" };
  }
  const syntaxCheck = checkTsxSyntax(tsx);
  if (!syntaxCheck.ok) {
    return { ok: false, error: syntaxCheck.message };
  }
  let transformed = transformTsxForPreview(tsx);
  transformed = stripTypesForJsx(transformed);

  let previewPageSource: { code: string; loader: "js" | "jsx" };
  try {
    const result = ts.transpileModule(transformed, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2020,
        jsx: ts.JsxEmit.React,
        moduleResolution: ts.ModuleResolutionKind.Bundler,
      },
      reportDiagnostics: false,
    });
    const emitted = result.outputText?.trim();
    if (emitted) {
      previewPageSource = { code: emitted, loader: "js" };
    } else {
      previewPageSource = { code: stripTypesForJsx(transformed), loader: "jsx" };
    }
  } catch {
    previewPageSource = { code: stripTypesForJsx(transformed), loader: "jsx" };
  }

  // Ensure React is in scope exactly once. Remove every React default/namespace import
  // from the page code (any format) to avoid "The symbol React has already been declared".
  // Use a single full-string replace so we catch all formats (single/multiline, straight/curly quotes).
  let codeForBundle = previewPageSource.code
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
  // Remove any "import React from 'react'" or "import * as React from 'react'" (single line; allow straight or curly quotes)
  const reactImportPattern =
    /\bimport\s+(?:React|\*\s+as\s+React)\s+from\s*["'\u201c\u201d]react["'\u201c\u201d]\s*;?\s*\n?/g;
  codeForBundle = codeForBundle.replace(reactImportPattern, "");
  // Remove "import React, { ... } from 'react'" (combined default + named)
  codeForBundle = codeForBundle.replace(
    /\bimport\s+React\s*,\s*\{[^}]*\}\s*from\s*["'\u201c\u201d]react["'\u201c\u201d]\s*;?\s*\n?/g,
    ""
  );
  // Remove "import { ... } from 'react'" (named only) so we don't duplicate useState etc.
  codeForBundle = codeForBundle.replace(
    /\bimport\s*\{[^}]*\}\s*from\s*["'\u201c\u201d]react["'\u201c\u201d]\s*;?\s*\n?/g,
    ""
  );
  // Remove multiline form: "import React\nfrom 'react';"
  codeForBundle = codeForBundle.replace(
    /\bimport\s+(?:React|\*\s+as\s+React)\s+\n\s*from\s*["'\u201c\u201d]react["'\u201c\u201d]\s*;?\s*\n?/g,
    ""
  );
  codeForBundle = codeForBundle.trimStart();
  const needsReact =
    /\bReact\./.test(codeForBundle) || /createElement\s*\(/.test(codeForBundle);
  const needsHooks =
    /\b(useState|useEffect|useCallback|useMemo|useRef)\s*\(/.test(codeForBundle);
  const reactImportLine =
    needsHooks
      ? "import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';\n"
      : "import React from 'react';\n";
  const previewPageWithReact = needsReact
    ? `${reactImportLine}${codeForBundle}`
    : codeForBundle;

  const virtualModules: Record<string, string> = {
    "preview-page": previewPageWithReact,
    "preview-font-stub": PREVIEW_FONT_STUB,
  };
  const NEXT_STUB = "export default function NextStub() { return null; };";
  const nextStubPlugin: esbuild.Plugin = {
    name: "next-stub",
    setup(build) {
      build.onResolve({ filter: /^next(\/|$)/ }, (args) => ({
        path: args.path,
        namespace: "next-stub",
      }));
      build.onLoad({ filter: /.*/, namespace: "next-stub" }, () => ({
        contents: NEXT_STUB,
        loader: "js",
      }));
    },
  };
  const virtualPlugin: esbuild.Plugin = {
    name: "virtual",
    setup(build) {
      build.onResolve({ filter: /^preview-(page|font-stub)$/ }, (args) => ({
        path: args.path,
        namespace: "virtual",
      }));
      build.onLoad({ filter: /.*/, namespace: "virtual" }, (args) => {
        const code = virtualModules[args.path];
        if (args.path === "preview-page" && code) {
          return { contents: code, loader: previewPageSource.loader, resolveDir: process.cwd() };
        }
        if (args.path === "preview-font-stub" && code) {
          return { contents: code, loader: "js" };
        }
        return null;
      });
    },
  };

  try {
    const result = await esbuild.build({
      stdin: {
        contents: PREVIEW_ENTRY,
        sourcefile: "entry.js",
        resolveDir: process.cwd(),
      },
      bundle: true,
      format: "iife",
      platform: "browser",
      target: "es2020",
      write: false,
      plugins: [nextStubPlugin, virtualPlugin],
      loader: { ".js": "jsx" },
    });
    const out = result.outputFiles?.[0];
    if (!out?.text) {
      return { ok: false, error: "esbuild produced no output" };
    }
    const bundle = out.text.replace(/<\/script>/gi, "<\\/script>");
    // If the page has a Calendly inline widget div, load the widget script so it can populate it.
    // Load script WITHOUT async so it runs before our init (avoids race where div appears before Calendly is defined).
    const needsCalendly =
      /calendly-inline-widget|data-url\s*=\s*["'][^"']*calendly\.com/i.test(tsx) ||
      /calendly-inline-widget/.test(out.text);
    const calendlyScript = needsCalendly
      ? `
  <script src="https://assets.calendly.com/assets/external/widget.js"><\\/script>
  <script>
  (function(){
    function initEl(el){
      if (typeof Calendly === 'undefined') return false;
      var url = el.getAttribute('data-url');
      if (!url || el.getAttribute('data-calendly-done')) return true;
      el.setAttribute('data-calendly-done', '1');
      try { Calendly.initInlineWidget({ url: url, parentElement: el, prefill: {}, utm: {}, resize: true }); } catch(e){}
      return true;
    }
    function run(){
      document.querySelectorAll('.calendly-inline-widget:not([data-calendly-done])').forEach(function(el){ initEl(el); });
    }
    if (typeof Calendly !== 'undefined') { run(); } else { window.addEventListener('load', function(){ run(); }); }
    setInterval(run, 400);
    setTimeout(run, 300);
    setTimeout(run, 1200);
    setTimeout(run, 2500);
    var observer = typeof MutationObserver !== 'undefined' && new MutationObserver(function(){ run(); });
    if (observer) {
      observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
    }
  })();
  <\\/script>`
      : "";
    // Open all links in a new tab so socials/external URLs don't load inside the iframe (CSP/frame-ancestors would block e.g. LinkedIn)
    const linkPatchScript = `
  <script>
  (function(){
    function patchLinks(){
      document.querySelectorAll('a[href]').forEach(function(a){
        var h = a.getAttribute('href') || '';
        if (h.startsWith('http') || h.startsWith('mailto:')) {
          a.setAttribute('target', '_blank');
          a.setAttribute('rel', 'noopener noreferrer');
        }
      });
    }
    setTimeout(patchLinks, 200);
    setTimeout(patchLinks, 800);
  })();
  <\\/script>`;
    // Load allowed Google Fonts in preview so they are available when TSX uses them (stub still returns font-sans; fonts ready if stub is enhanced)
    const PREVIEW_GOOGLE_FONTS =
      "Bebas+Neue|Manrope|Playfair+Display|Oswald|Source+Sans+3|Nunito|DM+Sans|Outfit|Sora|Plus+Jakarta+Sans|Lexend|Figtree|Work+Sans|Karla|Lora|Open+Sans|Raleway|Poppins|Anton|Abril+Fatface|DM+Serif+Display|Righteous|Teko";
    const fontLink = `  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=${PREVIEW_GOOGLE_FONTS.replace(/\|/g, "&family=")}&display=swap">`;
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Preview</title>
${fontLink}
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body>
  <div id="root"></div>
  <script>${bundle}</script>${calendlyScript}${linkPatchScript}
</body>
</html>`;
    return { ok: true, html };
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    if (/unterminated\s+string\s+literal/i.test(message) || /virtual:preview-page.*error/i.test(message)) {
      return {
        ok: false,
        error:
          "Unterminated string literal in your code. Check that every string and JSX attribute value is properly closed (matching \" or ').",
      };
    }
    return { ok: false, error: message };
  }
}

export interface ValidateTsxResult {
  runnable: boolean;
  mobileFriendly: boolean;
  browserSafe: boolean;
  sameButtons?: boolean;
  errors: string[];
}

export async function validateTsx(
  tsx: string,
  options?: { spec?: { ctaEntries?: Array<{ url: string }> } }
): Promise<ValidateTsxResult> {
  const errors: string[] = [];
  if (!tsx?.trim()) {
    return { runnable: false, mobileFriendly: false, browserSafe: false, errors: ["Empty TSX"] };
  }
  if (!looksLikeTsx(tsx)) {
    errors.push("Missing or invalid export default");
    return { runnable: false, mobileFriendly: false, browserSafe: false, errors };
  }
  const browserSafe = !hasBrowserUnsafePatterns(tsx);
  if (!browserSafe) {
    errors.push("Code uses Node or server-only APIs (require, process.env, node: imports)");
  }
  const mobileFriendly = hasResponsiveClasses(tsx);
  if (!mobileFriendly) {
    errors.push("No responsive Tailwind classes (sm:/md:/lg:) detected; layout may break on mobile");
  }
  const sameButtons = options?.spec ? checkSameButtons(tsx, options.spec) : undefined;
  if (sameButtons === false) {
    errors.push("CTA links in code do not match spec (same URLs required for all variants)");
  }
  const compile = await compileTsxToHtml(tsx);
  const runnable = compile.ok;
  if (!runnable) {
    errors.push(`Does not compile: ${compile.error}`);
  }
  return {
    runnable,
    mobileFriendly,
    browserSafe,
    ...(sameButtons !== undefined && { sameButtons }),
    errors,
  };
}
