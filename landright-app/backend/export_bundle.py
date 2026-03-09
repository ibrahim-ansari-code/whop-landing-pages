"""
Build a Vercel-ready Next.js bundle: one of 4 variants per visit, cycling so each variant
is shown once before any repeat (tracked in sessionStorage). CTA beacon sends
repo_full_name, layer, variant_id to the backend. Section visibility is tracked via
elements with data-landright-section: time in view is sent to POST /beacon-time with section_id
and to PostHog as section_viewed events.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _esc_js(s: str) -> str:
    """Escape for use inside a JavaScript string (backslash and quotes)."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences (```tsx ... ``` or ``` ... ```) so we never commit markdown in TSX."""
    if not text or "```" not in text:
        return text
    s = text.strip()
    # If entire content is wrapped in one fence block, unwrap
    if s.startswith("```"):
        first = s.find("\n")
        if first >= 0:
            s = s[first + 1:]
        if s.endswith("```"):
            s = s[: s.rfind("```")].rstrip()
        return s
    # Remove any leading fence line and trailing fence line
    lines = s.split("\n")
    start = 0
    if lines and lines[0].strip().startswith("```"):
        start = 1
    end = len(lines)
    if lines and lines[-1].strip() == "```":
        end = len(lines) - 1
    return "\n".join(lines[start:end])


def _normalize_curly_quotes(text: str) -> str:
    """Replace curly/smart quotes and non-ASCII backticks so JS/TSX parser never fails on them."""
    s = text
    s = s.replace("\u2018", "'").replace("\u2019", "'")  # ' '
    s = s.replace("\u201c", '"').replace("\u201d", '"')  # " "
    s = s.replace("\u201b", "'")  # single quote variant
    # Normalize backticks (template literals): non-ASCII grave/backtick -> ASCII so no unclosed literal
    s = s.replace("\u02cb", "`").replace("\u0060", "`")  # modifier letter grave, grave accent
    return s


# Allowed next/font/google names (must match backend FONT_WHITELIST). Unknown fonts get replaced with Manrope.
_FONT_WHITELIST = frozenset({
    "Bebas_Neue", "Playfair_Display", "Oswald", "Anton", "Archivo_Black", "Barlow_Condensed",
    "DM_Serif_Display", "Righteous", "Teko", "Ultra", "Abril_Fatface", "Alfa_Slab_One", "Fredoka_One",
    "Manrope", "Source_Sans_3", "Nunito", "DM_Sans", "Outfit", "Sora", "Plus_Jakarta_Sans",
    "Lexend", "Figtree", "Work_Sans", "Karla", "Lora", "Open_Sans", "Raleway", "Poppins",
})


def _normalize_font_names(text: str) -> str:
    """Replace any next/font/google font name not in whitelist with Manrope so Vercel never sees unknown font."""
    s = text
    # Find all font names used as Font_Name({ or in import { ... } from 'next/font/google'
    candidates = set(re.findall(r"\b([A-Z][A-Za-z0-9_]*)\s*\(\s*\{", s))
    imp = re.search(r"import\s+\{([^}]+)\}\s+from\s+['\"]next/font/google['\"]", s)
    if imp:
        for name in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)", imp.group(1)):
            candidates.add(name)
    to_replace = [n for n in candidates if n not in _FONT_WHITELIST]
    for name in to_replace:
        s = re.sub(r"\b" + re.escape(name) + r"\b", "Manrope", s)
    # Collapse duplicate Manrope in same import: { Manrope, Manrope } -> { Manrope }
    def collapse_import(m: re.Match) -> str:
        names = [x.strip() for x in m.group(2).split(",") if x.strip()]
        unique = list(dict.fromkeys(names))
        return m.group(1) + ", ".join(unique) + m.group(3)
    s = re.sub(
        r"(import\s+\{)([^}]+)(\}\s+from\s+['\"]next/font/google['\"])",
        collapse_import,
        s,
    )
    return s


