/**
 * Playwright Global Setup — Isolated Backend
 * ============================================
 * Starts an isolated backend server on port 8000 using a dedicated
 * playwright_test.db SQLite database that is completely separate from
 * the user's development smart_ambulance.db.
 *
 * The production database is NEVER touched.
 *
 * Steps:
 *  1. Fail fast if something is already listening on port 8000.
 *  2. Delete playwright_test.db if it exists (start fresh every run).
 *  3. Run app.seed against playwright_test.db to populate clean demo accounts.
 *  4. Start uvicorn on port 8000 with DATABASE_URL=playwright_test.db.
 *  5. Wait for the server to respond.
 *
 * globalTeardown stops the server and (optionally) removes the test DB.
 */

import { ChildProcess, execSync, spawn } from "child_process";
import { existsSync, rmSync } from "fs";
import { join } from "path";
import fetch from "node-fetch";

const BACKEND_DIR = join(__dirname, "../../../backend");
const TEST_DB     = join(BACKEND_DIR, "playwright_test.db");
const API_PORT    = 8000;
const READY_URL   = `http://localhost:${API_PORT}/api/v1/auth/me`;

const PW_ENV = {
  ...process.env,
  DATABASE_URL:                `sqlite:///${TEST_DB}`,
  RATE_LIMIT_ENABLED:          "0",
  SECRET_KEY:                  "smart_ambulance_playwright_test_key_isolated_9x7!",
  ACCESS_TOKEN_EXPIRE_MINUTES: "1440",
  ALLOWED_ORIGINS:             "http://localhost:3000",
  TRAFFIC_PROXIMITY_KM:        "0.01",   // tiny threshold → proximity alert fires on first GPS update near hospital
};

declare global {
  // eslint-disable-next-line no-var
  var __PW_BACKEND_PROC__: ChildProcess | undefined;
}

async function isPortInUse(port: number): Promise<boolean> {
  try {
    const r = await fetch(`http://localhost:${port}/api/v1/auth/me`, {
      signal: AbortSignal.timeout(1_000),
    } as any);
    return true; // something is responding
  } catch {
    return false;
  }
}

async function waitForReady(url: string, timeoutMs = 30_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(500) } as any);
      if (r.status === 401 || r.status === 200) return;
    } catch { /* not ready yet */ }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`Backend did not become ready at ${url} within ${timeoutMs}ms`);
}

export default async function globalSetup() {
  // ── 1. Verify port 8000 is free ───────────────────────────────────────────
  if (await isPortInUse(API_PORT)) {
    throw new Error(
      `\n\nPort ${API_PORT} is already in use.\n` +
      `Please stop your development backend before running Playwright tests.\n` +
      `The Playwright test suite starts its own isolated backend on this port.\n`
    );
  }

  // ── 2. Remove stale test database ─────────────────────────────────────────
  if (existsSync(TEST_DB)) {
    rmSync(TEST_DB);
    console.log(`[PW] Removed stale test DB: playwright_test.db`);
  }

  // ── 3. Seed the isolated test database ────────────────────────────────────
  console.log("[PW] Seeding playwright_test.db ...");
  await new Promise<void>((resolve, reject) => {
    const seed = spawn("python", ["-m", "app.seed"], {
      cwd: BACKEND_DIR,
      env: PW_ENV,
      stdio: ["ignore", "pipe", "pipe"],
    });
    seed.stdout?.on("data", (d) => process.stdout.write(`[seed] ${d}`));
    seed.stderr?.on("data", (d) => process.stderr.write(`[seed] ${d}`));
    seed.on("close", (code) => {
      if (code === 0) { resolve(); }
      else { reject(new Error(`seed.py exited with code ${code}`)); }
    });
  });
  console.log("[PW] Database seeded. Drivers D1/D2 have GPS coords and no active trips.");

  // ── 4. Start isolated uvicorn on port 8000 ────────────────────────────────
  console.log(`[PW] Starting isolated backend on port ${API_PORT} ...`);
  const server = spawn(
    "python",
    ["-m", "uvicorn", "app.main:app",
      "--host", "127.0.0.1",
      "--port", String(API_PORT),
      "--log-level", "warning"],
    {
      cwd: BACKEND_DIR,
      env: PW_ENV,
      stdio: ["ignore", "pipe", "pipe"],
      detached: false,
    }
  );
  server.stdout?.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  server.stderr?.on("data", (d) => process.stderr.write(`[backend] ${d}`));
  server.on("error", (e) => console.error("[backend] Error:", e));
  globalThis.__PW_BACKEND_PROC__ = server;

  // ── 5. Wait until ready ────────────────────────────────────────────────────
  await waitForReady(READY_URL, 30_000);
  console.log(`[PW] Isolated backend ready at http://localhost:${API_PORT}`);
  console.log(`[PW] Database: playwright_test.db (isolated, not smart_ambulance.db)`);
}
