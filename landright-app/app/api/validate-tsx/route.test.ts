import { describe, it, expect } from "vitest";
import { POST } from "./route";

const VALID_RESPONSIVE_TSX = `
export default function Page() {
  return (
    <div className="px-4 md:px-8 lg:max-w-6xl">
      <h1 className="text-2xl sm:text-4xl">Hi</h1>
    </div>
  );
}
`;

function req(body: unknown) {
  return new Request("http://localhost/api/validate-tsx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/validate-tsx", () => {
  it("returns runnable and mobileFriendly for valid responsive TSX", async () => {
    const res = await POST(req({ tsx: VALID_RESPONSIVE_TSX }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.runnable).toBe(true);
    expect(data.mobileFriendly).toBe(true);
    expect(data.browserSafe).toBe(true);
    expect(Array.isArray(data.errors)).toBe(true);
  });

  it("returns runnable false for invalid TSX", async () => {
    const res = await POST(req({ tsx: "not valid" }));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.runnable).toBe(false);
    expect(data.errors.length).toBeGreaterThan(0);
  });

  it("accepts empty body and returns validation result", async () => {
    const res = await POST(req({}));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.runnable).toBe(false);
    expect(data.errors).toContain("Empty TSX");
  });
});
