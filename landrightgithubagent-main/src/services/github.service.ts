import fs from "fs";
import path from "path";
import { getInstallationOctokit } from "./auth.service.js";
import type { Env } from "../config/env.js";

const WORKFLOWS_PREFIX = ".github/workflows";

interface AgentState {
  lastGoodCommitSha: string | null;
  lastGoodBranch: string | null;
}

function readState(env: Env): AgentState {
  try {
    const raw = fs.readFileSync(env.STATE_FILE, "utf8");
    const data = JSON.parse(raw) as AgentState;
    return { lastGoodCommitSha: data.lastGoodCommitSha ?? null, lastGoodBranch: data.lastGoodBranch ?? null };
  } catch {
    return { lastGoodCommitSha: null, lastGoodBranch: null };
  }
}

function writeState(env: Env, state: AgentState): void {
  fs.writeFileSync(env.STATE_FILE, JSON.stringify(state, null, 2), "utf8");
}

export function getLastGoodCommit(env: Env): { sha: string; branch: string } | null {
  const s = readState(env);
  if (s.lastGoodCommitSha && s.lastGoodBranch) return { sha: s.lastGoodCommitSha, branch: s.lastGoodBranch };
  return null;
}

function setLastGoodCommit(env: Env, sha: string, branch: string): void {
  writeState(env, { lastGoodCommitSha: sha, lastGoodBranch: branch });
}

function shouldSkipPath(filePath: string): boolean {
  const normalized = path.normalize(filePath).replace(/\\/g, "/");
  return normalized === WORKFLOWS_PREFIX || normalized.startsWith(WORKFLOWS_PREFIX + "/");
}

/** Fetches file content from the repo. Returns decoded string or throws. */
export async function getFileContent(
  env: Env,
  filePath: string,
  branch?: string
): Promise<string> {
  const octokit = await getInstallationOctokit(env);
  const targetBranch = branch ?? env.PRODUCTION_BRANCH;
  const { data } = await octokit.rest.repos.getContent({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    path: filePath,
    ref: targetBranch,
  });
  if (Array.isArray(data)) {
    throw new Error(`Path is a directory: ${filePath}`);
  }
  if (data.type !== "file" || data.content === undefined) {
    throw new Error(`Not a file or missing content: ${filePath}`);
  }
  return Buffer.from(data.content, "base64").toString("utf8");
}

/**
 * Create the initial commit on an empty repo (no branches yet) and create refs/heads/<branch>.
 * Used when createOrUpdateFileContents fails with 404 (reference not found).
 */
async function createInitialCommit(
  octokit: Awaited<ReturnType<typeof getInstallationOctokit>>,
  env: Env,
  filePath: string,
  content: string,
  message: string,
  targetBranch: string
): Promise<{ sha: string }> {
  const { data: blob } = await octokit.rest.git.createBlob({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    content: Buffer.from(content, "utf8").toString("base64"),
    encoding: "base64",
  });
  const { data: tree } = await octokit.rest.git.createTree({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    tree: [{ path: filePath, sha: blob.sha, mode: "100644" as const, type: "blob" as const }],
  });
  const { data: commit } = await octokit.rest.git.createCommit({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    message,
    tree: tree.sha,
    parents: [],
  });
  await octokit.rest.git.createRef({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    ref: `refs/heads/${targetBranch}`,
    sha: commit.sha,
  });
  setLastGoodCommit(env, commit.sha, targetBranch);
  return { sha: commit.sha };
}

export async function updateRecord(
  env: Env,
  filePath: string,
  content: string,
  message: string,
  branch?: string
): Promise<{ sha: string }> {
  const octokit = await getInstallationOctokit(env);
  const targetBranch = branch ?? env.PRODUCTION_BRANCH;

  let sha: string | undefined;
  try {
    const { data } = await octokit.rest.repos.getContent({
      owner: env.GITHUB_REPO_OWNER,
      repo: env.GITHUB_REPO_NAME,
      path: filePath,
      ref: targetBranch,
    });
    if (!Array.isArray(data)) sha = data.sha;
  } catch {
    // File does not exist, create new
  }

  try {
    const { data } = await octokit.rest.repos.createOrUpdateFileContents({
      owner: env.GITHUB_REPO_OWNER,
      repo: env.GITHUB_REPO_NAME,
      path: filePath,
      message,
      content: Buffer.from(content, "utf8").toString("base64"),
      sha,
      branch: targetBranch,
    });
    if (data.commit?.sha) setLastGoodCommit(env, data.commit.sha, targetBranch);
    return { sha: data.commit?.sha ?? "" };
  } catch (err: unknown) {
    const status = (err as { status?: number })?.status ?? (err as { response?: { status?: number } })?.response?.status;
    const msg = err instanceof Error ? err.message : String(err);
    if (status === 404 && (msg.includes("Reference") || msg.includes("not found") || msg.includes("branch"))) {
      return createInitialCommit(octokit, env, filePath, content, message, targetBranch);
    }
    throw err;
  }
}

export interface DeployFile {
  path: string;
  content: string;
}

export async function deployToProduction(
  env: Env,
  files: DeployFile[],
  message: string
): Promise<{ sha: string }> {
  const octokit = await getInstallationOctokit(env);
  const branch = env.PRODUCTION_BRANCH;

  const toDeploy = files.filter((f) => !shouldSkipPath(f.path));
  if (toDeploy.length === 0) {
    throw new Error("No files to deploy after excluding .github/workflows");
  }

  // Get branch ref to get base tree
  const { data: refData } = await octokit.rest.git.getRef({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    ref: `heads/${branch}`,
  });
  const baseSha = refData.object.sha;

  const { data: commitData } = await octokit.rest.git.getCommit({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    commit_sha: baseSha,
  });
  let baseTreeSha = commitData.tree.sha;

  // Create blobs and build tree
  const tree = await Promise.all(
    toDeploy.map(async (f) => {
      const { data: blob } = await octokit.rest.git.createBlob({
        owner: env.GITHUB_REPO_OWNER,
        repo: env.GITHUB_REPO_NAME,
        content: Buffer.from(f.content, "utf8").toString("base64"),
        encoding: "base64",
      });
      return { path: f.path, sha: blob.sha, mode: "100644" as const, type: "blob" as const };
    })
  );

  const { data: newTree } = await octokit.rest.git.createTree({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    tree,
    base_tree: baseTreeSha,
  });

  const { data: newCommit } = await octokit.rest.git.createCommit({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    message,
    tree: newTree.sha,
    parents: [baseSha],
  });

  await octokit.rest.git.updateRef({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    ref: `heads/${branch}`,
    sha: newCommit.sha,
  });

  setLastGoodCommit(env, newCommit.sha, branch);
  return { sha: newCommit.sha };
}

export async function rollbackToLastGood(env: Env): Promise<{ sha: string } | null> {
  const last = getLastGoodCommit(env);
  if (!last) return null;

  const octokit = await getInstallationOctokit(env);
  await octokit.rest.git.updateRef({
    owner: env.GITHUB_REPO_OWNER,
    repo: env.GITHUB_REPO_NAME,
    ref: `heads/${env.PRODUCTION_BRANCH}`,
    sha: last.sha,
  });
  return { sha: last.sha };
}
