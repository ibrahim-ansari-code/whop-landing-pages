import { Router, Request, Response } from "express";
import { ROUTES } from "../config/constants.js";
import { runReactiveFix } from "../services/simulation.service.js";
import type { Logger } from "pino";

async function handleReactiveFix(
  _req: Request,
  res: Response,
  log: Logger
): Promise<void> {
  try {
    const result = await runReactiveFix();
    if (result.applied) {
      res.status(200).json({
        ok: true,
        applied: true,
        filePath: result.filePath,
        sha: result.sha,
      });
    } else {
      res.status(200).json({ ok: true, applied: false });
    }
  } catch (err) {
    log.error({ err }, "Reactive fix failed");
    res.status(500).json({
      ok: false,
      error: err instanceof Error ? err.message : "Reactive fix failed",
    });
  }
}

export function createReactiveFixRouter(log: Logger): Router {
  const router = Router();
  const handler = (req: Request, res: Response) => void handleReactiveFix(req, res, log);
  router.post(ROUTES.REACTIVE_FIX, handler);
  router.post(ROUTES.BOT_REACTIVE_FIX, handler);
  return router;
}
