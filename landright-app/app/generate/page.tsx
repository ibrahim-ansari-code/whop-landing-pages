"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { DesignSpec } from "@/lib/design-spec";
import { STORAGE_KEYS, GENERATE_API_BASE, DEFAULT_PROMPT_ID, AGENT_URL, GITHUB_CLIENT_ID, GITHUB_APP_INSTALL_URL } from "@/lib/config";
import { COPY } from "@/lib/copy";
import { IMPLEMENTATION_INSTRUCTIONS_TSX, IMPLEMENTATION_INSTRUCTIONS_HTML } from "@/lib/implementation-instructions";
import { TsxPreview } from "@/components/TsxPreview";

/** True if variant content is TSX (Next.js component), false if HTML (template fallback). */
function isTsxVariant(content: string): boolean {
  const t = content.trim();
  return !t.startsWith("<!DOCTYPE") && !t.startsWith("<html") && t.includes("export default");
}

type VariantState = "loading" | "show" | "picked";

/** Python backend URL. Generation is handled by Python only; no Next.js proxy. */
const PYTHON_BACKEND_URL = GENERATE_API_BASE ?? "";
const MISSING_BACKEND_MSG =
  "Set NEXT_PUBLIC_GENERATE_API_URL to your Python backend (e.g. http://localhost:8000).";