def _strip_trailing_explanation(text: str) -> str:
    """Remove trailing LLM explanation after the default export closing }; ."""
    if not text or "};" not in text:
        return text
    idx = text.rfind("};")
    # Only consider }; that is at end of line (avoid cutting inside a string)
    if idx > 0 and text[idx - 1] not in (" ", "\n", "\t", "\r"):
        return text
    after = text[idx + 2 :].strip()
    if not after or len(after) < 15:
        return text
    # Heuristic: if what follows looks like prose (starts with capital, or common phrases), truncate
    strip_phrases = ("note:", "here's", "here is", "the above", "explanation:", "this code", "above code")
    after_lower = after[:50].lower()
    if after[0].isupper() or any(after_lower.startswith(p) for p in strip_phrases):
        return text[: idx + 2].rstrip()
    return text


def _normalize_variant_tsx(tsx: str) -> str:
    """Apply safe fixes so the variant can run on Vercel (fences, quotes, next/font names, etc.)."""
    if not (tsx or "").strip():
        return tsx or ""
    s = _strip_markdown_fences(tsx or "")
    s = _normalize_curly_quotes(s)
    s = _strip_trailing_explanation(s)
    s = s.replace("\ufeff", "")
    # Strip other common invisible/breaking characters
    for char in ("\u200b", "\u200c", "\u200d", "\ufeff"):
        s = s.replace(char, "")
    s = s.strip()
    # next/font/google export names: Claude sometimes uses wrong names
    s = re.sub(r"\bSource_Sans_Pro\b", "Source_Sans_3", s)
    s = re.sub(r"\bNunito_Sans\b", "Nunito", s)
    s = _normalize_font_names(s)
    return s


def _ensure_script_import(content: str) -> str:
    """If content uses <Script but has no Script import, add 'import Script from \"next/script\";' after first line or first import."""
    if "<Script" not in content and "<script" not in content:
        return content
    if re.search(r"from\s+['\"]next/script['\"]", content) or re.search(r"import\s+.*Script.*next/script", content):
        return content
    lines = content.split("\n")
    insert_at = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("import "):
            insert_at = i + 1
        elif insert_at > 0 and line.strip() and not line.strip().startswith("import "):
            break
    script_line = 'import Script from "next/script";'
    lines.insert(insert_at, script_line)
    return "\n".join(lines)


def _wrap_multiple_roots_in_fragment(content: str) -> str:
    """If return ( has multiple root JSX elements (e.g. <Script /> and <div>, or two <div>s), wrap in <> </> so Vercel build succeeds."""
    idx = content.find("return (")
    if idx < 0:
        return content
    start = idx + len("return (")
    depth = 1
    i = start
    while i < len(content) and depth > 0:
        if content[i] == "(":
            depth += 1
        elif content[i] == ")":
            depth -= 1
        i += 1
    if depth != 0:
        return content
    closing_paren = i - 1
    between = content[start:closing_paren]
    if between.strip().startswith("<>"):
        return content
    # Count top-level JSX opening tags: lines that start with optional whitespace then < then a tag name
    lines = between.split("\n")
    root_tag_lines = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("<") and len(stripped) > 1 and stripped[1:2].isalnum():
            indent = len(line) - len(stripped)
            root_tag_lines.append(indent)
    if len(root_tag_lines) < 2:
        return content
    min_indent = min(root_tag_lines)
    sibling_count = sum(1 for ind in root_tag_lines if ind == min_indent)
    if sibling_count < 2:
        return content
    # Insert <> after "return (" and </> before the closing ")"
    before = content[:start]
    after = content[closing_paren:]
    return before + "<>\n    " + between + "\n    </>" + after


def _ensure_client_directive(content: str) -> str:
    """Prepend \"use client\"; so Next.js treats the file as a client component (required for hooks/JSX on Vercel).
    Always strip BOM and ensure the directive is exactly the first line so the parser never fails."""
    raw = (content or "").replace("\ufeff", "")
    c = raw.strip()
    if not c:
        return '"use client";\n\n'
    # If content already has "use client" or 'use client', remove that first line so we don't duplicate
    lower = c.lstrip().lower()
    if lower.startswith('"use client"') or lower.startswith("'use client'"):
        # Find end of first line and take the rest
        first_newline = c.find("\n")
        if first_newline >= 0:
            rest = c[first_newline + 1 :].lstrip()
        else:
            rest = ""
        return '"use client";\n\n' + (rest + "\n" if rest else "")
    return '"use client";\n\n' + c


