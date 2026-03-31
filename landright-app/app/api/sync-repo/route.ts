import { NextRequest, NextResponse } from "next/server";
import { validateTsx } from "@/lib/preview-compile";
import { buildSyncHeaders, DEFAULT_LAYER_NAME, DEFAULT_COMMIT_MESSAGE_SINGLE as DEFAULT_COMMIT_MESSAGE } from "@/lib/sync-utils";

/**
 * Push full Vercel bundle (app/page.tsx wrapper + layout + 4 variants + config) to GitHub.
 * Uses the chosen variant for all 4 slots so the repo is a deployable Next.js app.
 * 1) GET full bundle from backend build-export-bundle (variant_tsx_list = [data, data, data, data]).
 * 2) Push each file to repo root via sync agent.
 */
export async function POST(request: NextRequest) {
  const syncAgentUrl = process.env.SYNC_AGENT_URL?.trim().replace(/\/$/, "");
  if (!syncAgentUrl) {
    return NextResponse.json(
      { error: "SYNC_AGENT_URL is not configured" },
      { status: 503 }
    );
  }

  const backendUrl = process.env.NEXT_PUBLIC_GENERATE_API_URL?.trim().replace(/\/$/, "");
  if (!backendUrl) {
    return NextResponse.json(
      { error: "NEXT_PUBLIC_GENERATE_API_URL is not set. Backend is required to build the full export bundle." },
      { status: 503 }
    );
  }

  let body: { data?: string; commitMessage?: string; repoFullName?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const data = typeof body?.data === "string" ? body.data : "";
  if (!data.trim()) {
    return NextResponse.json(
      { error: "Missing or empty body.data (chosen variant content)" },
      { status: 400 }
    );
  }

  const repoFullName =
    typeof body?.repoFullName === "string" && body.repoFullName.trim() !== ""
      ? body.repoFullName.trim()
      : undefined;
  if (!repoFullName) {
    return NextResponse.json(
      { error: "repoFullName is required (e.g. owner/repo). Needed so the full app bundle can be pushed to the correct repo." },
      { status: 400 }
    );
  }

  const commitMessage =
    typeof body?.commitMessage === "string" && body.commitMessage.trim() !== ""
      ? body.commitMessage.trim()
      : DEFAULT_COMMIT_MESSAGE;

  const validation = await validateTsx(data);
  if (!validation.runnable) {
    const detail = validation.errors?.length ? validation.errors.join("; ") : "Does not compile";
    return NextResponse.json(
      {
        error: "Chosen variant is not runnable. Fix or pick another before pushing.",
        details: detail,
      },
      { status: 400 }
    );
  }

  let files: Record<string, string>;
  try {
    const bundleRes = await fetch(`${backendUrl}/build-export-bundle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        variant_tsx_list: [data, data, data, data],
        repo_full_name: repoFullName,
        layer: DEFAULT_LAYER_NAME,
      }),
    });
    if (!bundleRes.ok) {
      const errText = await bundleRes.text();
      return NextResponse.json(
        { error: `Backend build-export-bundle failed: ${errText || bundleRes.status}` },
        { status: bundleRes.status >= 500 ? 502 : bundleRes.status }
      );
    }
    const bundleData = await bundleRes.json();
    files = bundleData.files || {};
    if (Object.keys(files).length === 0) {
      return NextResponse.json({ error: "Backend returned no files" }, { status: 502 });
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Request failed";
    return NextResponse.json(
      { error: `Could not reach backend (${backendUrl}): ${msg}` },
      { status: 502 }
    );
  }

  try {
    const checkRes = await fetch(`${backendUrl}/vercel-compatibility-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
    if (checkRes.ok) {
      const checkData = await checkRes.json();
      const extraFiles = checkData?.extra_files;
      if (extraFiles && typeof extraFiles === "object" && Object.keys(extraFiles).length > 0) {
        files = { ...files, ...extraFiles };
      }
    }
  } catch {
    // Non-fatal: push without merge if check fails
  }

  const headers = buildSyncHeaders();
  const errors: string[] = [];
  const filePaths = Object.keys(files).sort();

  try {
    const healthRes = await fetch(`${syncAgentUrl}/health`, { method: "GET" });
    if (!healthRes.ok) {
      return NextResponse.json(
        {
          error: `Sync agent at ${syncAgentUrl} returned ${healthRes.status}. Start the agent (e.g. port 4000) and set SYNC_AGENT_URL in .env.local.`,
        },
        { status: 503 }
      );
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Connection failed";
    return NextResponse.json(
      {
        error: `Cannot reach sync agent at ${syncAgentUrl}. ${msg} Start the Python agent and set SYNC_AGENT_URL in .env.local.`,
      },
      { status: 503 }
    );
  }

  for (const filePath of filePaths) {
    const payload: { filePath: string; data: string; commitMessage: string; repo_full_name?: string } = {
      filePath,
      data: files[filePath],
      commitMessage,
      repo_full_name: repoFullName,
    };
    try {
      const res = await fetch(`${syncAgentUrl}/sync`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      const text = await res.text();
      if (!res.ok) {
        errors.push(`${filePath}: ${text || res.status}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Request failed";
      errors.push(`${filePath}: ${msg}`);
    }
  }

  if (errors.length > 0) {
    return NextResponse.json(
      { ok: false, error: "One or more syncs failed", details: errors },
      { status: 502 }
    );
  }
  return NextResponse.json({
    ok: true,
    message: `Full bundle pushed (${filePaths.length} files). Repo has app/ at root and is ready to deploy to Vercel.`,
  });
}
