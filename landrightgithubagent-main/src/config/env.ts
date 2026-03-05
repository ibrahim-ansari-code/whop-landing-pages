import { z } from "zod";
import dotenv from "dotenv";

dotenv.config();

const envSchema = z.object({
  PORT: z.coerce.number().default(4000),
  HOST: z.string().default("localhost"),
  GITHUB_APP_ID: z.string().min(1, "GITHUB_APP_ID is required"),
  GITHUB_INSTALLATION_ID: z.string().min(1, "GITHUB_INSTALLATION_ID is required"),
  GITHUB_REPO_OWNER: z.string().min(1, "GITHUB_REPO_OWNER is required"),
  GITHUB_REPO_NAME: z.string().min(1, "GITHUB_REPO_NAME is required"),
  PRIVATE_KEY_PATH: z.string().min(1, "PRIVATE_KEY_PATH is required").transform((s) => s.trim()),
  API_KEY: z.string().optional().default(""),
  GENERATOR_OUTPUT_PATH: z.string().default("./generator-output"),
  PRODUCTION_BRANCH: z.string().default("production"),
  GENERATOR_PORT: z.coerce.number().default(8000),
  GENERATOR_REPORT_URL: z.string().optional(),
  TRACK_API_KEY: z.string().optional(),
  AGENT_BASE_URL: z.string().url().default("http://localhost:4000"),
  STATE_FILE: z.string().default(".agent-state.json"),
  EVENTS_FILE: z.string().default("data/events.json"),
  MOCK_ANALYTICS_PATH: z.string().default("python-agent/mock-analytics.json"),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
  const issues = parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("\n");
  throw new Error(`Invalid environment:\n${issues}`);
}

export const env = parsed.data;
export type Env = z.infer<typeof envSchema>;