# Canonical section names for visibility tracking (aligned with _analyze_variant_structure in backend).
_SECTION_PATTERNS: list[tuple[str, str]] = [
    (r"\bhero\b", "Hero"),
    (r"\bfeatures?\b", "Features"),
    (r"\btestimonial", "Testimonials"),
    (r"\bpricing\b", "Pricing"),
    (r"\bfaq\b", "FAQ"),
    (r"\bfooter\b", "Footer"),
    (r"\bnav\b", "Navigation"),
    (r"social\s*proof|socialproof", "Social Proof"),
]


def _inject_section_markers(tsx: str) -> str:
    """Inject data-landright-section attributes into section roots for visibility tracking.
    Skips if any data-landright-section already present. Best-effort: matches first <section|div|nav|header|footer>
    whose className/class contains the keyword (hero, features, etc.) and adds the attribute."""
    if not (tsx or "").strip():
        return tsx or ""
    if "data-landright-section" in tsx:
        return tsx
    for keyword_pattern, section_name in _SECTION_PATTERNS:
        for m in re.finditer(
            r"(<(?:section|div|nav|header|footer)\s+)([^>]*?)(>)",
            tsx,
            re.IGNORECASE,
        ):
            attrs = m.group(2)
            if "data-landright-section" in attrs:
                continue
            if re.search(keyword_pattern, attrs, re.IGNORECASE):
                new_tag = (
                    m.group(1)
                    + attrs.rstrip()
                    + f' data-landright-section="{section_name}"'
                    + m.group(3)
                )
                tsx = tsx[: m.start()] + new_tag + tsx[m.end() :]
                break
    return tsx


