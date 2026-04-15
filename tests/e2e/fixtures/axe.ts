// Shared axe-core wrapper for accessibility specs.
//
// Centralizing the AxeBuilder configuration keeps per-page specs short
// and gives us one place to disable rules that are known to be false
// positives or accepted design decisions.

import { test as base, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

export type AxeRunOptions = {
  tags?: string[];
  disabledRules?: string[];
};

/**
 * Run axe-core against `page` and return the full results object.
 *
 * Defaults to the WCAG 2.0/2.1 A + AA rulesets which is what the live
 * site aims to ship. Additional tags or rule exclusions can be passed
 * by callers that need them.
 */
export async function runAxe(
  page: Page,
  options: AxeRunOptions = {},
): Promise<Awaited<ReturnType<InstanceType<typeof AxeBuilder>["analyze"]>>> {
  const tags = options.tags ?? ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
  const disabled = options.disabledRules ?? [
    // Allow known-acceptable violations here with a comment explaining why.
    // (empty for v0 — we want the baseline to show everything)
  ];

  const builder = new AxeBuilder({ page }).withTags(tags);
  if (disabled.length > 0) {
    builder.disableRules(disabled);
  }
  return builder.analyze();
}

export const test = base.extend<Record<string, never>>({});
export { expect } from "@playwright/test";
