import { NextRequest, NextResponse } from "next/server";
import { buildSyncHeaders } from "@/lib/sync-utils";

/**
 * Forward dashboard "implement" requests to the sync agent.
 * Body: { repoFullName: string, message: string, scope?: string }
 */
export async function POST(request: NextRequest) {
  const syncAgentUrl = process.env.SYNC_AGENT_URL?.trim().replace(/\/$/, "");
  if (!syncAgentUrl) {
    return NextResponse.json(
      { error: "SYNC_AGENT_URL is not configured. Add it to .env.local and run the sync agent." },
      { status: 503 }
    );
  }

  let body: { repoFullName?: string; message?: string; scope?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const repoFullName = typeof body?.repoFullName === "string" ? body.repoFullName.trim() : "";
  if (!repoFullName) {
    return NextResponse.json(
      { error: "repoFullName is required (e.g. owner/repo)." },
      { status: 400 }
    );
  }

  const instruction = typeof body?.message === "string" ? body.message.trim() : "";
  if (!instruction) {
    return NextResponse.json(
      { error: "message (instruction) is required." },
      { status: 400 }
    );
  }

  const scope = typeof body?.scope === "string" && body.scope.trim() ? body.scope.trim() : "all";

  try {
    const res = await fetch(`${syncAgentUrl}/implement`, {
      method: "POST",
      headers: buildSyncHeaders(),
      body: JSON.stringify({
        repo_full_name: repoFullName,
        instruction,
        scope,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : res.statusText;
      return NextResponse.json(
        { error: detail || "Implement failed" },
        { status: res.status >= 500 ? 502 : res.status }
      );
    }
    return NextResponse.json({
      ok: true,
      message: (data as { message?: string }).message ?? "Done.",
      pushed: (data as { pushed?: string[] }).pushed ?? [],
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Request failed";
    return NextResponse.json(
      { error: `Cannot reach sync agent: ${msg}` },
      { status: 503 }
    );
  }
}
