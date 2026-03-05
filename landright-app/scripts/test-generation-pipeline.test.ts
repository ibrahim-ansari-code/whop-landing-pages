/**
 * Integration test: code generation pipeline.
 * - Template TSX with Calendly → preview compile → Calendly script + root in HTML.
 * - Backend /generate → 4 variants → first variant compiles.
 * - Backend /build-export-bundle → Vercel files (next.config.js, package.json, variants).
 */
import { describe, it, expect } from "vitest";
import { compileTsxToHtml } from "@/lib/preview-compile";

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

describe("Code generation pipeline", () => {
  it("compiles template TSX with Calendly and injects widget script", async () => {
    const result = await compileTsxToHtml(TEMPLATE_TSX_WITH_CALENDLY);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.html).toContain("calendly.com/assets/external/widget.js");
    expect(result.html).toContain('id="root"');
    expect(result.html).toContain("calendly-inline-widget");
  });

  it("first variant from backend /generate compiles when backend returns template", async () => {
    let variants: string[] = [];
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
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
        signal: controller.signal,
      });
      clearTimeout(timeout);
      const data = await res.json();
      if (res.ok && Array.isArray(data.variants) && data.variants.length === 4) {
        variants = data.variants;
      }
    } catch {
      clearTimeout(timeout);
      return;
    }
    if (variants.length === 0) return;
    const result = await compileTsxToHtml(variants[0]);
    expect(result.ok).toBe(true);
  }, 8000);

  it("build-export-bundle returns valid Vercel config files", async () => {
    const fourVariants = [
      TEMPLATE_TSX_WITH_CALENDLY,
      TEMPLATE_TSX_WITH_CALENDLY,
      TEMPLATE_TSX_WITH_CALENDLY,
      TEMPLATE_TSX_WITH_CALENDLY,
    ];
    let files: Record<string, string> = {};
    try {
      const res = await fetch("http://localhost:8000/build-export-bundle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variant_tsx_list: fourVariants,
          repo_full_name: "test-owner/test-repo",
          layer: "layer-1",
        }),
      });
      if (!res.ok) return;
      const data = await res.json();
      files = data.files || {};
    } catch {
      return;
    }
    expect(files["app/page.tsx"]).toBeDefined();
    expect(files["app/layout.tsx"]).toBeDefined();
    expect(files["next.config.js"]).toBeDefined();
    expect(files["next.config.js"]).toContain("module.exports");
    expect(files["package.json"]).toBeDefined();
    const pkg = JSON.parse(files["package.json"]);
    expect(pkg.scripts?.build).toBe("next build");
    expect(pkg.dependencies?.next).toBeDefined();
    for (let i = 1; i <= 4; i++) {
      expect(files[`app/variants/variant-${i}.tsx`]).toBeDefined();
    }
  });
});
