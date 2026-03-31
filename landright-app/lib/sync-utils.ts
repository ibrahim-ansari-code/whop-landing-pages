/** Shared utilities for sync agent API routes. */

export const DEFAULT_LAYER_NAME = "layer-1";
export const DEFAULT_COMMIT_MESSAGE_BUNDLE = "Deploy 4 variants from Landright";
export const DEFAULT_COMMIT_MESSAGE_SINGLE = "Update landing page from Landright";

export function buildSyncHeaders(): Record<string, string> {
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
