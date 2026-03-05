"""
Build a Vercel-ready Next.js bundle: one of 4 variants per visit, cycling so each variant
is shown once before any repeat (tracked in sessionStorage). CTA beacon sends
repo_full_name, layer, variant_id to the backend.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _esc_js(s: str) -> str:
    """Escape for use inside a JavaScript string (backslash and quotes)."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")


def _normalize_variant_tsx(tsx: str) -> str:
    """Apply safe fixes so the variant can run on Vercel (next/font names, etc.)."""
    if not (tsx or "").strip():
        return tsx or ""
    s = (tsx or "").replace("\ufeff", "").strip()
    # next/font/google export names: Claude sometimes uses wrong names
    s = re.sub(r"\bSource_Sans_Pro\b", "Source_Sans_3", s)
    s = re.sub(r"\bNunito_Sans\b", "Nunito", s)
    return s


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


def build_vercel_bundle(
    variant_tsx_list: list[str],
    repo_full_name: str,
    layer: str,
    beacon_url: str,
) -> dict[str, str]:
    """
    Build a dict of path -> content for a Vercel-ready Next.js app.
    - app/page.tsx: picks random 1-4, renders that variant, wraps with data attrs for beacon.
    - app/variants/variant-1.tsx .. variant-4.tsx: the four variant components.
    - app/layout.tsx, app/globals.css, package.json, next.config.ts, tsconfig.json, postcss.config.mjs.
    """
    if len(variant_tsx_list) != 4:
        raise ValueError("variant_tsx_list must have exactly 4 elements")
    repo_esc = _esc_js(repo_full_name.strip())
    layer_esc = _esc_js(layer.strip())
    beacon_esc = _esc_js(beacon_url.rstrip("/"))

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

import {{ useState, useCallback, useEffect }} from "react";
import Variant1 from "./variants/variant-1";
import Variant2 from "./variants/variant-2";
import Variant3 from "./variants/variant-3";
import Variant4 from "./variants/variant-4";

const VARIANTS = [Variant1, Variant2, Variant3, Variant4];
const REPO_FULL_NAME = '{repo_esc}';
const LAYER = '{layer_esc}';
const BEACON_URL = '{beacon_esc}';
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

export default function ClientPage() {{
  const [v, setV] = useState<number | null>(null);
  useEffect(() => {{
    setV(pickAndUpdatePool());
  }}, []);
  useEffect(() => {{
    if (v != null) (window as unknown as {{ __landrightVariantId?: number }}).__landrightVariantId = v;
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
        # Normalize (font names, etc.) then ensure "use client" so it runs on Vercel
        content = _normalize_variant_tsx(tsx or "")
        content = content.strip()
        if not content.endswith(";"):
            content = content.rstrip()
        content = _ensure_client_directive(content)
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
        "- **The 4 variant files** (`app/variants/variant-1.tsx` … `variant-4.tsx`) are the page content; the root page handles selection and tracking.\n"
    )
    files["global.d.ts"] = (
        "declare global { interface Window { __landrightVariantId?: number; } }\nexport {};\n"
    )

    return files
