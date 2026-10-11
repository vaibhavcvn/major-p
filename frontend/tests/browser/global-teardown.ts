/**
 * Playwright Global Teardown
 * Kills the isolated backend process started by global-setup.ts.
 */

export default async function globalTeardown() {
  const proc = globalThis.__PW_BACKEND_PROC__;
  if (proc && !proc.killed) {
    proc.kill("SIGTERM");
    // Give it a moment to exit gracefully
    await new Promise<void>((resolve) => {
      proc.on("close", () => resolve());
      setTimeout(() => { proc.kill("SIGKILL"); resolve(); }, 3_000);
    });
    console.log("[PW-teardown] Backend server stopped.");
  }
}
