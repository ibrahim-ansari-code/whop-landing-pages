import { Router, Request, Response } from "express";
import { z } from "zod";
import { env } from "../config/env.js";
import { ERROR_CODES, MESSAGES, ROUTES } from "../config/constants.js";
import { createApiKeyMiddleware } from "../middleware/auth.middleware.js";
import { updateRecord } from "../services/github.service.js";
import type { Logger } from "pino";

const bodySchema = z.object({
  filePath: z.string().min(1),
  data: z.string(),
  commitMessage: z.string().min(1),
});

export function createUpdateRouter(log: Logger): Router {
  const router = Router();
  const syncAuth = createApiKeyMiddleware({
    apiKey: env.API_KEY || undefined,
    logContext: "Sync",
    log,
  });

  router.post(ROUTES.SYNC, syncAuth, async (req: Request, res: Response) => {
    const body = req.body;
    if (body === undefined || body === null || typeof body !== "object") {
      res.status(400).json({
        error: ERROR_CODES.VALIDATION_ERROR,
        details: { formErrors: [MESSAGES.JSON_BODY_REQUIRED], fieldErrors: {} },
      });
      return;
    }
    const parsed = bodySchema.safeParse(body);
    if (!parsed.success) {
      res.status(400).json({ error: ERROR_CODES.VALIDATION_ERROR, details: parsed.error.flatten() });
      return;
    }
    const { filePath, data, commitMessage } = parsed.data;

    try {
      const { sha } = await updateRecord(env, filePath, data, commitMessage);
      res.status(200).json({ sha, filePath });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      const status =
        (err as { status?: number })?.status ??
        (err as { response?: { status?: number } })?.response?.status;
      if (status === 403 || message.includes("403")) {
        log.warn({ filePath }, "GitHub rate limit");
        res.status(429).json({ error: ERROR_CODES.RATE_LIMITED });
        return;
      }
      if (status === 404 || message.includes("404")) {
        res.status(404).json({ error: ERROR_CODES.FILE_NOT_FOUND, detail: message });
        return;
      }
      if (message.includes("ENOENT") || message.includes("no such file")) {
        log.error({ err, filePath }, "PEM file missing (PRIVATE_KEY_PATH)");
        res.status(500).json({
          error: ERROR_CODES.INTERNAL_ERROR,
          detail: MESSAGES.PEM_MISSING,
        });
        return;
      }
      log.error({ err, filePath }, "Sync failed");
      res.status(500).json({ error: ERROR_CODES.INTERNAL_ERROR, detail: message });
    }
  });

  return router;
}
