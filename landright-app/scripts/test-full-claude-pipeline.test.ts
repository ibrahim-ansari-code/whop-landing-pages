/**
 * Full pipeline test: call backend /generate (Claude), then lint 4 variant TSX,
 * check Calendly, run build-export-bundle and next build. No request timeout on /generate.
 * Backend must be on http://localhost:8000 with ANTHROPIC_API_KEY set.
 */
import { describe, it, expect } from "vitest";
import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { compileTsxToHtml } from "@/lib/preview-compile";

const BACKEND = process.env.NEXT_PUBLIC_GENERATE_API_URL?.trim().replace(/\/$/, "") ?? "http://localhost:8000";

const SPEC_WITH_CALENDLY = {
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
};

function hasCalendlyEmbed(tsx: string): boolean {
  const hasWidget =
    /calendly-inline-widget/i.test(tsx) || /CalendlyInlineWidget/i.test(tsx);
  const hasDataUrl =
    /data-url\s*=\s*["']https?:\/\/[^"']*calendly\.com/i.test(tsx) ||
    /data-url\s*=\s*\{[^}]*calendly/i.test(tsx);
  return hasWidget && hasDataUrl;
}

describe("Full Claude pipeline", () => {
  it(
    "calls /generate, lints 4 variants, checks Calendly, runs Vercel build",
    async () => {
      // 1) Call backend /generate (real Claude) – no request timeout; must return 4 variants
      let variants: string[] = [];
      try {
        const res = await fetch(`${BACKEND}/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(SPEC_WITH_CALENDLY),
        });
        const data = await res.json();
        if (!res.ok) {
          expect.fail(
            `Backend /generate returned ${res.status}. Body: ${JSON.stringify(data)}. Is backend on :8000 and ANTHROPIC_API_KEY set?`
          );
        }
        if (!Array.isArray(data.variants) || data.variants.length !== 4) {
          expect.fail(
            `Backend /generate must return 4 variants. Got: ${data.variants?.length ?? 0}. Body: ${JSON.stringify(data).slice(0, 500)}`
          );
        }
        variants = data.variants;
      } catch (e) {
        expect.fail(
          `Backend /generate failed: ${(e as Error).message}. Is backend running on http://localhost:8000 and ANTHROPIC_API_KEY set?`
        );
      }

      // 1) Compile each variant (no runtime React duplicate / syntax errors)
      for (let i = 0; i < variants.length; i++) {
        const result = await compileTsxToHtml(variants[i]);
        expect(result.ok, `variant ${i + 1} should compile`).toBe(true);
      }

      // 2) Calendly: when spec had embedCalendly, each variant should have proper embed
      if (SPEC_WITH_CALENDLY.spec.ctaEntries.some((c) => (c as { embedCalendly?: boolean }).embedCalendly)) {
        for (let i = 0; i < variants.length; i++) {
          expect(
            hasCalendlyEmbed(variants[i]),
            `variant ${i + 1} should include Calendly embed (calendly-inline-widget + data-url)`
          ).toBe(true);
        }
      }

      // Normalise next/font names that Claude sometimes gets wrong (next/font/google export names)
      variants = variants.map((v) =>
        v
          .replace(/\bSource_Sans_Pro\b/g, "Source_Sans_3")
          .replace(/\bNunito_Sans\b/g, "Nunito")
      );

      // 3) Build export bundle and run next build in temp dir
      const res = await fetch(`${BACKEND}/build-export-bundle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variant_tsx_list: variants,
          repo_full_name: "test-owner/test-repo",
          layer: "layer-1",
        }),
      });
      expect(res.ok, "build-export-bundle should return 200").toBe(true);
      const data = await res.json();
      const files: Record<string, string> = data.files || {};
      expect(files["app/page.tsx"]).toBeDefined();
      expect(files["package.json"]).toBeDefined();
      expect(files["next.config.js"]).toBeDefined();

      const buildDir = path.join(process.cwd(), "scripts", ".tmp-vercel-build");
      fs.mkdirSync(buildDir, { recursive: true });
      for (const [relPath, content] of Object.entries(files)) {
        const fullPath = path.join(buildDir, relPath);
        fs.mkdirSync(path.dirname(fullPath), { recursive: true });
        fs.writeFileSync(fullPath, content, "utf8");
      }
      // If bundle has no global.d.ts (old backend), add it so next build type-check passes
      if (!files["global.d.ts"]) {
        fs.writeFileSync(
          path.join(buildDir, "global.d.ts"),
          "declare global { interface Window { __landrightVariantId?: number; } }\nexport {};\n",
          "utf8"
        );
        const tsconfigPath = path.join(buildDir, "tsconfig.json");
        if (fs.existsSync(tsconfigPath)) {
          const tsconfig = JSON.parse(fs.readFileSync(tsconfigPath, "utf8"));
          tsconfig.include = (tsconfig.include || []).concat("global.d.ts");
          fs.writeFileSync(tsconfigPath, JSON.stringify(tsconfig, null, 2), "utf8");
        }
      }
      try {
        execSync("npm install", { cwd: buildDir, stdio: "inherit" });
        execSync("npm run build", { cwd: buildDir, stdio: "inherit" });
      } finally {
        try {
          fs.rmSync(buildDir, { recursive: true, force: true });
        } catch {}
      }
    },
    600_000
  ); // 10 min test timeout so generation can finish
});