export default function GeneratePage() {
  const router = useRouter();
  const [spec, setSpec] = useState<DesignSpec | null>(null);
  const [variants, setVariants] = useState<string[]>([]);
  const [variantReasoning, setVariantReasoning] = useState<string[]>([]);
  const [conversionDrivers, setConversionDrivers] = useState<string[][]>([]);
  const [state, setState] = useState<VariantState>("loading");
  const [viewingIndex, setViewingIndex] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [done, setDone] = useState(false);
  const [chosenFinalHtml, setChosenFinalHtml] = useState<string | null>(null);
  const [showExport, setShowExport] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState(false);
  const [experienceLibrary, setExperienceLibrary] = useState<string[]>([]);
  const [refinementRound, setRefinementRound] = useState(1);
  const [similarityRound, setSimilarityRound] = useState(0);
  const [loadingStepIndex, setLoadingStepIndex] = useState(0);
  const [validation, setValidation] = useState<{
    runnable: boolean;
    mobileFriendly: boolean;
    browserSafe: boolean;
    sameButtons?: boolean;
    errors: string[];
  } | null>(null);
  const [showAgentPanel, setShowAgentPanel] = useState(false);
  const [agentUploadedVariants, setAgentUploadedVariants] = useState<string[] | null>(null);
  const [agentSending, setAgentSending] = useState(false);
  const [agentResult, setAgentResult] = useState<{ success: boolean; message: string } | null>(null);
  const [syncPushing, setSyncPushing] = useState(false);
  const [syncResult, setSyncResult] = useState<{ success: boolean; message: string } | null>(null);
  const [syncRepoFullName, setSyncRepoFullName] = useState("");
  const [syncCommitMessage, setSyncCommitMessage] = useState("Update landing page from Landright");
  const [syncVariantsPushing, setSyncVariantsPushing] = useState(false);
  const [syncVariantsResult, setSyncVariantsResult] = useState<{ success: boolean; message: string } | null>(null);
  const [syncVariantsLayerName, setSyncVariantsLayerName] = useState("layer-1");
  const [syncVariantsCommitMessage, setSyncVariantsCommitMessage] = useState("Deploy 4 variants from Landright");
  const [syncVariantsRepoFullName, setSyncVariantsRepoFullName] = useState("");
  const [exportToGitHubRepoName, setExportToGitHubRepoName] = useState("");
  const [exportToGitHubLayer, setExportToGitHubLayer] = useState("1");
  const [competitorDna, setCompetitorDna] = useState<Record<string, unknown> | null>(null);
  const [useCritic, setUseCritic] = useState(false);
  const initialFetchDone = useRef(false);

  const fetchVariants = useCallback(
    async (opts?: {
      chosenVariantTsx?: string;
      selectedVariantIndex?: number;
      experienceLibrary?: string[];
      variantTsxList?: string[];
      similarityRound?: number;
    }) => {
      if (!spec) {
        console.log("[Landright Generate] fetchVariants skipped: no spec");
        return;
      }
      if (!PYTHON_BACKEND_URL) {
        console.warn("[Landright Generate] missing backend URL");
        setError(MISSING_BACKEND_MSG);
        setState("show");
        setVariants([]);
        return;
      }
      setError(null);
      setState("loading");
      const isRefinement = !!opts?.chosenVariantTsx && opts.selectedVariantIndex != null;
      console.log("[Landright Generate] fetchVariants", { isRefinement, selectedVariantIndex: opts?.selectedVariantIndex });
      try {
        const url = `${PYTHON_BACKEND_URL}/generate`;
        const body: Record<string, unknown> = {
          spec,
          promptId: DEFAULT_PROMPT_ID,
          useCritic,
          ...(competitorDna ? { competitorDna } : {}),
          ...(isRefinement
            ? {
                chosenVariantHtml: opts!.chosenVariantTsx,
                selectedVariantIndex: opts!.selectedVariantIndex,
                experienceLibrary: opts!.experienceLibrary ?? [],
                variantTsxList: opts!.variantTsxList ?? [],
                similarityRound: opts!.similarityRound ?? 0,
              }
            : {}),
        };
        console.log("[Landright Generate] POST", url);
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        console.log("[Landright Generate] response", res.status, res.statusText);
        let data: { error?: string; message?: string; details?: string; detail?: string | { error?: string; details?: string }; variants?: unknown; experienceLibrary?: string[]; retry_after?: number };
        try {
          const text = await res.text();
          data = text ? (JSON.parse(text) as typeof data) : {};
        } catch {
          throw new Error(res.ok ? "Invalid response from server" : `Generation failed (${res.status})`);
        }
        if (!res.ok) {
          if (res.status === 503 && (data?.error === "rate_limit" || (typeof data?.detail === "object" && data?.detail?.error === "rate_limit"))) {
            throw new Error(COPY.GENERATE.ERROR_RATE_LIMIT);
          }
          const detailRaw = data?.detail;
          const errorMsg =
            typeof data?.error === "string"
              ? data.error
              : typeof data?.message === "string"
                ? data.message
                : typeof detailRaw === "string"
                  ? detailRaw
                  : typeof detailRaw === "object" && detailRaw !== null && typeof (detailRaw as { error?: string }).error === "string"
                    ? (detailRaw as { error: string }).error
                    : "Generation failed";
          let details = typeof data?.details === "string" ? data.details : "";
          if (typeof detailRaw === "object" && detailRaw !== null && typeof (detailRaw as { details?: string }).details === "string") {
            details = (detailRaw as { details: string }).details;
          }
          const fullMsg = details && !errorMsg.includes(details) ? `${errorMsg}\n${details}` : errorMsg;
          throw new Error(fullMsg);
        }
        if (!Array.isArray(data.variants) || data.variants.length < 1) {
          throw new Error("Invalid response: expected at least one variant");
        }
        const list = data.variants as string[];
        if (!isRefinement) {
          setSimilarityRound(0);
        }
        console.log("[Landright Generate] got variants", list.length, "experienceLibrary", (data.experienceLibrary as string[])?.length ?? 0);
        setVariants(list);
        if (Array.isArray((data as Record<string, unknown>).reasoning)) {
          setVariantReasoning((data as Record<string, unknown>).reasoning as string[]);
        } else {
          setVariantReasoning([]);
        }
        if (Array.isArray((data as Record<string, unknown>).conversionDrivers)) {
          setConversionDrivers((data as Record<string, unknown>).conversionDrivers as string[][]);
        } else {
          setConversionDrivers([]);
        }
        if (Array.isArray(data.experienceLibrary)) {
          setExperienceLibrary(data.experienceLibrary);
        }
        if (isRefinement) {
          setRefinementRound((r: number) => r + 1);
          if (opts?.variantTsxList != null && opts.variantTsxList.length > 0) {
            setSimilarityRound((r: number) => r + 1);
          }
        }
        setState("show");
        setViewingIndex(0);
        setSelectedIndex(null);
        initialFetchDone.current = true;
      } catch (e) {
        let message = e instanceof Error ? e.message : "Something went wrong";
        if (message === "Failed to fetch" || /NetworkError|load failed/i.test(message)) {
          message = `${message}. Make sure the backend is running (e.g. \`cd backend && python3 -m uvicorn main:app --port 8000\`) and NEXT_PUBLIC_GENERATE_API_URL is set (e.g. http://localhost:8000).`;
        }
        console.error("[Landright Generate] fetch error", e);
        setError(message);
        setState("show");
        if (!isRefinement) {
          setVariants([]);
          initialFetchDone.current = false;
        }
      }
    },
    [spec, competitorDna, useCritic]
  );

  useEffect(() => {
    const storedSpec = typeof window !== "undefined" ? sessionStorage.getItem(STORAGE_KEYS.SPEC) : null;
    console.log("[Landright Generate] load spec from storage", storedSpec ? "ok" : "missing");
    if (!storedSpec) {
      router.replace("/");
      return;
    }
    try {
      const parsed = JSON.parse(storedSpec) as DesignSpec;
      setSpec(parsed);
      console.log("[Landright Generate] spec loaded", parsed?.websiteInformation?.name);
      const storedDna = sessionStorage.getItem("landright-competitor-dna");
      if (storedDna) {
        try {
          setCompetitorDna(JSON.parse(storedDna) as Record<string, unknown>);
          console.log("[Landright Generate] competitor DNA loaded");
        } catch { /* ignore */ }
      }
      const storedUseCritic = sessionStorage.getItem("landright-use-critic");
      if (storedUseCritic !== null) {
        try {
          setUseCritic(JSON.parse(storedUseCritic) as boolean);
        } catch { /* ignore */ }
      }
    } catch (e) {
      console.error("[Landright Generate] invalid spec in storage", e);
      router.replace("/");
    }
  }, [router]);

  // Load default (pre-built) experience library at session start (paper: token prior)
  useEffect(() => {
    if (!PYTHON_BACKEND_URL) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${PYTHON_BACKEND_URL}/experience-library`);
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as { experienceLibrary?: string[] };
        if (!cancelled && Array.isArray(data.experienceLibrary) && data.experienceLibrary.length > 0) {
          setExperienceLibrary(data.experienceLibrary);
          console.log("[Landright Generate] loaded default experience library", data.experienceLibrary.length, "items");
        }
      } catch {
        // ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!spec || initialFetchDone.current || regenerating) return;
    if (variants.length === 0 && state === "loading") {
      fetchVariants();
    }
  }, [spec, variants.length, state, regenerating, fetchVariants]);

  // Rotate loading step message with varied timing (1.2s–3.2s) and occasional random jump for variety
  useEffect(() => {
    if (state !== "loading") return;
    const steps = COPY.GENERATE.LOADING_STEPS;
    if (!steps?.length) return;
    let timeoutId: ReturnType<typeof setTimeout>;
    const scheduleNext = () => {
      const baseMs = 1200 + Math.random() * 2000;
      timeoutId = setTimeout(() => {
        setLoadingStepIndex((i) => {
          const len = steps.length;
          if (Math.random() < 0.25) return Math.floor(Math.random() * len);
          return (i + 1) % len;
        });
        scheduleNext();
      }, baseMs);
    };
    scheduleNext();
    return () => clearTimeout(timeoutId);
  }, [state]);

  // Validate current variant (runnable + mobile-friendly) when viewing changes
  useEffect(() => {
    const tsx = variants[viewingIndex] ?? "";
    if (!tsx.trim() || !isTsxVariant(tsx)) {
      setValidation(null);
      return;
    }
    let cancelled = false;
    setValidation(null);
    (async () => {
      try {
        const res = await fetch("/api/validate-tsx", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tsx, spec: spec ?? undefined }),
        });
        const data = await res.json();
        if (!cancelled && data && typeof data.runnable === "boolean") {
          setValidation({
            runnable: data.runnable,
            mobileFriendly: !!data.mobileFriendly,
            browserSafe: !!data.browserSafe,
            sameButtons: data.sameButtons,
            errors: Array.isArray(data.errors) ? data.errors : [],
          });
        }
      } catch {
        if (!cancelled) setValidation(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [viewingIndex, variants, spec]);

  function handlePick(index: number) {
    console.log("[Landright Generate] handlePick", index);
    setSelectedIndex(index);
    setState("picked");
  }

  const [deployPushing, setDeployPushing] = useState(false);
  const [deployResult, setDeployResult] = useState<{ success: boolean; message: string } | null>(null);

  async function handleDeployToAgent() {
    if (selectedIndex == null || !variants[selectedIndex]) return;
    if (!PYTHON_BACKEND_URL) {
      setDeployResult({ success: false, message: "Set NEXT_PUBLIC_GENERATE_API_URL (e.g. http://localhost:8000) to deploy." });
      return;
    }
    const tsx = variants[selectedIndex];
    const reasoning = variantReasoning[selectedIndex] || "";
    const drivers = conversionDrivers[selectedIndex] || [];
    setDeployPushing(true);
    setDeployResult(null);
    try {
      const res = await fetch(`${PYTHON_BACKEND_URL}/deploy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tsx,
          reasoning,
          conversionDrivers: drivers,
          companyName: spec?.websiteInformation?.name || "",
          variantIndex: selectedIndex,
        }),
      });
      if (res.ok) {
        setDeployResult({ success: true, message: "Deployed to agent successfully" });
      } else {
        const text = await res.text().catch(() => "");
        setDeployResult({ success: false, message: text || `Agent returned ${res.status}` });
      }
    } catch (e) {
      setDeployResult({ success: false, message: e instanceof Error ? e.message : "Deploy failed" });
    } finally {
      setDeployPushing(false);
    }
  }

  function handleSatisfied() {
    console.log("[Landright Generate] handleSatisfied", { selectedIndex });
    if (selectedIndex != null && variants[selectedIndex]) {
      setChosenFinalHtml(variants[selectedIndex]);
    }
    if (variants.length >= 4 && typeof window !== "undefined") {
      sessionStorage.setItem(STORAGE_KEYS.VARIANTS, JSON.stringify(variants.slice(0, 4)));
    }
    setDone(true);
  }

  function handleCopyHtml() {
    if (!chosenFinalHtml) return;
    navigator.clipboard.writeText(chosenFinalHtml).then(() => {
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    });
  }

  function handleDownload() {
    if (!chosenFinalHtml) return;
    const isTsx = isTsxVariant(chosenFinalHtml);
    const name = spec?.websiteInformation?.name?.replace(/[^a-z0-9-_]/gi, "-") || "landing";
    const filename = isTsx ? "page.tsx" : `${name}.html`;
    const mime = isTsx ? "text/tsx" : "text/html";
    const blob = new Blob([chosenFinalHtml], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handlePushToGitHub() {
    const repo = syncRepoFullName.trim();
    if (!repo) {
      setSyncResult({ success: false, message: "Enter GitHub repo (owner/repo)." });
      return;
    }
    const four = variants.slice(0, 4);
    if (four.length !== 4 || four.some((v) => !v?.trim())) {
      setSyncResult({ success: false, message: "Need exactly 4 variants to push the full Vercel bundle. Generate 4, then push." });
      return;
    }
    if (!PYTHON_BACKEND_URL) {
      setSyncResult({ success: false, message: MISSING_BACKEND_MSG });
      return;
    }
    setSyncPushing(true);
    setSyncResult(null);
    try {
      const bundleRes = await fetch(`${PYTHON_BACKEND_URL}/build-export-bundle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variant_tsx_list: four,
          repo_full_name: repo,
          layer: "1",
        }),
      });
      const bundleData = (await bundleRes.json().catch(() => ({}))) as { files?: Record<string, string>; detail?: string };
      if (!bundleRes.ok) {
        const msg = typeof bundleData.detail === "string" ? bundleData.detail : bundleRes.statusText;
        setSyncResult({ success: false, message: msg || "Failed to build export bundle." });
        return;
      }
      const files = bundleData.files;
      if (!files || Object.keys(files).length === 0) {
        setSyncResult({ success: false, message: "Backend returned no bundle files." });
        return;
      }
      const res = await fetch("/api/sync-bundle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          files,
          repoFullName: repo,
          commitMessage: syncCommitMessage.trim() || "Update landing page from Landright",
          layerName: "layer-1",
          skipBuildCheck: true,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string; details?: string[] };
      if (!res.ok) {
        const detailsStr = Array.isArray(data?.details) ? data.details.join("; ") : "";
        setSyncResult({
          success: false,
          message: detailsStr || (typeof data?.error === "string" ? data.error : COPY.EXPORT.PUSH_ERROR),
        });
        return;
      }
      setSyncResult({ success: true, message: (data as { message?: string }).message ?? COPY.EXPORT.PUSH_SUCCESS });
    } catch (e) {
      setSyncResult({
        success: false,
        message: e instanceof Error ? e.message : COPY.EXPORT.PUSH_ERROR,
      });
    } finally {
      setSyncPushing(false);
    }
  }

  async function handleGenerateSimilar() {
    if (selectedIndex == null || selectedIndex < 0 || selectedIndex >= variants.length || !variants[selectedIndex]) return;
    console.log("[Landright Generate] handleGenerateSimilar", { selectedIndex, experienceLibraryLength: experienceLibrary.length });
    setRegenerating(true);
    setState("loading");
    try {
      await fetchVariants({
        chosenVariantTsx: variants[selectedIndex],
        selectedVariantIndex: selectedIndex,
        experienceLibrary,
        variantTsxList: variants.slice(0, 4),
        similarityRound,
      });
    } finally {
      setRegenerating(false);
    }
  }

  function handleUseCurrentVariantsForAgent() {
    const four = variants.slice(0, 4);
    if (four.length !== 4) return;
    setAgentUploadedVariants(four);
    setAgentResult(null);
  }

  async function handleAgentFileChange(e: React.ChangeEvent<HTMLInputElement>, index: number) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setAgentUploadedVariants((prev) => {
        const next = prev ? [...prev] : ["", "", "", ""];
        next[index] = text;
        return next;
      });
      setAgentResult(null);
    } catch {
      setAgentResult({ success: false, message: COPY.GENERATE.AGENT_ERROR });
    }
  }

  async function handlePushAllFourToGitHub() {
    const four = variants.slice(0, 4);
    if (four.length !== 4 || four.some((v) => !v?.trim())) {
      setSyncVariantsResult({ success: false, message: "Need exactly 4 variants to push." });
      return;
    }
    const repo = syncVariantsRepoFullName.trim();
    if (!repo) {
      setSyncVariantsResult({
        success: false,
        message: "Enter GitHub repo (owner/repo) or set GITHUB_REPO_FULL_NAME in the sync agent .env.",
      });
      return;
    }
    if (!PYTHON_BACKEND_URL) {
      setSyncVariantsResult({ success: false, message: MISSING_BACKEND_MSG });
      return;
    }
    setSyncVariantsPushing(true);
    setSyncVariantsResult(null);
    try {
      const bundleRes = await fetch(`${PYTHON_BACKEND_URL}/build-export-bundle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variant_tsx_list: four,
          repo_full_name: repo,
          layer: syncVariantsLayerName.trim() || "1",
        }),
      });
      const bundleData = (await bundleRes.json().catch(() => ({}))) as { files?: Record<string, string>; detail?: string };
      if (!bundleRes.ok) {
        const msg = typeof bundleData.detail === "string" ? bundleData.detail : bundleRes.statusText;
        setSyncVariantsResult({ success: false, message: msg || "Failed to build export bundle." });
        return;
      }
      const files = bundleData.files;
      if (!files || Object.keys(files).length === 0) {
        setSyncVariantsResult({ success: false, message: "Backend returned no bundle files." });
        return;
      }
      const res = await fetch("/api/sync-bundle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          files,
          repoFullName: repo,
          commitMessage: syncVariantsCommitMessage.trim() || "Deploy 4 variants from Landright",
          layerName: syncVariantsLayerName.trim() || "layer-1",
          skipBuildCheck: true,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string; details?: string[]; message?: string };
      if (!res.ok) {
        const detailsStr = Array.isArray(data?.details) ? data.details.join("; ") : "";
        const msg =
          res.status === 503 && typeof data?.error === "string" && data.error.toLowerCase().includes("sync_agent")
            ? COPY.GENERATE.PUSH_ALL_AGENT_NOT_CONFIGURED
            : detailsStr || (typeof data?.error === "string" ? data.error : COPY.GENERATE.PUSH_ALL_ERROR);
        setSyncVariantsResult({ success: false, message: msg });
        return;
      }
      setSyncVariantsResult({ success: true, message: data.message ?? COPY.GENERATE.PUSH_ALL_SUCCESS });
    } catch (e) {
      setSyncVariantsResult({
        success: false,
        message: e instanceof Error ? e.message : COPY.GENERATE.PUSH_ALL_ERROR,
      });
    } finally {
      setSyncVariantsPushing(false);
    }
  }

  async function handleSendToAgent() {
    const toSend = agentUploadedVariants ?? variants.slice(0, 4);
    if (toSend.length !== 4 || !toSend.every(Boolean)) {
      setAgentResult({ success: false, message: "Need exactly 4 variants (use current or upload 4 files)." });
      return;
    }
    if (!AGENT_URL) {
      setAgentResult({ success: false, message: "NEXT_PUBLIC_AGENT_URL is not set." });
      return;
    }
    setAgentSending(true);
    setAgentResult(null);
    try {
      const res = await fetch(`${AGENT_URL}/test-variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ variants: toSend }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || `Agent returned ${res.status}`);
      }
      setAgentResult({ success: true, message: COPY.GENERATE.AGENT_SUCCESS });
    } catch (e) {
      setAgentResult({
        success: false,
        message: e instanceof Error ? e.message : COPY.GENERATE.AGENT_ERROR,
      });
    } finally {
      setAgentSending(false);
    }
  }

  if (!spec) return null;

  if (done) {
    if (showExport && chosenFinalHtml) {
      const exportIsTsx = isTsxVariant(chosenFinalHtml);
      const instructions = exportIsTsx ? IMPLEMENTATION_INSTRUCTIONS_TSX : IMPLEMENTATION_INSTRUCTIONS_HTML;
      return (
        <div className="min-h-screen bg-black text-white">
          <div className="mx-auto max-w-2xl px-6 py-12">
            <p className="mb-4">
              <Link href="/dashboard" className="text-sm font-medium text-white/70 hover:text-orange-400">
                {COPY.DASHBOARD.HOME_LINK}
              </Link>
            </p>
            <h1 className="text-2xl font-semibold text-white">{COPY.EXPORT.TITLE}</h1>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                onClick={handleCopyHtml}
                className="rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-400"
              >
                {copyFeedback ? COPY.EXPORT.COPIED : exportIsTsx ? COPY.EXPORT.COPY_TSX : COPY.EXPORT.COPY_HTML}
              </button>
              <button
                onClick={handleDownload}
                className="rounded-lg border border-orange-500/50 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500/20"
              >
                {exportIsTsx ? COPY.EXPORT.DOWNLOAD_TSX : COPY.EXPORT.DOWNLOAD_HTML}
              </button>
              <button
                onClick={handlePushToGitHub}
                disabled={syncPushing || variants.length < 4}
                className="rounded-lg border border-orange-500/50 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500/20 disabled:opacity-50"
              >
                {syncPushing ? COPY.EXPORT.PUSH_SENDING : COPY.EXPORT.PUSH_TO_GITHUB}
              </button>
            </div>
            <div className="mt-6 rounded-lg border border-orange-500/20 bg-black/60 p-4 space-y-3">
              <p className="text-xs text-white/60">GitHub repo (owner/name). Required to push full app bundle.</p>
              <input
                type="text"
                value={syncRepoFullName}
                onChange={(e) => setSyncRepoFullName(e.target.value)}
                className="w-full rounded-md border border-orange-500/30 bg-black/80 px-3 py-2 text-sm text-white placeholder-white/40"
                placeholder="owner/repo"
              />
              <p className="text-xs text-white/60">{COPY.EXPORT.COMMIT_MESSAGE_LABEL}</p>
              <input
                type="text"
                value={syncCommitMessage}
                onChange={(e) => setSyncCommitMessage(e.target.value)}
                className="w-full rounded-md border border-orange-500/30 bg-black/80 px-3 py-2 text-sm text-white placeholder-white/40"
                placeholder="Update landing page from Landright"
              />
              {syncResult && (
                <p className={`text-sm ${syncResult.success ? "text-emerald-400" : "text-red-400"}`}>
                  {syncResult.message}
                </p>
              )}
            </div>
            <section className="mt-10">
              <h2 className="text-sm font-medium text-white/90">{COPY.EXPORT.INSTRUCTIONS_TITLE}</h2>
              <ul className="mt-3 list-inside list-decimal space-y-2 text-sm text-white/70">
                {instructions.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ul>
            </section>
            <button
              onClick={() => setShowExport(false)}
              className="mt-10 text-sm text-white/60 hover:text-orange-400"
            >
              {COPY.EXPORT.BACK}
            </button>
          </div>
        </div>
      );
    }
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-4">
          <h1 className="text-2xl font-semibold text-white">{COPY.GENERATE.DONE_TITLE}</h1>
          <p className="mt-2 text-white/70">{COPY.GENERATE.DONE_SUBTITLE}</p>
          {chosenFinalHtml && (
            <button
              onClick={() => setShowExport(true)}
              className="mt-6 block w-full max-w-xs mx-auto rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-400"
            >
              {COPY.EXPORT.BUTTON}
            </button>
          )}
          {variants.length >= 4 && (
            <div className="mt-6 rounded-lg border border-orange-500/20 bg-black/60 p-4 text-left">
              <h2 className="text-sm font-medium text-white/90">Export to GitHub (OAuth)</h2>
              <p className="mt-1 text-xs text-white/60">Create a new repo under your account and push a Vercel-ready bundle.</p>
              <input
                type="text"
                value={exportToGitHubRepoName}
                onChange={(e) => setExportToGitHubRepoName(e.target.value)}
                placeholder="landright-my-company"
                className="mt-3 w-full rounded-md border border-orange-500/30 bg-black/80 px-3 py-2 text-sm text-white placeholder-white/40"
              />
              <input
                type="text"
                value={exportToGitHubLayer}
                onChange={(e) => setExportToGitHubLayer(e.target.value)}
                placeholder="Layer (e.g. 1)"
                className="mt-2 w-full rounded-md border border-orange-500/30 bg-black/80 px-3 py-2 text-sm text-white placeholder-white/40"
              />
              <button
                onClick={() => {
                  const repoName = (exportToGitHubRepoName || "").trim() || "landright-landing";
                  const layer = (exportToGitHubLayer || "").trim() || "1";
                  if (typeof window === "undefined" || !GITHUB_CLIENT_ID) return;
                  try {
                    sessionStorage.setItem(STORAGE_KEYS.EXPORT_PENDING, JSON.stringify({ repoName, layer }));
                    const origin = window.location.origin;
                    const redirectUri = `${origin}/export-github/callback`;
                    const state = crypto.randomUUID?.() ?? Math.random().toString(36).slice(2);
                    sessionStorage.setItem("github_oauth_state", state);
                    const url = `https://github.com/login/oauth/authorize?client_id=${encodeURIComponent(GITHUB_CLIENT_ID)}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=public_repo&state=${encodeURIComponent(state)}`;
                    window.location.href = url;
                  } catch (e) {
                    console.error("[Landright] Export to GitHub redirect failed", e);
                  }
                }}
                className="mt-3 w-full rounded-lg border border-orange-500/50 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500/20"
              >
                Continue to GitHub
              </button>
              {GITHUB_APP_INSTALL_URL && (
                <a
                  href={GITHUB_APP_INSTALL_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 w-full inline-block text-center rounded-lg border border-orange-500/30 px-4 py-2 text-sm text-white/90 hover:bg-orange-500/10"
                >
                  Install Landright GitHub App (for CTA optimization)
                </a>
              )}
            </div>
          )}
          <button
            onClick={() => {
              setShowAgentPanel(true);
              setAgentResult(null);
              setAgentUploadedVariants(null);
            }}
            className="mt-4 block w-full max-w-xs mx-auto rounded-lg border border-orange-500/50 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500/20"
          >
            {COPY.GENERATE.SEND_TO_AGENT}
          </button>
          {showAgentPanel && (
            <div className="mt-6 p-4 rounded-xl border border-orange-500/30 bg-black/80 text-left">
              <h2 className="text-sm font-medium text-white mb-3">{COPY.GENERATE.AGENT_PANEL_TITLE}</h2>
              <button
                onClick={handleUseCurrentVariantsForAgent}
                className="rounded-lg bg-orange-500/20 border border-orange-500/50 px-3 py-2 text-sm text-white hover:bg-orange-500/30 w-full mb-3"
              >
                {COPY.GENERATE.AGENT_USE_CURRENT}
              </button>
              <p className="text-xs text-white/60 mb-2">{COPY.GENERATE.AGENT_UPLOAD_FILES}</p>
              <div className="grid grid-cols-4 gap-2 mb-3">
                {[0, 1, 2, 3].map((i) => (
                  <label key={i} className="flex flex-col gap-1">
                    <span className="text-xs text-white/50">Variant {i + 1}</span>
                    <input
                      type="file"
                      accept=".tsx,.html,.txt,text/plain"
                      className="text-xs text-white/70 file:mr-2 file:rounded file:border-0 file:bg-orange-500/30 file:px-2 file:py-1 file:text-white"
                      onChange={(e) => handleAgentFileChange(e, i)}
                    />
                  </label>
                ))}
              </div>
              {agentResult && (
                <p className={`text-sm mb-3 ${agentResult.success ? "text-emerald-400" : "text-red-400"}`}>
                  {agentResult.message}
                </p>
              )}
              <button
                onClick={handleSendToAgent}
                disabled={agentSending}
                className="rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-400 disabled:opacity-50"
              >
                {agentSending ? COPY.GENERATE.AGENT_SENDING : COPY.GENERATE.AGENT_SEND}
              </button>
            </div>
          )}
          <button
            onClick={() => {
              setDone(false);
              setChosenFinalHtml(null);
              setShowExport(false);
              setShowAgentPanel(false);
              setVariants([]);
              setState("loading");
              setSelectedIndex(null);
              initialFetchDone.current = false;
            }}
            className="mt-4 rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-400"
          >
            {COPY.GENERATE.GENERATE_AGAIN}
          </button>
          <button
            onClick={() => {
              setChosenFinalHtml(null);
              setShowExport(false);
              setShowAgentPanel(false);
              router.push("/");
            }}
            className="ml-3 mt-4 rounded-lg border border-orange-500/50 px-4 py-2 text-sm text-white hover:bg-orange-500/20"
          >
            {COPY.GENERATE.NEW_SESSION}
          </button>
          <p className="mt-4">
            <Link href="/dashboard" className="text-sm font-medium text-white/70 hover:text-orange-400">
              {COPY.DASHBOARD.HOME_LINK}
            </Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-black text-white">
      <div className="sticky top-0 z-10 border-b border-orange-500/30 bg-black/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <span className="text-sm font-medium text-white">
            {COPY.GENERATE.BRAND}
            {refinementRound > 1 && (
              <span className="ml-2 text-white/60">({COPY.GENERATE.ROUND(refinementRound)})</span>
            )}
          </span>
          <nav className="flex items-center gap-4">
            <Link
              href="/dashboard"
              className="text-sm font-medium text-white/70 hover:text-orange-400 transition-colors"
            >
              {COPY.DASHBOARD.HOME_LINK}
            </Link>
            <button
              onClick={() => router.push("/")}
              className="text-sm text-white/70 hover:text-orange-400 transition-colors"
            >
              {COPY.GENERATE.NEW_SESSION}
            </button>
          </nav>
        </div>
      </div>

      {error && (
        <div className="mx-auto max-w-6xl px-4 py-3">
          <div className="rounded-lg bg-red-950/50 border border-red-500/50 px-4 py-2 text-sm text-red-200">
            {error}
          </div>
        </div>
      )}

      {state === "loading" && (
        <div className="flex-1 flex flex-col h-[calc(100vh-3.5rem)] min-h-0 p-2">
          <div className="generating-glow flex-1 min-h-0 rounded-xl flex flex-col items-center justify-center gap-2 bg-black/50">
            <p className="text-white font-medium transition-opacity duration-300">
              {COPY.GENERATE.LOADING_STEPS[loadingStepIndex % COPY.GENERATE.LOADING_STEPS.length]}
            </p>
            <p className="text-sm text-white/70">{COPY.GENERATE.ESTIMATED_TIME}</p>
          </div>
        </div>
      )}

      {state === "show" && variants.length === 0 && (
        <div className="mx-auto max-w-xl px-4 py-12 text-center">
          <p className="text-white/80 whitespace-pre-wrap">
            {error?.toLowerCase().includes("valid json")
              ? COPY.GENERATE.ERROR_JSON
              : error && /401|unauthorized|invalid key|authentication|forbidden/i.test(error)
                ? "See the error above. Fix any API key or network issue, then retry."
                : error || COPY.GENERATE.ERROR_RETRY}
          </p>
          <button
            onClick={() => {
              setError(null);
              initialFetchDone.current = false;
              setState("loading");
              fetchVariants();
            }}
            className="mt-4 rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-400"
          >
            {COPY.GENERATE.RETRY}
          </button>
        </div>
      )}

      {state === "show" && variants.length >= 1 && (
        <div className="flex flex-col flex-1 min-h-0 h-[calc(100vh-3.5rem)]">
          {/* Top bar: pick instruction left, switcher + Pick button top right */}
          <div className="flex-none border-b border-orange-500/30 bg-black/95 px-4 py-2 flex items-center justify-between gap-4 flex-wrap">
            <p className="text-sm text-white/80">{COPY.GENERATE.PICK_ONE}</p>
            <div className="flex items-center gap-3">
              <span className="text-xs text-white/60 tabular-nums">Variant</span>
              <div className="flex rounded-lg border border-orange-500/40 bg-black/80 p-0.5" role="tablist" aria-label="Switch variant">
                {Array.from({ length: variants.length }, (_, i) => i).map((i) => (
                  <button
                    key={i}
                    type="button"
                    role="tab"
                    aria-selected={viewingIndex === i}
                    aria-label={COPY.GENERATE.VARIANT(i + 1)}
                    onClick={() => setViewingIndex(i)}
                    className={`min-w-[2.5rem] rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                      viewingIndex === i
                        ? "bg-orange-500 text-white"
                        : "text-white/70 hover:text-white hover:bg-orange-500/30"
                    }`}
                  >
                    {i + 1}
                  </button>
                ))}
              </div>
              <button
                onClick={() => handlePick(viewingIndex)}
                className="rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-400 transition-colors whitespace-nowrap"
              >
                {COPY.GENERATE.PICK_THIS}
              </button>
            </div>
          </div>
          {/* Validation: runnable, mobile-friendly, browser-safe */}
          {validation && (
            <div className="flex-none flex flex-wrap items-center gap-3 px-4 py-2 border-b border-orange-500/20 bg-black/90 text-xs">
              <span
                className={validation.runnable ? "text-emerald-400" : "text-amber-400"}
                title={validation.runnable ? "Compiles and runs" : validation.errors?.join(" ") ?? "Does not compile"}
              >
                {validation.runnable ? "\u2713 Runnable" : "\u2717 Not runnable"}
              </span>
              <span
                className={validation.mobileFriendly ? "text-emerald-400" : "text-white/50"}
                title={validation.mobileFriendly ? "Uses responsive classes" : "No sm:/md:/lg: classes detected"}
              >
                {validation.mobileFriendly ? "\u2713 Mobile-friendly" : "\u25CB Mobile unknown"}
              </span>
              <span
                className={validation.browserSafe ? "text-emerald-400" : "text-amber-400"}
                title={validation.browserSafe ? "Browser-only APIs" : "Uses Node/server APIs"}
              >
                {validation.browserSafe ? "\u2713 Browser-safe" : "\u2717 Not browser-safe"}
              </span>
              {validation.sameButtons !== undefined && (
                <span
                  className={validation.sameButtons ? "text-emerald-400" : "text-amber-400"}
                  title={validation.sameButtons ? "CTA URLs match spec" : "CTA links do not match spec"}
                >
                  {validation.sameButtons ? "\u2713 Same buttons" : "\u2717 Same buttons"}
                </span>
              )}
              {validation.errors.length > 0 && (
                <span className="text-white/60 max-w-md truncate" title={validation.errors.join(" ")}>
                  {validation.errors[0]}
                </span>
              )}
            </div>
          )}
          {/* Critic reasoning + conversion drivers for current variant */}
          {(variantReasoning[viewingIndex] || (conversionDrivers[viewingIndex] && conversionDrivers[viewingIndex].length > 0)) && (
            <div className="flex-none px-4 py-2 border-b border-orange-500/10 bg-gradient-to-r from-orange-950/30 to-black/80 text-xs text-orange-200/80">
              {variantReasoning[viewingIndex] && (
                <div className="flex items-start gap-2">
                  <span className="text-orange-400 mt-0.5 shrink-0">&#9733;</span>
                  <span>{variantReasoning[viewingIndex]}</span>
                </div>
              )}
              {conversionDrivers[viewingIndex] && conversionDrivers[viewingIndex].length > 0 && (
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  {conversionDrivers[viewingIndex].map((d, i) => (
                    <span key={i} className="inline-flex items-center gap-1 bg-orange-500/15 border border-orange-500/20 rounded-full px-2 py-0.5 text-[10px] text-orange-300">
                      {d}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          {/* All previews rendered; only the active one visible (instant tab switch, no remount). */}
          <div className="flex-1 min-h-0 overflow-hidden bg-black relative">
            {Array.from({ length: variants.length }, (_, i) => i).map((i) => (
              <div
                key={i}
                className="absolute inset-0 h-full w-full"
                style={{ display: viewingIndex === i ? "block" : "none" }}
                aria-hidden={viewingIndex !== i}
              >
                <TsxPreview tsx={variants[i] ?? ""} className="h-full w-full" />
              </div>
            ))}
          </div>
        </div>
      )}

      {state === "picked" && selectedIndex != null && variants[selectedIndex] && (
        <div className={`mx-auto max-w-2xl px-4 py-8 ${regenerating ? "generating-glow rounded-xl p-6" : ""}`}>
          {regenerating && (
            <p className="text-orange-400 text-sm font-medium mb-4">Generating 4 similar variants\u2026</p>
          )}
          <p className="text-sm text-white/80">{COPY.GENERATE.YOU_PICKED(selectedIndex + 1)}</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              onClick={handleSatisfied}
              className="rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-400"
            >
              {COPY.GENERATE.SATISFIED}
            </button>
            <button
              onClick={handleGenerateSimilar}
              disabled={regenerating}
              className="rounded-lg border border-orange-500/50 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500/20 disabled:opacity-50"
            >
              {COPY.GENERATE.GENERATE_FOUR_SIMILAR}
            </button>
            <button
              onClick={() => setState("show")}
              className="rounded-lg border border-orange-500/50 px-4 py-2 text-sm text-white hover:bg-orange-500/20"
            >
              {COPY.GENERATE.BACK_TO_VARIANTS}
            </button>
          </div>
          {/* Deploy to Agent: one clean POST with TSX + reasoning */}
          <div className="mt-6 rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-4 space-y-3">
            <p className="text-sm font-medium text-emerald-200">Deploy selected variant</p>
            <p className="text-xs text-emerald-300/60">One-click deploy: sends the selected TSX and reasoning to the agent.</p>
            {variantReasoning[selectedIndex ?? 0] && (
              <p className="text-xs text-zinc-400 italic">&quot;{variantReasoning[selectedIndex ?? 0]}&quot;</p>
            )}
            {conversionDrivers[selectedIndex ?? 0] && conversionDrivers[selectedIndex ?? 0].length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {conversionDrivers[selectedIndex ?? 0].map((d, i) => (
                  <span key={i} className="text-[10px] bg-emerald-500/15 border border-emerald-500/20 rounded-full px-2 py-0.5 text-emerald-300">{d}</span>
                ))}
              </div>
            )}
            <button
              onClick={handleDeployToAgent}
              disabled={deployPushing}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50 transition"
            >
              {deployPushing ? "Deploying…" : "Deploy to Agent"}
            </button>
            {deployResult && (
              <p className={`text-xs ${deployResult.success ? "text-emerald-400" : "text-red-400"}`}>{deployResult.message}</p>
            )}
          </div>
          {/* Push all 4 variants to GitHub via landrightgithubagent */}
          <div className="mt-8 rounded-lg border border-orange-500/20 bg-black/60 p-4 space-y-3">
            <p className="text-sm font-medium text-white/90">{COPY.GENERATE.PUSH_ALL_FOUR_TO_GITHUB}</p>
            <p className="text-xs text-white/60">GitHub repo (owner/name, e.g. myorg/my-repo). Required unless set in agent .env as GITHUB_REPO_FULL_NAME.</p>
            <input
              type="text"
              value={syncVariantsRepoFullName}
              onChange={(e) => setSyncVariantsRepoFullName(e.target.value)}
              className="w-full rounded-md border border-orange-500/30 bg-black/80 px-3 py-2 text-sm text-white placeholder-white/40"
              placeholder="owner/repo"
            />
            <p className="text-xs text-white/60">{COPY.GENERATE.LAYER_NAME_LABEL}</p>
            <input
              type="text"
              value={syncVariantsLayerName}
              onChange={(e) => setSyncVariantsLayerName(e.target.value)}
              className="w-full rounded-md border border-orange-500/30 bg-black/80 px-3 py-2 text-sm text-white placeholder-white/40"
              placeholder={COPY.GENERATE.LAYER_NAME_PLACEHOLDER}
            />
            <p className="text-xs text-white/60">{COPY.EXPORT.COMMIT_MESSAGE_LABEL}</p>
            <input
              type="text"
              value={syncVariantsCommitMessage}
              onChange={(e) => setSyncVariantsCommitMessage(e.target.value)}
              className="w-full rounded-md border border-orange-500/30 bg-black/80 px-3 py-2 text-sm text-white placeholder-white/40"
              placeholder="Deploy 4 variants from Landright"
            />
            {syncVariantsResult && (
              <p className={`text-sm ${syncVariantsResult.success ? "text-emerald-400" : "text-red-400"}`}>
                {syncVariantsResult.message}
              </p>
            )}
            <button
              onClick={handlePushAllFourToGitHub}
              disabled={syncVariantsPushing || variants.length < 4}
              className="rounded-lg border border-orange-500/50 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500/20 disabled:opacity-50"
            >
              {syncVariantsPushing ? COPY.GENERATE.PUSH_ALL_SENDING : COPY.GENERATE.PUSH_ALL_FOUR_TO_GITHUB}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
