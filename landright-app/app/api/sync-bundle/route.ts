import { NextRequest, NextResponse } from "next/server";
import { buildVercelBundleWithRetry } from "@/lib/vercel-build-with-retry";

const DEFAULT_LAYER_NAME = "layer-1";
const DEFAULT_COMMIT_MESSAGE = "Deploy 4 variants from Landright";

function buildSyncHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const apiKey = process.env.SYNC_AGENT_API_KEY?.trim();
  if (apiKey) {
    headers["x-api-key"] = apiKey;
    headers["Authorization"] = `Bearer ${apiKey}`;
  }
  return headers;
}

/**
 * Build a provided bundle and push to GitHub. Used when automatic fixes were exhausted:
 * client sends the returned `files` (optionally edited) and we run build + sync.
 * Gives the client full control to fix the bundle and retry.
 */
export async function POST(request: NextRequest) {
  const syncAgentUrl = process.env.SYNC_AGENT_URL?.trim().replace(/\/$/, "");
  if (!syncAgentUrl) {
    return NextResponse.json(
      { error: "SYNC_AGENT_URL is not configured." },
      { status: 503 }
    );
  }

  let body: {
    files?: Record<string, string>;
    repoFullName?: string;
    commitMessage?: string;
    layerName?: string;
    /** When true, skip local build check and push bundle so it always reaches GitHub (Vercel will build on deploy). */
    skipBuildCheck?: boolean;
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const skipBuildCheck = body?.skipBuildCheck === true;

  const files =
    body?.files && typeof body.files === "object" && !Array.isArray(body.files)
      ? body.files
      : undefined;
  if (!files || Object.keys(files).length === 0) {
    return NextResponse.json(
      { error: "body.files (record of path -> content) is required." },
      { status: 400 }
    );
  }

  const repoFullName =
    typeof body?.repoFullName === "string" && body.repoFullName.trim() !== ""
      ? body.repoFullName.trim()
      : undefined;
  if (!repoFullName) {
    return NextResponse.json(
      { error: "repoFullName is required." },
      { status: 400 }
    );
  }

  const commitMessage =
    typeof body?.commitMessage === "string" && body.commitMessage.trim() !== ""
      ? body.commitMessage.trim()
      : DEFAULT_COMMIT_MESSAGE;
  const _layerName =
    typeof body?.layerName === "string" && body.layerName.trim() !== ""
      ? body.layerName.trim()
      : DEFAULT_LAYER_NAME;
  void _layerName;

  let finalFiles: Record<string, string>;
  if (skipBuildCheck) {
    finalFiles = files;
  } else {
    const buildResult = buildVercelBundleWithRetry(files);
    if (!buildResult.ok) {
      return NextResponse.json(
        {
          error: buildResult.error ?? "Vercel build failed",
          lastStderr: buildResult.lastStderr,
          attempts: buildResult.attempts,
          automaticFixesExhausted: buildResult.automaticFixesExhausted ?? false,
          files: buildResult.files ?? files,
        },
        { status: 400 }
      );
    }
    finalFiles = buildResult.files ?? files;
  }
  const headers = buildSyncHeaders();
  const errors: string[] = [];
  const filePaths = Object.keys(finalFiles).sort();

  // Check sync agent is reachable before pushing many files (avoids N× "fetch failed")
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
    const payload = {
      filePath,
      data: finalFiles[filePath],
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

  const backendUrl = process.env.NEXT_PUBLIC_GENERATE_API_URL?.trim().replace(/\/$/, "");
  const variantPaths = ["app/variants/variant-1.tsx", "app/variants/variant-2.tsx", "app/variants/variant-3.tsx", "app/variants/variant-4.tsx"];
  const variantTsxList = variantPaths.map((p) => finalFiles[p]).filter(Boolean);
  if (backendUrl && variantTsxList.length === 4) {
    const layerName = typeof body?.layerName === "string" && body.layerName.trim() !== "" ? body.layerName.trim() : DEFAULT_LAYER_NAME;
    const layerForSnapshots = layerName.replace(/^layer-/, "") || "1";
    try {
      const snapRes = await fetch(`${backendUrl}/record-variant-snapshots`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_full_name: repoFullName,
          layer: layerForSnapshots,
          variants: variantTsxList,
          source: "deploy",
        }),
      });
      if (!snapRes.ok) {
        const errText = await snapRes.text();
        console.warn("record-variant-snapshots failed (push succeeded):", snapRes.status, errText);
      }
    } catch (e) {
      console.warn("record-variant-snapshots request failed (push succeeded):", e);
    }
  }

  return NextResponse.json({
    ok: true,
    message: `Bundle pushed (${filePaths.length} files). Repo is ready to deploy to Vercel.`,
  });
}
