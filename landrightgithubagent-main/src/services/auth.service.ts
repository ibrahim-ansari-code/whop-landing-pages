import { App } from "octokit";
import fs from "fs";
import path from "path";
import type { Env } from "../config/env.js";

let appInstance: App | null = null;

function resolvePemPath(rawPath: string): string {
  const resolved = path.isAbsolute(rawPath) ? rawPath : path.resolve(process.cwd(), rawPath);
  if (!fs.existsSync(resolved)) {
    console.error(
      "[auth] PEM file missing or unreadable: path=%s PRIVATE_KEY_PATH=%s",
      resolved,
      rawPath
    );
    throw new Error(`PEM file not found at ${resolved} (PRIVATE_KEY_PATH=${rawPath}). Copy your GitHub App private key there or set PRIVATE_KEY_PATH to the full path.`);
  }
  return resolved;
}

export function getApp(env: Env): App {
  if (!appInstance) {
    const pemPath = resolvePemPath(env.PRIVATE_KEY_PATH);
    let privateKey: string;
    try {
      privateKey = fs.readFileSync(pemPath, "utf8");
    } catch (err) {
      console.error("[auth] PEM file missing or unreadable: path=%s", pemPath, err);
      throw err;
    }
    appInstance = new App({ appId: env.GITHUB_APP_ID, privateKey });
  }
  return appInstance;
}

export async function getInstallationOctokit(env: Env) {
  const app = getApp(env);
  return app.getInstallationOctokit(Number(env.GITHUB_INSTALLATION_ID));
}