def build_vercel_bundle(
    variant_tsx_list: list[str],
    repo_full_name: str,
    layer: str,
    beacon_url: str,
    posthog_key: str | None = None,
    posthog_host: str | None = None,
) -> dict[str, str]:
    """
    Build a dict of path -> content for a Vercel-ready Next.js app.
    - app/page.tsx: picks random 1-4, renders that variant, wraps with data attrs for beacon.
    - app/variants/variant-1.tsx .. variant-4.tsx: the four variant components (with section markers for visibility tracking).
    - app/layout.tsx, app/globals.css, package.json, next.config.ts, tsconfig.json, postcss.config.mjs.
    If posthog_key is set (e.g. from backend env), it is embedded so session replay goes to your PostHog
    without the deployer needing to set any env vars. Section visibility: elements with data-landright-section
    are observed; when a section leaves view or the user leaves the page, duration is sent to beacon-time (section_id)
    and to PostHog as section_viewed events.
    """
    if len(variant_tsx_list) != 4:
        raise ValueError("variant_tsx_list must have exactly 4 elements")
    repo_esc = _esc_js(repo_full_name.strip())
    layer_esc = _esc_js(layer.strip())
    beacon_esc = _esc_js(beacon_url.rstrip("/"))
    posthog_key_esc = _esc_js((posthog_key or "").strip())
    posthog_host_esc = _esc_js((posthog_host or "https://us.i.posthog.com").strip().rstrip("/"))

    # Root page: server component that opts out of prerender (avoids "Cannot read properties of null (reading 'useContext')"
    # during next build), then renders the client wrapper.
    page_server_tsx = """import ClientPage from "./ClientPage";
export const dynamic = "force-dynamic";
export default function Page() {
  return <ClientPage />;
}
"""
    # Client page: pick variant from pool so each of 1-4 is shown once before any repeat
    page_tsx = f'''"use client";

import {{ useState, useCallback, useEffect, useRef }} from "react";
import posthog from "posthog-js";
import Variant1 from "./variants/variant-1";
import Variant2 from "./variants/variant-2";
import Variant3 from "./variants/variant-3";
import Variant4 from "./variants/variant-4";

const VARIANTS = [Variant1, Variant2, Variant3, Variant4];
const REPO_FULL_NAME = '{repo_esc}';
const LAYER = '{layer_esc}';
const BEACON_URL = '{beacon_esc}';
const POSTHOG_KEY = '{posthog_key_esc}';
const POSTHOG_HOST = '{posthog_host_esc}';
const POOL_KEY = "landright_variant_pool";

function getPool(): number[] {{
  if (typeof window === "undefined") return [1, 2, 3, 4];
  try {{
    const raw = sessionStorage.getItem(POOL_KEY);
    if (raw) {{
      const parsed = JSON.parse(raw) as number[];
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }}
  }} catch {{}}
  return [1, 2, 3, 4];
}}

function pickAndUpdatePool(): number {{
  const pool = getPool();
  const idx = Math.floor(Math.random() * pool.length);
  const picked = pool[idx];
  const next = pool.filter((_, i) => i !== idx);
  if (typeof window !== "undefined") {{
    try {{
      sessionStorage.setItem(POOL_KEY, JSON.stringify(next.length > 0 ? next : [1, 2, 3, 4]));
    }} catch {{}}
  }}
  return picked;
}}

function sendCtaClick(ctaLabel?: string, ctaId?: string) {{
  const w = window as unknown as {{ __landrightVariantId?: number }};
  fetch(BEACON_URL + "/beacon", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{
      event: "button_click",
      repo_full_name: REPO_FULL_NAME,
      layer: LAYER,
      variant_id: String(w.__landrightVariantId ?? ""),
      cta_label: ctaLabel ?? undefined,
      cta_id: ctaId ?? undefined,
    }}),
  }}).catch(() => {{}});
}}

function sendTimeOnPage(durationSeconds: number, sectionId?: string) {{
  const w = window as unknown as {{ __landrightVariantId?: number }};
  const payload: Record<string, unknown> = {{
    repo_full_name: REPO_FULL_NAME,
    layer: LAYER,
    variant_id: String(w.__landrightVariantId ?? ""),
    duration_seconds: durationSeconds,
  }};
  if (sectionId) payload.section_id = sectionId;
  const body = JSON.stringify(payload);
  if (navigator.sendBeacon) {{
    navigator.sendBeacon(BEACON_URL + "/beacon-time", body);
  }} else {{
    fetch(BEACON_URL + "/beacon-time", {{
      method: "POST",
      headers: {{ "Content-Type": "text/plain;charset=UTF-8" }},
      body,
      keepalive: true,
    }}).catch(() => {{}});
  }}
}}

export default function ClientPage() {{
  const [v, setV] = useState<number | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const sectionStartTimesRef = useRef<Record<string, number>>({{}});
  useEffect(() => {{
    setV(pickAndUpdatePool());
  }}, []);
  useEffect(() => {{
    if (v != null) (window as unknown as {{ __landrightVariantId?: number }}).__landrightVariantId = v;
  }}, [v]);
  useEffect(() => {{
    if (v == null) return;
    const startTime = Date.now();
    let lastHeartbeatAt = startTime;
    const sendTime = () => {{
      const durationSeconds = (Date.now() - startTime) / 1000;
      if (durationSeconds > 0) sendTimeOnPage(durationSeconds);
    }};
    const onVisibilityChange = () => {{
      if (document.visibilityState === "hidden") sendTime();
    }};
    const onPageHide = () => {{ sendTime(); }};
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pagehide", onPageHide);
    // Periodic heartbeat so Supabase gets time even when unload beacon is dropped (e.g. tab close)
    const HEARTBEAT_INTERVAL_MS = 30000;
    const heartbeatId = setInterval(() => {{
      const now = Date.now();
      const durationSeconds = (now - lastHeartbeatAt) / 1000;
      lastHeartbeatAt = now;
      if (durationSeconds > 0) sendTimeOnPage(durationSeconds);
    }}, HEARTBEAT_INTERVAL_MS);
    return () => {{
      clearInterval(heartbeatId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("pagehide", onPageHide);
    }};
  }}, [v]);
  useEffect(() => {{
    if (v == null || typeof window === "undefined") return;
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const flushSectionTimes = () => {{
      const startTimes = sectionStartTimesRef.current;
      const now = Date.now();
      for (const sectionId of Object.keys(startTimes)) {{
        const durationSeconds = (now - startTimes[sectionId]) / 1000;
        if (durationSeconds > 0) sendTimeOnPage(durationSeconds, sectionId);
      }}
      sectionStartTimesRef.current = {{}};
    }};
    const onVisibilityChange = () => {{
      if (document.visibilityState === "hidden") flushSectionTimes();
    }};
    const onPageHide = () => {{ flushSectionTimes(); }};
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pagehide", onPageHide);
    const els = wrapper.querySelectorAll("[data-landright-section]");
    const observer = new IntersectionObserver(
      (entries) => {{
        for (const entry of entries) {{
          const id = (entry.target as Element).getAttribute("data-landright-section");
          if (!id) continue;
          if (entry.isIntersecting) {{
            sectionStartTimesRef.current[id] = Date.now();
          }} else {{
            const start = sectionStartTimesRef.current[id];
            if (start != null) {{
              const durationSeconds = (Date.now() - start) / 1000;
              if (durationSeconds > 0) sendTimeOnPage(durationSeconds, id);
              delete sectionStartTimesRef.current[id];
            }}
          }}
        }}
      }},
      {{ threshold: 0.25, rootMargin: "0px" }}
    );
    els.forEach((el) => observer.observe(el));
    return () => {{
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("pagehide", onPageHide);
    }};
  }}, [v]);
  useEffect(() => {{
    if (typeof window === "undefined" || v == null) return;
    if (!POSTHOG_KEY) return;
    if (!(posthog as unknown as {{ __loaded?: boolean }}).__loaded) {{
      posthog.init(POSTHOG_KEY, {{
        api_host: POSTHOG_HOST || "https://us.i.posthog.com",
        capture_pageview: true,
        session_recording: {{ maskAllInputs: false }},
      }});
    }}
    posthog.register({{
      repo_full_name: REPO_FULL_NAME,
      layer: LAYER,
      variant_id: String(v),
    }});
  }}, [v]);
  const handleCtaClick = useCallback((e: React.MouseEvent) => {{
    const t = (e.target as HTMLElement).closest("a, button");
    if (!t) return;
    const label = (t as HTMLElement).textContent?.trim();
    const id = (t as HTMLElement).id ?? (t as HTMLElement).getAttribute("data-cta-id") ?? undefined;
    sendCtaClick(label ?? undefined, id ?? undefined);
  }}, []);
  if (v == null) return <div style={{{{ minHeight: "100vh" }}}} />;
  const VariantComponent = VARIANTS[v - 1];
  return (
    <div
      ref={{wrapperRef}}
      data-repo-full-name={{REPO_FULL_NAME}}
      data-layer={{LAYER}}
      data-variant-id={{String(v)}}
      onClick={{handleCtaClick}}
      role="presentation"
    >
      <VariantComponent />
    </div>
  );
}}
'''

    files: dict[str, str] = {
        "app/page.tsx": page_server_tsx,
        "app/ClientPage.tsx": page_tsx,
    }

    for i, tsx in enumerate(variant_tsx_list):
        # Normalize (font names, BOM, etc.), inject section markers for visibility tracking, then ensure "use client", Script import, and fragment wrap
        content = _normalize_variant_tsx(tsx or "")
        content = _inject_section_markers(content)
        content = content.strip()
        if not content.endswith(";"):
            content = content.rstrip()
        content = _ensure_client_directive(content)
        content = _ensure_script_import(content)
        content = _wrap_multiple_roots_in_fragment(content)
        files[f"app/variants/variant-{i + 1}.tsx"] = content

    layout_tsx = '''import type { Metadata } from "next";
import "./globals.css";
import CalendlyInit from "./calendly-init";

export const metadata: Metadata = {
  title: "Landing Page",
  description: "Generated by Landright",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <CalendlyInit />
        {children}
      </body>
    </html>
  );
}
'''

    globals_css = '''@import "tailwindcss";

:root {
  --background: #ffffff;
  --foreground: #171717;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
}

body {
  background: var(--background);
  color: var(--foreground);
  margin: 0;
  font-family: system-ui, sans-serif;
}
'''

    package_json = {
        "name": "landright-export",
        "version": "0.1.0",
        "private": True,
        "engines": {"node": ">=18"},
        "scripts": {
            "dev": "next dev",
            "build": "next build",
            "start": "next start",
        },
        "dependencies": {
            "next": "14.2.18",
            "posthog-js": "^1.180.0",
            "react": "^18.3.1",
            "react-dom": "^18.3.1",
        },
        "devDependencies": {
            "@tailwindcss/postcss": "^4",
            "@types/node": "^20",
            "@types/react": "^18",
            "@types/react-dom": "^18",
            "postcss": "^8",
            "tailwindcss": "^4",
            "typescript": "^5",
        },
    }

    next_config = '''/** @type { import('next').NextConfig } */
const nextConfig = {};
module.exports = nextConfig;
'''

    # So Vercel detects Next.js and auto-deploys. Root Directory must be . or empty in Vercel.
    # Do not set outputDirectory in Vercel UI; Next.js framework handles it.
    vercel_json = '''{
  "framework": "nextjs",
  "buildCommand": "npm run build",
  "installCommand": "npm install"
}
'''

    tsconfig = json.dumps({
        "compilerOptions": {
            "target": "ES2017",
            "lib": ["dom", "dom.iterable", "esnext"],
            "allowJs": True,
            "skipLibCheck": True,
            "strict": True,
            "noEmit": True,
            "esModuleInterop": True,
            "module": "esnext",
            "moduleResolution": "bundler",
            "resolveJsonModule": True,
            "isolatedModules": True,
            "jsx": "react-jsx",
            "incremental": True,
            "plugins": [{"name": "next"}],
            "paths": {"@/*": ["./*"]},
        },
        "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
        "exclude": ["node_modules"],
    }, indent=2)

    postcss_config = '''const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
module.exports = config;
'''

    files["app/layout.tsx"] = layout_tsx
    files["app/globals.css"] = globals_css
    # Client component: load Calendly script and init any .calendly-inline-widget (so embed works on Vercel)
    calendly_init_tsx = r'''"use client";

import { useEffect } from "react";

export default function CalendlyInit() {
  useEffect(() => {
    if (typeof document === "undefined") return;
    const script = document.createElement("script");
    script.src = "https://assets.calendly.com/assets/external/widget.js";
    script.async = true;
    script.onload = run;
    document.body.appendChild(script);
    const t = setInterval(run, 400);
    const mo =
      typeof MutationObserver !== "undefined" &&
      new MutationObserver(run);
    if (mo) mo.observe(document.body, { childList: true, subtree: true });
    return () => {
      clearInterval(t);
      if (mo) mo.disconnect();
    };
  }, []);
  return null;
}

function run() {
  if (typeof (window as unknown as { Calendly?: unknown }).Calendly === "undefined") return;
  document.querySelectorAll(".calendly-inline-widget:not([data-calendly-done])").forEach((el) => {
    const url = el.getAttribute("data-url");
    if (!url) return;
    el.setAttribute("data-calendly-done", "1");
    try {
      (window as unknown as { Calendly: { initInlineWidget: (o: unknown) => void } }).Calendly.initInlineWidget({
        url,
        parentElement: el,
        prefill: {},
        utm: {},
        resize: true,
      });
    } catch {}
  });
}
'''
    files["app/calendly-init.tsx"] = calendly_init_tsx
    files["package.json"] = json.dumps(package_json, indent=2)
    files["app/not-found.tsx"] = '''export default function NotFound() {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "system-ui" }}>
      <div style={{ textAlign: "center" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>Page not found</h1>
        <a href="/" style={{ marginTop: "1rem", display: "inline-block", color: "#2563eb" }}>Go home</a>
      </div>
    </div>
  );
}
'''
    files["next.config.js"] = next_config
    files["tsconfig.json"] = tsconfig
    files["postcss.config.js"] = postcss_config
    files["vercel.json"] = vercel_json
    files[".gitignore"] = (
        "# Dependencies\nnode_modules/\n.pnp\n.pnp.js\n\n"
        "# Next.js\n.next/\nout/\n\n"
        "# Vercel\n.vercel\n\n"
        "# Debug\nnpm-debug.log*\n.yarn/cache\n.yarn/unplugged\n.yarn/build-state.yml\n.yarn/install-state.gz\n.pnp.*\n\n"
        "# Env\n.env*.local\n.env\n\n"
        "# IDE\n.idea\n.vscode\n*.swp\n*.swo\n"
    )
    files["next-env.d.ts"] = (
        "/// <reference types=\"next\" />\n"
        "/// <reference types=\"next/image-types/global\" />\n\n"
    )
    files["README.md"] = (
        "# Landright Export – Next.js Landing Page\n\n"
        "Next.js 14 app (App Router) with Tailwind CSS. Ready for **automatic deployment on Vercel**.\n\n"
        "---\n\n"
        "## Deploy on Vercel (automatic)\n\n"
        "1. **Connect this repo to Vercel**\n"
        "   - Go to [vercel.com](https://vercel.com) → **Add New** → **Project**.\n"
        "   - Import your GitHub repository (this repo).\n"
        "   - Vercel will detect Next.js from `package.json` and `vercel.json`.\n\n"
        "2. **Use these settings** (usually auto-detected):\n"
        "   - **Framework Preset**: Next.js\n"
        "   - **Root Directory**: leave **empty** or set to `.`\n"
        "   - **Build Command**: `npm run build` (default)\n"
        "   - **Install Command**: `npm install` (default)\n"
        "   - **Output Directory**: leave **empty** (Next.js uses `.next` automatically; do not set it in the UI)\n\n"
        "3. **Deploy**\n"
        "   - Click **Deploy**. Every push to the default branch will trigger a new deployment.\n"
        "   - Preview deployments are created for other branches and pull requests.\n\n"
        "### If you see 404 after deploy\n"
        "   - In Vercel **Project Settings → General**: set **Root Directory** to `.` or leave empty.\n"
        "   - Ensure **Framework Preset** is **Next.js**.\n"
        "   - Leave **Output Directory** empty, then **Redeploy**.\n\n"
        "---\n\n"
        "## Local development\n\n"
        "```bash\nnpm install\nnpm run dev\n```\n\n"
        "Open [http://localhost:3000](http://localhost:3000).\n\n"
        "---\n\n"
        "## How this app works\n\n"
        "- **Variant selection**: `app/page.tsx` picks one of 4 variants per visit (sessionStorage pool so each variant is shown once before any repeat).\n"
        "- **Click tracking**: The wrapper in `app/page.tsx` sends a beacon to the Landright backend (`POST /beacon`) on button/link clicks; clicks are keyed by repo, layer, and variant_id.\n"
        "- **Time on page**: Total time on page is sent to `POST /beacon-time` when the user hides the tab or leaves; a heartbeat every 30s also sends incremental time. Sections with `data-landright-section` are observed; time in view per section is sent to `POST /beacon-time` with `section_id` when the section leaves view or the user leaves.\n"
        "- **PostHog session replay**: If Landright configured a PostHog key when building this bundle, session replays are sent to Landright's PostHog and tagged with `repo_full_name`, `layer`, and `variant_id`. No env vars are required from the deployer.\n"
        "- **The 4 variant files** (`app/variants/variant-1.tsx` … `variant-4.tsx`) are the page content; the root page handles selection and tracking.\n"
    )
    files["global.d.ts"] = (
        "declare global { interface Window { __landrightVariantId?: number; } }\nexport {};\n"
    )

    return files
