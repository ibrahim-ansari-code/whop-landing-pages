"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { STORAGE_KEYS } from "@/lib/config";

/** Redirect: /prompts with spec → /generate; otherwise → /. Prompts step removed from flow. */
export default function PromptsPage() {
  const router = useRouter();
  useEffect(() => {
    const spec = typeof window !== "undefined" ? sessionStorage.getItem(STORAGE_KEYS.SPEC) : null;
    router.replace(spec ? "/generate" : "/");
  }, [router]);
  return null;
}
