/** Client-safe config: app name, storage keys, and limits. Use env for overrides where needed. */
export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Landright";

/** Base URL for the Python generate API. Required; no Next.js proxy. Set NEXT_PUBLIC_GENERATE_API_URL (e.g. http://localhost:8000). */
export const GENERATE_API_BASE =
  typeof process.env.NEXT_PUBLIC_GENERATE_API_URL === "string" && process.env.NEXT_PUBLIC_GENERATE_API_URL.trim() !== ""
    ? process.env.NEXT_PUBLIC_GENERATE_API_URL.trim().replace(/\/$/, "")
    : "";

/** Prompt id sent to backend (must exist in backend prompts.json or backend default). */
export const DEFAULT_PROMPT_ID = process.env.NEXT_PUBLIC_DEFAULT_PROMPT_ID?.trim() || "default";

/** Agent URL for sending 4 variants for testing. Set NEXT_PUBLIC_AGENT_URL (e.g. http://localhost:8080). */
export const AGENT_URL =
  typeof process.env.NEXT_PUBLIC_AGENT_URL === "string" && process.env.NEXT_PUBLIC_AGENT_URL.trim() !== ""
    ? process.env.NEXT_PUBLIC_AGENT_URL.trim().replace(/\/$/, "")
    : "";

/**
 * Sync agent (landrightgithubagent) is used server-side only via app/api/sync-repo.
 * Set SYNC_AGENT_URL (e.g. http://localhost:4000) and optionally SYNC_AGENT_API_KEY.
 * Not in client config so the key is never exposed.
 */

export const STORAGE_KEYS = {
  SPEC: process.env.NEXT_PUBLIC_STORAGE_KEY_SPEC ?? "landright-spec",
  PROMPT_ID: process.env.NEXT_PUBLIC_STORAGE_KEY_PROMPT_ID ?? "landright-prompt-id",
  VARIANTS: process.env.NEXT_PUBLIC_STORAGE_KEY_VARIANTS ?? "landright-variants",
  EXPORT_PENDING: process.env.NEXT_PUBLIC_STORAGE_KEY_EXPORT_PENDING ?? "landright-export-pending",
} as const;

export const GITHUB_CLIENT_ID =
  typeof process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID === "string" && process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID.trim() !== ""
    ? process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID.trim()
    : "";

/**
 * Public URL where users can install the Landright GitHub App (for CTA optimization).
 * Set NEXT_PUBLIC_GITHUB_APP_INSTALL_URL (e.g. https://github.com/apps/landright/installations/new).
 * When set, the app shows an "Install Landright GitHub App" button after export and in the export block.
 */
export const GITHUB_APP_INSTALL_URL =
  typeof process.env.NEXT_PUBLIC_GITHUB_APP_INSTALL_URL === "string" && process.env.NEXT_PUBLIC_GITHUB_APP_INSTALL_URL.trim() !== ""
    ? process.env.NEXT_PUBLIC_GITHUB_APP_INSTALL_URL.trim()
    : "";

/** Validation limits (shared with API where possible). */
export const LIMITS = {
  BUSINESS_INFO_MIN_LENGTH: 10,
  BUSINESS_INFO_MAX_LENGTH: 2000,
  SKILLS_MAX_LENGTH: 500,
  GOALS_MAX_LENGTH: 500,
  CHANGE_REQUEST_MAX_LENGTH: 1000,
  CHOSEN_HTML_MAX_LENGTH: 500_000,
  REFERENCE_SITES_MAX_LENGTH: 1500,
  CUSTOM_FONT_MAX_LENGTH: 100,
  CUSTOM_COLOR_MAX_LENGTH: 20,
} as const;
