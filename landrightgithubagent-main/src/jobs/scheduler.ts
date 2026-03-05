import cron from "node-cron";
import { env } from "../config/env.js";
import { instrumentAll } from "../services/instrument.service.js";
import { deployToProduction, rollbackToLastGood } from "../services/github.service.js";
import {
  buildReport,
  sendReportToGenerator,
  clearEventsAfterReport,
} from "../services/report.service.js";
import type { Logger } from "pino";

export function startScheduler(log: Logger): void {
  // Every hour: instrument + deploy
  cron.schedule("0 * * * *", async () => {
    log.info("Running hourly instrument + deploy");
    try {
      const files = instrumentAll(env);
      if (files.length === 0) {
        log.info("No HTML files in generator-output, skipping deploy");
        return;
      }
      const { sha } = await deployToProduction(
        env,
        files,
        `Deploy instrumented pages (${files.length} files)`
      );
      log.info({ sha, fileCount: files.length }, "Deploy completed");
    } catch (err) {
      log.error({ err }, "Deploy failed, attempting rollback");
      try {
        const result = await rollbackToLastGood(env);
        if (result) log.warn({ sha: result.sha }, "Rolled back to last good commit");
        else log.warn("No last good commit to rollback to");
      } catch (rollbackErr) {
        log.error({ err: rollbackErr }, "Rollback failed");
      }
    }
  });

  // Every day at 00:00: report
  cron.schedule("0 0 * * *", async () => {
    log.info("Running daily report");
    try {
      const report = buildReport(env);
      if (env.GENERATOR_REPORT_URL?.trim()) {
        const ok = await sendReportToGenerator(env, report);
        if (ok) {
          clearEventsAfterReport(env);
          log.info({ variants: report.variants.length }, "Report sent to Generator");
        } else {
          log.warn("Failed to send report to Generator");
        }
      } else {
        log.info({ variants: report.variants.length }, "Report built (no GENERATOR_REPORT_URL)");
      }
    } catch (err) {
      log.error({ err }, "Report job failed");
    }
  });

  log.info("Scheduler started: hourly instrument+deploy, daily report");
}
