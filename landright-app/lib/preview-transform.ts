/**
 * Transform TSX meant for Next.js so it can run in a standalone preview (browser bundle).
 * Stubs next/font (any font name), strips metadata and type-only imports.
 * Used by the preview API route and can be shared with client if needed.
 */
export function transformTsxForPreview(tsx: string): string {
  let code = tsx.trim();
  // Strip "use client" and "use server" anywhere (LLM may emit them in various places)
  code = code.replace(/^["']use (client|server)["']\s*;?\s*\n?/gm, "");
  code = code.replace(/\n\s*["']use (client|server)["']\s*;?\s*\n?/g, "\n");
  // Replace named font imports with single default stub + const bindings so any font name works
  code = code.replace(
    /import\s*\{\s*([^}]+)\s*\}\s*from\s*['"]next\/font\/google[^'"]*['"]\s*;?\s*/g,
    (_, names: string) => {
      const bindings = names.split(",").map((n: string) => n.trim()).filter(Boolean);
      if (bindings.length === 0) return "";
      const constLine = `const ${bindings.map((b: string) => `${b} = __fontStub`).join(", ")};`;
      return `import __fontStub from 'preview-font-stub';\n${constLine}\n`;
    }
  );
  code = code.replace(
    /import\s+(\w+)\s+from\s*['"]next\/font\/google[^'"]*['"]\s*;?\s*/g,
    "import __fontStub from 'preview-font-stub';\nconst $1 = __fontStub;\n"
  );
  // Stub next/script so preview bundle builds; Calendly script is injected in preview HTML when needed
  code = code.replace(
    /import\s+(\w+)\s+from\s*['"]next\/script['"]\s*;?\s*/g,
    "const $1 = function ScriptStub(_props: unknown) { return null; };\n"
  );
  // Stub next/image so preview bundle builds (LLM may emit it)
  code = code.replace(
    /import\s+(\w+)\s+from\s*['"]next\/image['"]\s*;?\s*/g,
    "const $1 = function ImageStub(_p: unknown) { return null; };\n"
  );
  // Stub next/link so preview bundle builds; render as <a> so links work in standalone preview
  code = code.replace(
    /import\s+(\w+)\s+from\s*['"]next\/link['"]\s*;?\s*/g,
    "const $1 = function LinkStub(p) { return React.createElement('a', { href: p.href || '#', ...p }, p.children); };\n"
  );
  // Catch-all: any other next/* import (e.g. next/head, or malformed next/image) -> generic stub
  code = code.replace(
    /import\s+(\w+)\s+from\s*['"]next\/[^'"]*['"]\s*;?\s*/g,
    "const $1 = function NextStub(_p: unknown) { return null; };\n"
  );
  code = code.replace(/import\s+type\s+[^;]+;?\s*\n?/g, "");
  code = code.replace(/export\s+const\s+metadata\s*=\s*\{[\s\S]*?\}\s*;?\s*\n?/g, "// metadata omitted\n");
  // Strip styled-jsx (Next.js) so preview bundle doesn't crash - we don't run that transform
  code = code.replace(/<style\s+jsx(?:\s+[^>]*)?>[\s\S]*?<\/style>/g, "/* styled-jsx stripped for preview */");
  return code;
}

/**
 * Strip TypeScript syntax so the result is valid JSX only (for esbuild loader "jsx").
 * Used as fallback when ts.transpileModule fails on LLM output.
 */
export function stripTypesForJsx(code: string): string {
  let out = code;
  // Return type before { : ): JSX.Element { -> ) {
  out = out.replace(/\)\s*:\s*[A-Za-z0-9._<>[\]\s|]+\s*\{/g, ") {");
  // Return type before => : ): Type => -> ) =>
  out = out.replace(/\)\s*:\s*[A-Za-z0-9._<>[\]\s|]+\s*=>/g, ") =>");
  // Type assertion: value as SomeType
  out = out.replace(/\s+as\s+[A-Za-z0-9._<>[\]\s|]+(?=[\s;,)\]}>])/g, "");
  // Variable/param type annotations: const x: Type = -> const x = , let x: Type = -> let x =
  out = out.replace(/(\bconst|\blet|\bvar)\s+(\{[^}]*\}|[\w.]+)\s*:\s*[^=]+=/g, "$1 $2 =");
  // Function param types: (x: Type) -> (x) , (x: Type, y: Type) -> (x, y)
  out = out.replace(/(\()(\s*\w+\s*):\s*[^),]+/g, "$1$2");
  // Remove interface/type declarations: multi-line interface/type ... { ... }
  out = out.replace(/^\s*(?:export\s+)?interface\s+\w+[\s\S]*?^\s*}\s*;?\s*/gm, "");
  out = out.replace(/^\s*(?:export\s+)?type\s+\w+\s*=\s*[^;]+;\s*$/gm, "");
  return out;
}

/** Single default export; transformTsxForPreview rewrites font imports to use this. */
export const PREVIEW_FONT_STUB = `function __fontStub() { return { className: "font-sans", style: {} }; }
export default __fontStub;
`;
