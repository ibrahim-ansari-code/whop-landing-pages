/** Centralized route paths, error codes, and app constants. */

export const ROUTES = {
  HEALTH: "/health",
  API_HEALTH: "/api/health",
  SYNC: "/sync",
  TRACK: "/track",
  REACTIVE_FIX: "/api/reactive-fix",
  BOT_REACTIVE_FIX: "/api/bot/reactive-fix",
  /** Full path for track; when mounted at /api, use TRACK_PATH. */
  API_TRACK: "/api/track",
  TRACK_PATH: "/track",
} as const;

export const ERROR_CODES = {
  UNAUTHORIZED: "UNAUTHORIZED",
  VALIDATION_ERROR: "VALIDATION_ERROR",
  RATE_LIMITED: "RATE_LIMITED",
  FILE_NOT_FOUND: "FILE_NOT_FOUND",
  INTERNAL_ERROR: "INTERNAL_ERROR",
} as const;

export const BODY_LIMIT = "1mb";

export const MESSAGES = {
  PEM_MISSING:
    "Missing PEM file. Add landright-agent.pem to project root or set PRIVATE_KEY_PATH.",
  JSON_BODY_REQUIRED: "JSON body required (Content-Type: application/json)",
} as const;
