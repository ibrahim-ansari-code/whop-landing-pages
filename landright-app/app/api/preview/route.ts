import { NextRequest, NextResponse } from "next/server";
import { looksLikeTsx, compileTsxToHtml } from "@/lib/preview-compile";

const MAX_TSX_LENGTH = 1_500_000;

export async function POST(request: NextRequest) {
  let body: { tsx?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const tsx = typeof body?.tsx === "string" ? body.tsx : "";
  if (!tsx.trim()) {
    return NextResponse.json({ error: "Missing tsx" }, { status: 400 });
  }
  if (!looksLikeTsx(tsx)) {
    return NextResponse.json({ error: "Invalid tsx: expected a component with export default" }, { status: 400 });
  }
  if (tsx.length > MAX_TSX_LENGTH) {
    return NextResponse.json({ error: "tsx too long" }, { status: 400 });
  }

  const result = await compileTsxToHtml(tsx);
  if (!result.ok) {
    return NextResponse.json(
      { error: "Compile failed", details: result.error },
      { status: 422 }
    );
  }
  return NextResponse.json({ html: result.html });
}
