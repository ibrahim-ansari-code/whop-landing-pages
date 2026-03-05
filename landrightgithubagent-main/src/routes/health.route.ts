import { Router, Request, Response } from "express";
import { ROUTES } from "../config/constants.js";

function healthHandler(_req: Request, res: Response): void {
  res.json({ status: "ok" });
}

export function createHealthRouter(): Router {
  const router = Router();
  router.get(ROUTES.HEALTH, healthHandler);
  router.get(ROUTES.API_HEALTH, healthHandler);
  return router;
}
