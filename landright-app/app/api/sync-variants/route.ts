import { NextRequest, NextResponse } from "next/server";
import { validateTsx } from "@/lib/preview-compile";
import { buildSyncHeaders, DEFAULT_LAYER_NAME, DEFAULT_COMMIT_MESSAGE_BUNDLE as DEFAULT_COMMIT_MESSAGE } from "@/lib/sync-utils";

const VARIANT_COUNT = 4;

/**
 * Push full Vercel bundle (app/page.tsx wrapper + layout + 4 variants + config) to GitHub
 * so the repo is a deployable Next.js app with variant selection and click tracking.
 * 1) GET full bundle from backend build-export-bundle.
 * 2) Push each file to repo root via sync agent (app/page.tsx, app/layout.tsx, app/variants/variant-*.tsx, etc.).
 */
export async function POST(request: NextRequest) {
  const syncAgentUrl = process.env.SYNC_AGENT_URL?.trim().replace(/\/$/, "");
  if (!syncAgentUrl) {
    return NextResponse.json(
      { error: "SYNC_AGENT_URL is not configured. Add it to .env.local (e.g. http://localhost:4000) and ensure the GitHub agent is running." },
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

  let body: { variants?: unknown; commitMessage?: string; layerName?: string; repoFullName?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const rawVariants = Array.isArray(body?.variants) ? body.variants : [];
  if (rawVariants.length !== VARIANT_COUNT) {
    return NextResponse.json(
      { error: `Exactly ${VARIANT_COUNT} variants required, got ${rawVariants.length}` },
      { status: 400 }
    );
  }
  const variants = rawVariants.map((v) => (typeof v === "string" ? v : String(v)));
  if (variants.some((v) => !v.trim())) {
    return NextResponse.json(
      { error: "All 4 variants must be non-empty strings" },
      { status: 400 }
    );
  }

  const layerName =
    typeof body?.layerName === "string" && body.layerName.trim() !== ""
      ? body.layerName.trim()
      : DEFAULT_LAYER_NAME;
  const commitMessage =
    typeof body?.commitMessage === "string" && body.commitMessage.trim() !== ""
      ? body.commitMessage.trim()
      : DEFAULT_COMMIT_MESSAGE;
  const repoFullName =
    typeof body?.repoFullName === "string" && body.repoFullName.trim() !== ""
      ? body.repoFullName.trim()
      : undefined;

  if (!repoFullName) {
    return NextResponse.json(
      { error: "repoFullName is required (e.g. owner/repo). Set it in the form or in the agent's GITHUB_REPO_FULL_NAME." },
      { status: 400 }
    );
  }

  const failed: { index: number; errors: string[] }[] = [];
  for (let i = 0; i < variants.length; i++) {
    const result = await validateTsx(variants[i]);
    if (!result.runnable) {
      failed.push({ index: i + 1, errors: result.errors });
    }
  }
  if (failed.length > 0) {
    const detail = failed.map((f) => `Variant ${f.index}: ${f.errors.join("; ")}`).join(". ");
    return NextResponse.json(
      {
        error: "One or more variants are not runnable (do not pass validation). Fix or regenerate before pushing.",
        failedVariants: failed.map((f) => f.index),
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
        variant_tsx_list: variants,
        repo_full_name: repoFullName,
        layer: layerName,
      }),
    });
    if (!bundleRes.ok) {
      const errText = await bundleRes.text();
      return NextResponse.json(
        { error: `Backend build-export-bundle failed: ${errText || bundleRes.status}` },
        { status: bundleRes.status >= 500 ? 502 : bundleRes.status }
      );
    }
    const data = await bundleRes.json();
    files = data.files || {};
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

  const layerForSnapshots = layerName.replace(/^layer-/, "") || "1";
  try {
    const snapRes = await fetch(`${backendUrl}/record-variant-snapshots`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_full_name: repoFullName,
        layer: layerForSnapshots,
        variants,
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

  return NextResponse.json({
    ok: true,
    message: `Full bundle pushed (${filePaths.length} files). Repo has app/page.tsx at root and is ready to deploy to Vercel.`,
  });
}
