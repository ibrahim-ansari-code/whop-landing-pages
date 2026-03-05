import { Request, Response } from "express";
import { ERROR_CODES } from "../config/constants.js";
import type { Logger } from "pino";

function getApiKeyFromRequest(req: Request): string | undefined {
  const header =
    req.headers["x-api-key"] ?? req.headers.authorization?.replace(/^Bearer\s+/i, "");
  return typeof header === "string" ? header : undefined;
}

export interface ApiKeyMiddlewareOptions {
  apiKey: string | undefined;
  logContext: string;
  log: Logger;
}

/**
 * Returns a middleware that enforces API key auth when apiKey is set.
 * When apiKey is empty/undefined, passes through (no auth required).
 */
export function createApiKeyMiddleware(options: ApiKeyMiddlewareOptions) {
  const { apiKey, logContext, log } = options;
  return (req: Request, res: Response, next: () => void): void => {
    if (!apiKey) {
      next();
      return;
    }
    const key = getApiKeyFromRequest(req);
    if (!key || key !== apiKey) {
      log.warn({ path: req.path }, `${logContext}: missing or invalid API key`);
      res.status(401).json({ error: ERROR_CODES.UNAUTHORIZED });
      return;
    }
    next();
  };
}
