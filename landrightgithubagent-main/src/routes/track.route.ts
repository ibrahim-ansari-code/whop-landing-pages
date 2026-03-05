import { Router, Request, Response } from "express";
import { z } from "zod";
import { env } from "../config/env.js";
import { ERROR_CODES, ROUTES } from "../config/constants.js";
import { createApiKeyMiddleware } from "../middleware/auth.middleware.js";
import { appendEvent, type TrackEvent } from "../services/report.service.js";
import type { Logger } from "pino";

const trackBodySchema = z.object({
  generation_id: z.string().min(1),
  variant_id: z.string().min(1),
  event_type: z.enum(["view", "click", "conversion"]),
  url: z.string().optional(),
  timestamp: z.string().optional(),
});

export function createTrackRouter(log: Logger): Router {
  const router = Router();
  const trackAuth = createApiKeyMiddleware({
    apiKey: env.TRACK_API_KEY ?? undefined,
    logContext: "Track endpoint",
    log,
  });

  router.post(ROUTES.TRACK_PATH, trackAuth, (req: Request, res: Response) => {
    const parsed = trackBodySchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: ERROR_CODES.VALIDATION_ERROR, details: parsed.error.flatten() });
      return;
    }
    const event: TrackEvent = {
      generation_id: parsed.data.generation_id,
      variant_id: parsed.data.variant_id,
      event_type: parsed.data.event_type,
      url: parsed.data.url,
      timestamp: parsed.data.timestamp,
    };
    appendEvent(env, event);
    res.status(200).json({ ok: true });
  });

  return router;
}
