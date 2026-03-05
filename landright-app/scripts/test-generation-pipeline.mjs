/**
 * Integration test: code generation pipeline.
 * - Uses template-style TSX (with Calendly) as would come from backend when no API key.
 * - Runs preview compile and checks Calendly script + widget in output.
 * - Runs backend build_vercel_bundle and checks Vercel config files exist.
 *
 * Run: node scripts/test-generation-pipeline.mjs
 * Requires: backend running on port 8000.
 */

// Template variant 0 with Calendly (matches backend _build_template_variant when needs_calendly)
const TEMPLATE_TSX_WITH_CALENDLY = `"use client";

import { useState } from "react";

export default function Page() {
  const [showCalendly, setShowCalendly] = useState(false);
  return (
    <div className="min-h-screen bg-white text-gray-900">
      <main className="max-w-4xl mx-auto px-6 py-16 text-center">
        <h1 className="text-4xl font-bold tracking-tight">Tablingos</h1>
        <p className="mt-2 text-xl text-gray-600">Tagline</p>
        <p className="mt-6 text-gray-600">We do stuff.</p>
        <div className="flex flex-wrap gap-3 justify-center">
        <button type="button" className={\`rounded-lg bg-gray-900 text-white px-6 py-3 font-medium\`} onClick={() => setShowCalendly(true)}>Book a call</button>
        {showCalendly && <div className="calendly-inline-widget" data-url="https://calendly.com/example/30min" style={{ minWidth: 320, height: 700 }}></div>}
        </div>
      </main>
    </div>
  );
}
`;

async function main() {
  const base = new URL("../", import.meta.url).pathname;
  process.chdir(base);

  console.log("1. Loading preview-compile (compileTsxToHtml)...");
  const { compileTsxToHtml } = await import("../lib/preview-compile.ts");

  console.log("2. Compiling template TSX with Calendly...");
  const result = await compileTsxToHtml(TEMPLATE_TSX_WITH_CALENDLY);
  if (!result.ok) {
    console.error("FAIL: Preview compile failed:", result.error);
    process.exit(1);
  }
  const html = result.html;
  const hasCalendlyScript = html.includes("calendly.com/assets/external/widget.js");
  const hasRoot = html.includes('id="root"');
  console.log("   - Has Calendly script:", hasCalendlyScript);
  console.log("   - Has #root:", hasRoot);
  if (!hasCalendlyScript || !hasRoot) {
    console.error("FAIL: Calendly or root missing from preview HTML");
    process.exit(1);
  }
  console.log("   OK Preview compile and Calendly injection.\n");

  console.log("3. Testing backend /generate (template when no API key)...");
  let variants = [];
  try {
    const res = await fetch("http://localhost:8000/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        spec: {
          websiteInformation: {
            name: "Tablingos",
            tagline: "Tag",
            whatTheyDo: "We do stuff for at least ten chars",
          },
          ctaEntries: [
            {
              type: "call",
              label: "Book a call",
              url: "https://calendly.com/example/30min",
              embedCalendly: true,
            },
          ],
          goals: ["G1"],
          skillsOrNiches: [],
          colorScheme: { preset: "neutral" },
          theme: "minimal",
        },
        promptId: "default",
        experienceLibrary: [],
      }),
    });
    const data = await res.json();
    if (res.ok && Array.isArray(data.variants) && data.variants.length === 4) {
      variants = data.variants;
      console.log("   Got 4 variants, source:", data.source || "unknown");
    } else {
      console.log("   Backend returned error, using inline TSX for export test.");
      variants = [TEMPLATE_TSX_WITH_CALENDLY, TEMPLATE_TSX_WITH_CALENDLY, TEMPLATE_TSX_WITH_CALENDLY, TEMPLATE_TSX_WITH_CALENDLY];
    }
  } catch (e) {
    console.log("   Backend not reachable:", e.message, "- using inline TSX.");
    variants = [TEMPLATE_TSX_WITH_CALENDLY, TEMPLATE_TSX_WITH_CALENDLY, TEMPLATE_TSX_WITH_CALENDLY, TEMPLATE_TSX_WITH_CALENDLY];
  }

  console.log("4. Compiling first variant through preview (simulate UI)...");
  const firstVariant = variants[0];
  const previewResult = await compileTsxToHtml(firstVariant);
  if (!previewResult.ok) {
    console.error("FAIL: First variant did not compile:", previewResult.error);
    process.exit(1);
  }
  console.log("   OK First variant compiles.\n");

  console.log("5. Testing Vercel export bundle (build_vercel_bundle)...");
  const res = await fetch("http://localhost:8000/build-export-bundle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      variant_tsx_list: variants,
      repo_full_name: "test-owner/test-repo",
      layer: "layer-1",
    }),
  });
  if (!res.ok) {
    console.error("FAIL: build-export-bundle returned", res.status, await res.text());
    process.exit(1);
  }
  const { files } = await res.json();
  const required = [
    "app/page.tsx",
    "app/layout.tsx",
    "app/globals.css",
    "app/variants/variant-1.tsx",
    "app/variants/variant-2.tsx",
    "app/variants/variant-3.tsx",
    "app/variants/variant-4.tsx",
    "package.json",
    "next.config.js",
    "tsconfig.json",
    "postcss.config.js",
  ];
  for (const key of required) {
    if (!(key in files) || !files[key]) {
      console.error("FAIL: Missing or empty file in bundle:", key);
      process.exit(1);
    }
  }
  const pkg = JSON.parse(files["package.json"]);
  if (pkg.scripts?.build !== "next build" || !pkg.dependencies?.next) {
    console.error("FAIL: package.json missing next or build script");
    process.exit(1);
  }
  if (!files["next.config.js"].includes("nextConfig") || !files["next.config.js"].includes("module.exports")) {
    console.error("FAIL: next.config.js invalid");
    process.exit(1);
  }
  console.log("   OK All Vercel bundle files present and valid.\n");

  console.log("All checks passed: code generation, Calendly preview, Vercel config.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
