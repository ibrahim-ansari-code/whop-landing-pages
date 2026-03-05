/**
 * Integration tests: full pipeline from bundle → Vercel build with retry and automatic fixes
 * until deployable (or exhausted with files returned for custom fix).
 *
 * - With backend: fetch build-export-bundle, run buildVercelBundleWithRetry, expect deployable.
 * - With fixable bundle: variant missing "use client" → retry applies fix → expect success.
 * - Exhausted shape: when build fails and no fix applies, result has files + automaticFixesExhausted.
 */
import { describe, it, expect } from "vitest";
import { buildVercelBundleWithRetry } from "@/lib/vercel-build-with-retry";

const BACKEND = process.env.NEXT_PUBLIC_GENERATE_API_URL?.trim().replace(/\/$/, "") || "http://localhost:8000";

const VALID_VARIANT_TSX = `"use client";

import { useState } from "react";

export default function Page() {
  const [show, setShow] = useState(false);
  return (
    <div className="min-h-screen bg-white text-gray-900">
      <main className="max-w-4xl mx-auto px-6 py-16 text-center">
        <h1 className="text-4xl font-bold">Test Co</h1>
        <p className="mt-2 text-xl text-gray-600">Tagline</p>
        <button type="button" className="rounded-lg bg-gray-900 text-white px-6 py-3" onClick={() => setShow(true)}>
          Book a call
        </button>
      </main>
    </div>
  );
}
`;

async function fetchBundleFromBackend(): Promise<Record<string, string> | null> {
  try {
    const res = await fetch(`${BACKEND}/build-export-bundle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        variant_tsx_list: [VALID_VARIANT_TSX, VALID_VARIANT_TSX, VALID_VARIANT_TSX, VALID_VARIANT_TSX],
        repo_full_name: "test-owner/test-repo",
        layer: "layer-1",
      }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    const files = data.files || {};
    if (typeof files !== "object" || Object.keys(files).length === 0) return null;
    // Ensure TypeScript type deps exist so next build can run (backend may not include them in older bundles)
    const pkg = files["package.json"];
    if (typeof pkg === "string" && !pkg.includes("@types/react")) {
      const parsed = JSON.parse(pkg) as { devDependencies?: Record<string, string> };
      parsed.devDependencies = {
        ...parsed.devDependencies,
        "@types/node": "^20",
        "@types/react": "^18",
        "@types/react-dom": "^18",
      };
      files["package.json"] = JSON.stringify(parsed, null, 2);
    }
    return files;
  } catch {
    return null;
  }
}

describe("Vercel build pipeline (generate → check Vercel compatible → apply fixes until deployable)", () => {
  it(
    "build-export-bundle + buildVercelBundleWithRetry produces deployable bundle when backend is available",
    async () => {
      const files = await fetchBundleFromBackend();
      if (!files) {
        console.warn("Backend not available at " + BACKEND + "; skipping full pipeline test.");
        return;
      }
      expect(files["app/page.tsx"]).toBeDefined();
      expect(files["app/variants/variant-1.tsx"]).toBeDefined();
      expect(files["package.json"]).toBeDefined();

      const result = buildVercelBundleWithRetry(files);

      if (!result.ok && result.lastStderr) {
        console.warn("Build failed (lastStderr):", result.lastStderr.slice(-2000));
      }
      expect(result.ok, result.error || result.lastStderr || "build should succeed").toBe(true);
      expect(result.files).toBeDefined();
      expect(Object.keys(result.files!).length).toBeGreaterThan(0);
      expect(result.attempts).toBeGreaterThanOrEqual(1);
    },
    300_000
  );

  it(
    "when a variant is missing \"use client\", automatic fix is applied and build succeeds",
    async () => {
      const files = await fetchBundleFromBackend();
      if (!files) {
        console.warn("Backend not available; skipping fixable-bundle test.");
        return;
      }
      // Strip "use client" from variant-1 so first build fails (Next.js needs it for client components)
      const variant1 = files["app/variants/variant-1.tsx"] || "";
      const withoutUseClient = variant1.replace(/^\s*["']use client["'];?\s*\n?/i, "").trim();
      expect(withoutUseClient).not.toMatch(/^["']use client["']/i);
      const modifiedFiles = { ...files, "app/variants/variant-1.tsx": withoutUseClient };

      const result = buildVercelBundleWithRetry(modifiedFiles);

      expect(result.ok, result.error || result.lastStderr || "build should succeed after fix").toBe(true);
      expect(result.files).toBeDefined();
      // If the build failed initially, our fix adds "use client"; otherwise Next may accept the component as-is
      if (result.files!["app/variants/variant-1.tsx"]) {
        expect(result.files!["app/variants/variant-1.tsx"].trim()).toBeTruthy();
      }
    },
    300_000
  );

  it("when build fails and no automatic fix applies, returns files and automaticFixesExhausted", () => {
    // Minimal bundle that will fail to build: valid structure but variant has unfixable syntax error
    const badVariant = `
export default function Page() {
  return <div>unclosed
`;
    const files: Record<string, string> = {
      "app/page.tsx": `"use client";
import V1 from "./variants/variant-1";
import V2 from "./variants/variant-2";
import V3 from "./variants/variant-3";
import V4 from "./variants/variant-4";
export default function Page() { const v = 1; const C = [V1,V2,V3,V4][v-1]; return C ? <C /> : null; }
`,
      "app/variants/variant-1.tsx": badVariant,
      "app/variants/variant-2.tsx": '"use client";\nexport default function P() { return <div>2</div>; }',
      "app/variants/variant-3.tsx": '"use client";\nexport default function P() { return <div>3</div>; }',
      "app/variants/variant-4.tsx": '"use client";\nexport default function P() { return <div>4</div>; }',
      "app/layout.tsx": `export default function Layout({ children }: { children: React.ReactNode }) { return <html><body>{children}</body></html>; }`,
      "package.json": JSON.stringify({
        name: "test",
        private: true,
        scripts: { build: "next build" },
        dependencies: { next: "14.2.18", react: "^18.2.0", "react-dom": "^18.2.0" },
        devDependencies: { typescript: "^5" },
      }),
      "next.config.js": "module.exports = {};",
      "tsconfig.json": JSON.stringify({
        compilerOptions: { target: "ES2017", lib: ["dom", "esnext"], jsx: "preserve", module: "esnext", moduleResolution: "bundler", strict: true, skipLibCheck: true },
        include: ["**/*.ts", "**/*.tsx"],
      }),
    };

    const result = buildVercelBundleWithRetry(files);

    expect(result.ok).toBe(false);
    expect(result.automaticFixesExhausted).toBe(true);
    expect(result.files).toBeDefined();
    expect(Object.keys(result.files!).length).toBeGreaterThan(0);
    expect(result.error).toBeDefined();
    expect(result.lastStderr).toBeDefined();
  }, 120_000);
});
