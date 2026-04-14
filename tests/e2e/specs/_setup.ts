// Global setup: fail fast if the target deployment is unreachable.
//
// Hits ${VOYAGENT_BASE_URL}/api/health before any spec runs. If the
// probe fails (non-200, bad JSON, or the request throws), the suite
// aborts with a clear message so engineers do not have to dig through
// dozens of unrelated failures.
//
// This module is NOT a test file. It is referenced from
// playwright.config.ts via the `globalSetup` field.

import { request } from "@playwright/test";

const DEFAULT_BASE_URL = "https://voyagent.globusdemos.com";

export default async function globalSetup(): Promise<void> {
  const baseURL = process.env.VOYAGENT_BASE_URL ?? DEFAULT_BASE_URL;
  const healthUrl = `${baseURL.replace(/\/+$/, "")}/api/health`;

  let ctx;
  try {
    ctx = await request.newContext({ ignoreHTTPSErrors: false });
    const res = await ctx.get(healthUrl, { timeout: 15_000 });
    if (!res.ok()) {
      throw new Error(
        `health probe returned HTTP ${res.status()} for ${healthUrl}`,
      );
    }
    const body = (await res.json()) as { status?: unknown };
    if (body.status !== "ok") {
      throw new Error(
        `health probe returned unexpected body for ${healthUrl}: ${JSON.stringify(
          body,
        )}`,
      );
    }
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    throw new Error(
      `Voyagent target unreachable at ${healthUrl} (${reason}). ` +
        `Set VOYAGENT_BASE_URL to a reachable origin or start the stack.`,
    );
  } finally {
    if (ctx) {
      await ctx.dispose();
    }
  }
}
