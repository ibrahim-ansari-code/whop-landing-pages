import "dotenv/config";
import express from "express";
import pino from "pino";
import pinoHttp from "pino-http";
import { env } from "./config/env.js";
import { BODY_LIMIT, ERROR_CODES } from "./config/constants.js";
import { createUpdateRouter } from "./routes/update.route.js";
import { createTrackRouter } from "./routes/track.route.js";
import { createHealthRouter } from "./routes/health.route.js";
import { createReactiveFixRouter } from "./routes/reactive-fix.route.js";
import { startScheduler } from "./jobs/scheduler.js";

const log = pino({ level: process.env.LOG_LEVEL ?? "info" });
const httpLog = pinoHttp({ logger: log });

const app = express();
app.use(express.json({ limit: BODY_LIMIT }));
app.use(httpLog);

app.use("/", createUpdateRouter(log));
app.use("/", createHealthRouter());
app.use("/api", createTrackRouter(log));
app.use("/", createReactiveFixRouter(log));

app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  log.error({ err }, "Unhandled error");
  res.status(500).json({ error: ERROR_CODES.INTERNAL_ERROR });
});

startScheduler(log);

app.listen(env.PORT, env.HOST, () => {
  log.info({ port: env.PORT, host: env.HOST }, "Landright Agent listening");
});
