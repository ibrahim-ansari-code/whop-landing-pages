import { describe, it, expect } from "vitest";
import {
  looksLikeTsx,
  hasResponsiveClasses,
  hasBrowserUnsafePatterns,
  checkTsxSyntax,
  validateTsx,
  compileTsxToHtml,
} from "./preview-compile";

const VALID_RESPONSIVE_TSX = `
import React from 'react';
export default function Page() {
  return (
    <div className="min-h-screen px-4 md:px-8 lg:max-w-6xl mx-auto">
      <h1 className="text-2xl sm:text-4xl">Hello</h1>
    </div>
  );
}
`;

const VALID_MINIMAL_TSX = `
export default function Page() {
  return <div className="p-4">Hi</div>;
}
`;

describe("looksLikeTsx", () => {
  it("accepts TSX with export default", () => {
    expect(looksLikeTsx("export default function X() { return null; }")).toBe(true);
    expect(looksLikeTsx(VALID_MINIMAL_TSX)).toBe(true);
  });
  it("rejects empty or no default export", () => {
    expect(looksLikeTsx("")).toBe(false);
    expect(looksLikeTsx("  \n  ")).toBe(false);
    expect(looksLikeTsx("function X() {}")).toBe(false);
    expect(looksLikeTsx("<html></html>")).toBe(false);
    expect(looksLikeTsx("<!DOCTYPE html>")).toBe(false);
  });
});

describe("hasResponsiveClasses", () => {
  it("detects Tailwind responsive prefixes", () => {
    expect(hasResponsiveClasses("class=\"md:flex lg:text-xl\"")).toBe(true);
    expect(hasResponsiveClasses("sm:px-4")).toBe(true);
    expect(hasResponsiveClasses("min-h-screen")).toBe(true);
  });
  it("returns false when no responsive classes", () => {
    expect(hasResponsiveClasses("class=\"p-4 text-xl\"")).toBe(false);
  });
});

describe("hasBrowserUnsafePatterns", () => {
  it("detects require and process.env", () => {
    expect(hasBrowserUnsafePatterns("require('fs')")).toBe(true);
    expect(hasBrowserUnsafePatterns("process.env.NODE_ENV")).toBe(true);
    expect(hasBrowserUnsafePatterns("import x from 'node:fs'")).toBe(true);
    expect(hasBrowserUnsafePatterns("from 'path'")).toBe(true);
  });
  it("returns false for clean TSX", () => {
    expect(hasBrowserUnsafePatterns(VALID_MINIMAL_TSX)).toBe(false);
  });
});

describe("validateTsx", () => {
  it("returns runnable and mobileFriendly for valid responsive TSX", async () => {
    const r = await validateTsx(VALID_RESPONSIVE_TSX);
    expect(r.runnable).toBe(true);
    expect(r.mobileFriendly).toBe(true);
    expect(r.browserSafe).toBe(true);
    expect(r.errors).toEqual([]);
  });

  it("returns runnable true but mobileFriendly false when no responsive classes", async () => {
    const r = await validateTsx(VALID_MINIMAL_TSX);
    expect(r.runnable).toBe(true);
    expect(r.mobileFriendly).toBe(false);
    expect(r.browserSafe).toBe(true);
    expect(r.errors.some((e) => e.includes("responsive"))).toBe(true);
  });

  it("returns runnable false for invalid TSX", async () => {
    const r = await validateTsx("not valid at all");
    expect(r.runnable).toBe(false);
    expect(r.errors.length).toBeGreaterThan(0);
  });

  it("returns runnable false for empty TSX", async () => {
    const r = await validateTsx("");
    expect(r.runnable).toBe(false);
    expect(r.errors).toContain("Empty TSX");
  });

  it("flags browser-unsafe code", async () => {
    const r = await validateTsx(`
      const x = process.env.FOO;
      export default function Page() { return <div>{x}</div>; }
    `);
    expect(r.browserSafe).toBe(false);
    expect(r.errors.some((e) => e.includes("Node") || e.includes("process"))).toBe(true);
  });
});

describe("compileTsxToHtml", () => {
  it("produces HTML for valid TSX", async () => {
    const out = await compileTsxToHtml(VALID_MINIMAL_TSX);
    expect(out.ok).toBe(true);
    if (out.ok) {
      expect(out.html).toContain("<!DOCTYPE html>");
      expect(out.html).toContain("<div id=\"root\">");
      expect(out.html).toContain("tailwindcss.com");
    }
  });

  it("returns error for invalid TSX", async () => {
    const out = await compileTsxToHtml("syntax error {{{");
    expect(out.ok).toBe(false);
    if (!out.ok) {
      expect(out.error.length).toBeGreaterThan(0);
    }
  });

  it("returns friendly error for unterminated string literal", async () => {
    const badTsx = `
export default function Page() {
  return <div className="unclosed>Hi</div>;
}
`;
    const out = await compileTsxToHtml(badTsx);
    expect(out.ok).toBe(false);
    if (!out.ok) {
      expect(out.error).toMatch(/unterminated\s+string\s+literal/i);
      expect(out.error).toMatch(/properly closed|matching/);
    }
  });
});

describe("checkTsxSyntax", () => {
  it("passes valid TSX", () => {
    expect(checkTsxSyntax(VALID_MINIMAL_TSX)).toEqual({ ok: true });
  });
  it("fails with friendly message for unterminated string", () => {
    const r = checkTsxSyntax(`
export default function Page() {
  return <div title="oops>x</div>;
}
`);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.message).toMatch(/unterminated|properly closed|matching/);
    }
  });
});
