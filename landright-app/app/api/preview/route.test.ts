import { describe, it, expect } from "vitest";
import { POST } from "./route";

const VALID_TSX = `export default function Page() {
  return <div className="p-4 md:p-8">Hello</div>;
}
`;

function req(body: unknown) {
  return new Request("http://localhost/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/preview", () => {
  it("returns 200 and html for valid TSX", async () => {
    const res = await POST(req({ tsx: VALID_TSX }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.html).toBeDefined();
    expect(data.html).toContain("<!DOCTYPE html>");
    expect(data.html).toContain("<div id=\"root\">");
  });

  it("returns 200 for TSX that already has import React (no duplicate declaration)", async () => {
    const tsxWithReact = `import React from 'react';\nexport default function Page() { return <div className="p-4">Hi</div>; }\n`;
    const res = await POST(req({ tsx: tsxWithReact }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.html).toBeDefined();
    expect(data.html).toContain("<!DOCTYPE html>");
  });

  it("returns 200 for TSX with import React (double quotes) and useState", async () => {
    const tsx = `import React from "react";\nimport { useState } from "react";\nexport default function Page() { const [x, setX] = useState(0); return <div>{x}</div>; }\n`;
    const res = await POST(req({ tsx }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.html).toBeDefined();
    expect(data.html).toContain("<div id=\"root\">");
  });

  it("returns 200 for template-style TSX (use client + useState, no explicit React import)", async () => {
    const tsx = `"use client";\n\nimport { useState } from "react";\nexport default function Page() {\n  const [show, setShow] = useState(false);\n  return <div className="min-h-screen"><button onClick={() => setShow(true)}>Book</button>{show && <span>Hi</span>}</div>;\n}\n`;
    const res = await POST(req({ tsx }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.html).toBeDefined();
    expect(data.html).toContain("<!DOCTYPE html>");
  });

  it("returns 400 for missing tsx", async () => {
    const res = await POST(req({}));
    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.error).toBeDefined();
  });

  it("returns 400 for invalid JSON", async () => {
    const res = await POST(
      new Request("http://localhost/api/preview", {
        method: "POST",
        body: "not json",
      })
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 when tsx has no export default", async () => {
    const res = await POST(req({ tsx: "function X() { return null; }" }));
    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.error).toMatch(/export default|Invalid tsx/i);
  });

  it("returns 422 when TSX does not compile", async () => {
    // Invalid JSX: unclosed brace in expression causes compile failure
    const res = await POST(
      req({
        tsx: "export default function Page() { return <div className={>x</div>; }",
      })
    );
    expect(res.status).toBe(422);
    const data = await res.json();
    expect(data.error).toBeDefined();
  });
});
