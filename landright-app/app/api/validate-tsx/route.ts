import { NextRequest, NextResponse } from "next/server";
import { validateTsx } from "@/lib/preview-compile";
import { MAX_TSX_LENGTH } from "@/lib/config";

export async function POST(request: NextRequest) {
  let body: { tsx?: string; spec?: { ctaEntries?: Array<{ url: string }> } };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const tsx = typeof body?.tsx === "string" ? body.tsx : "";
  if (tsx.length > MAX_TSX_LENGTH) {
    return NextResponse.json({ error: "tsx too long" }, { status: 400 });
  }

  const spec = body?.spec && typeof body.spec === "object" ? body.spec : undefined;
  const result = await validateTsx(tsx, { spec });
  return NextResponse.json(result);
}
