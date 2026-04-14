# @voyagent/tests-e2e

End-to-end Playwright suite for the Voyagent deployment.

## Purpose

This package is the black-box acceptance suite for Voyagent. It exercises
the live marketing site, docs renderer, metadata routes, contact form,
authenticated `/app` gate, public API endpoints, a basic accessibility
audit, and a very loose performance smoke check.

It is intentionally shallow: it validates contracts and user-visible
behavior, not internal implementation. It runs against a real deployment
(default `https://voyagent.globusdemos.com`) and expects the target to be
behind Cloudflare.

## Running locally

From the repo root:

```bash
pnpm --filter @voyagent/tests-e2e test:install
pnpm --filter @voyagent/tests-e2e test
```

The first command installs a chromium binary and its system dependencies.
The second runs the full suite against the default production URL.

## Targeting a different environment

Set `VOYAGENT_BASE_URL` to any reachable origin:

```bash
VOYAGENT_BASE_URL=https://staging.voyagent.globusdemos.com \
  pnpm --filter @voyagent/tests-e2e test
```

A global setup hook pings `${VOYAGENT_BASE_URL}/api/health` before any
spec runs. If the target is unreachable the run aborts with a clear
error, instead of every spec failing individually.

## Layout

```
tests/e2e/
  playwright.config.ts
  specs/
    _setup.ts                  global setup (health probe)
    marketing-landing.spec.ts  landing page hero, nav, stats, disclaimers
    marketing-nav.spec.ts      all top-nav routes respond and render
    domains.spec.ts            three domain deep-dive pages
    docs.spec.ts               /docs/[slug] for all 5 slugs
    metadata.spec.ts           robots.txt, sitemap.xml, head meta
    contact-form.spec.ts       client + server validation and success state
    app-gated.spec.ts          /app redirect to /sign-in when unauthenticated
    api-smoke.spec.ts          /api/health, schemas, chat error contract
    accessibility.spec.ts      axe-core audit on key pages
    performance-budget.spec.ts loose goto/FCP smoke
```

## Docker / CI

Use the `test:ci` script for CI runs. It emits JUnit, HTML and list
reporters in parallel:

```bash
pnpm --filter @voyagent/tests-e2e test:ci
```

HTML reports land in `tests/e2e/playwright-report/`, JUnit in
`tests/e2e/test-results/junit.xml`.

## Known gaps (v0)

- No authenticated-flow tests. The suite only verifies that the
  in-house middleware redirects unauthenticated visitors from `/app`
  to `/sign-in`; it does not drive a full sign-up / sign-in session.
- No real chat-stream tests. `ANTHROPIC_API_KEY` is unset on the target;
  the suite verifies the error contract (401 / 403 / 503 / redirect)
  rather than a successful chat turn.
- No multi-browser matrix. Only chromium desktop and chromium mobile run.
  WebKit and Firefox are omitted to keep the CI image small.
- No visual regression. Screenshots are captured on failure only.
- No load or soak testing. The performance spec is a single navigation
  with a generous 15s budget and a soft FCP warning.
