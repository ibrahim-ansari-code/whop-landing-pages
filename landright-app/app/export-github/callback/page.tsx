"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { STORAGE_KEYS, GENERATE_API_BASE, GITHUB_APP_INSTALL_URL } from "@/lib/config";

type Status = "idle" | "exchanging" | "validating" | "pushing" | "success" | "error";

function ExportGitHubCallbackContent() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string>("");
  const [repoFullName, setRepoFullName] = useState<string | null>(null);

  const run = useCallback(async () => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    if (!code || !state) {
      setStatus("error");
      setMessage("Missing code or state from GitHub.");
      return;
    }
    if (typeof window === "undefined") return;
    const savedState = sessionStorage.getItem("github_oauth_state");
    if (savedState !== state) {
      setStatus("error");
      setMessage("Invalid state (possible CSRF). Try again from the generate page.");
      return;
    }
    const pendingRaw = sessionStorage.getItem(STORAGE_KEYS.EXPORT_PENDING);
    const variantsRaw = sessionStorage.getItem(STORAGE_KEYS.VARIANTS);
    if (!pendingRaw || !variantsRaw) {
      setStatus("error");
      setMessage("Missing export data. Please start Export to GitHub from the generate page.");
      return;
    }
    let pending: { repoName: string; layer: string };
    let variantList: string[];
    try {
      pending = JSON.parse(pendingRaw) as { repoName: string; layer: string };
      variantList = JSON.parse(variantsRaw) as string[];
    } catch {
      setStatus("error");
      setMessage("Invalid saved data. Try again from the generate page.");
      return;
    }
    if (!Array.isArray(variantList) || variantList.length !== 4) {
      setStatus("error");
      setMessage("Need exactly 4 variants. Generate again and use Export to GitHub.");
      return;
    }
    const base = (GENERATE_API_BASE || "").replace(/\/$/, "");
    if (!base) {
      setStatus("error");
      setMessage("Backend URL not configured (NEXT_PUBLIC_GENERATE_API_URL).");
      return;
    }

    setStatus("exchanging");
    let accessToken: string;
    const redirectUri = typeof window !== "undefined" ? `${window.location.origin}/export-github/callback` : "";
    try {
      const res = await fetch(`${base}/github-oauth-exchange`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, redirect_uri: redirectUri || undefined }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Exchange failed: ${res.status}`);
      }
      const data = (await res.json()) as { access_token?: string };
      const token = data.access_token;
      if (!token) throw new Error("No access_token in response");
      accessToken = token;
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "OAuth exchange failed.");
      return;
    }

    setStatus(typeof window !== "undefined" && window.location.origin ? "validating" : "pushing");
    try {
      // Validate all 4 variants are runnable before creating repo and pushing
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      if (origin) {
        for (let i = 0; i < variantList.length; i++) {
          const res = await fetch(`${origin}/api/validate-tsx`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tsx: variantList[i] }),
          });
          const v = (await res.json().catch(() => ({}))) as { runnable?: boolean; errors?: string[] };
          if (!v.runnable) {
            const msg = (v.errors && v.errors.length) ? v.errors.join("; ") : "Does not compile";
            setStatus("error");
            setMessage(`Variant ${i + 1} is not runnable: ${msg}. Fix or regenerate before exporting.`);
            return;
          }
        }
      }
      setStatus("pushing");
      const res = await fetch(`${base}/create-repo-and-push`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          github_access_token: accessToken,
          repo_name: pending.repoName,
          variant_tsx_list: variantList,
          layer: pending.layer || "1",
        }),
      });
      const data = (await res.json().catch(() => ({}))) as { repo_full_name?: string; detail?: string | string[] };
      if (!res.ok) {
        const detailMsg = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.join(" ") : res.statusText;
        throw new Error(detailMsg);
      }
      setRepoFullName(data.repo_full_name ?? null);
      sessionStorage.removeItem(STORAGE_KEYS.EXPORT_PENDING);
      sessionStorage.removeItem("github_oauth_state");
      setStatus("success");
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Create repo / push failed.");
    }
  }, [searchParams]);

  useEffect(() => {
    if (status === "idle") run();
  }, [status, run]);

  return (
    <div className="min-h-screen bg-black text-white flex items-center justify-center">
      <div className="max-w-md mx-auto px-6 py-12 text-center">
        {(status === "idle" || status === "exchanging" || status === "validating" || status === "pushing") && (
          <p className="text-white/80">
            {status === "idle" && "Starting..."}
            {status === "exchanging" && "Exchanging code for token..."}
            {status === "validating" && "Validating variants..."}
            {status === "pushing" && "Creating repo and pushing bundle..."}
          </p>
        )}
        {status === "success" && repoFullName && (
          <>
            <h1 className="text-xl font-semibold text-white">Repo created</h1>
            <p className="mt-2 text-white/70">{repoFullName}</p>
            <a
              href={`https://github.com/${repoFullName}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-block rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-400"
            >
              Open on GitHub
            </a>
            <p className="mt-4 text-sm text-white/60">Connect this repo to Vercel to deploy.</p>
            {GITHUB_APP_INSTALL_URL ? (
              <>
                <p className="mt-2 text-sm text-white/50">
                  Allow the Landright agent to optimize CTAs automatically by installing the app on your account.
                </p>
                <a
                  href={GITHUB_APP_INSTALL_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-block rounded-lg border border-orange-500/50 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500/20"
                >
                  Install Landright GitHub App
                </a>
              </>
            ) : (
              <p className="mt-2 text-sm text-white/50">
                For automatic CTA optimization, the Landright agent needs access (use <code className="bg-white/10 px-1 rounded">GITHUB_TOKEN</code> or configure the GitHub App install URL in the app).
              </p>
            )}
            <Link href="/generate" className="mt-6 block text-sm text-orange-400 hover:underline">
              Back to Generate
            </Link>
          </>
        )}
        {status === "error" && (
          <>
            <h1 className="text-xl font-semibold text-red-400">Export failed</h1>
            <p className="mt-2 text-white/70">{message}</p>
            <Link href="/generate" className="mt-6 inline-block text-sm text-orange-400 hover:underline">
              Back to Generate
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

export default function ExportGitHubCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-black text-white flex items-center justify-center">
          <p className="text-white/80">Loading...</p>
        </div>
      }
    >
      <ExportGitHubCallbackContent />
    </Suspense>
  );
}
