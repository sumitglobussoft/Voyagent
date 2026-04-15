# Getting started with Voyagent

This guide walks a new travel agency owner through their first day on
Voyagent — from signing in to exporting their audit log. If you are
looking for technical/architecture docs, jump to
[`ARCHITECTURE.md`](./ARCHITECTURE.md) or [`STACK.md`](./STACK.md) instead.

Throughout this guide, "the app" refers to your Voyagent deployment.
On the shared demo it is <https://voyagent.globusdemos.com>. On a
self-hosted install it will be whatever URL your admin configured.

---

## 1. Sign in (or accept an invite)

There are two ways you might be starting:

* **You signed up yourself.** Go to `/app/sign-up`, enter your name,
  agency name, email, and a strong password, and you are in. You are
  the tenant owner by default.
* **Your admin invited you.** Open the invite email, click the link,
  set a password, and you are dropped straight into your agency's
  workspace at `/app`.

If you ever forget your password, `/app/forgot-password` mails a reset
link.

## 2. Create your first chat session

Navigate to [`/app/chat`](../README.md#app-routes) and click "New
session". Try something like:

> Find the cheapest one-way BOM→DXB economy fare in the next two weeks
> for 2 adults.

The agent will pick the right driver, run the search, and stream the
result back. Every chat session is scoped to your tenant and the
transcript is automatically persisted to the audit log.

## 3. Log a customer enquiry

When a customer calls in, log the enquiry at
[`/app/enquiries/new`](../README.md#app-routes). Fill in:

* **Customer name + contact**
* **Origin / destination** (airport codes or city names)
* **Travel dates / flexibility**
* **Pax count + cabin class**
* **Free-text notes** (preferences, special requests, etc.)

Enquiries are persistent records and show up in the agency-wide inbox
at `/app/enquiries`.

## 4. Promote an enquiry to a chat session

From the enquiry detail page, click **"Open in chat"**. This creates a
new chat session pre-seeded with the enquiry context so the agent
already knows who the customer is and what they asked for. No need to
re-paste anything.

## 5. Review approvals in the inbox

Any action that touches money (issuing a ticket, posting a journal
entry, refunding a booking) lands in the approvals inbox at
[`/app/approvals`](../README.md#app-routes) first. As a reviewer you
will see:

* What the agent proposes to do
* Why (the chain-of-thought rationale, if enabled)
* Expected cost
* An **Approve** / **Reject** button

Nothing hits a vendor or your accounting system until a human clicks
Approve.

## 6. Invite a teammate (tenant admin)

If you are the tenant admin, go to `/app/settings` → **Team** → **Invite
member**. Enter their email + role (`admin`, `member`, or `viewer`).
They get a signed invite link valid for 7 days. The invite is scoped to
your tenant so new members land in the right workspace automatically.

## 7. Configure tenant settings

Still under `/app/settings`, the **General** tab lets you configure:

* **Default locale** (e.g. `en-IN`, `en-GB`, `en-US`) — affects date,
  number, and currency formatting in reports.
* **Reporting currency** (e.g. `INR`, `USD`, `AED`). FX conversions
  happen automatically on output; underlying transactions stay in their
  native currency.
* **Daily token budget** — a soft spend cap on the agent runtime. Once
  hit, the agent refuses new LLM calls until the next day.
* **Approval thresholds** — the money amount above which an action
  automatically routes to approvals instead of auto-executing.

## 8. Export your audit log

For compliance — and because India DPDP requires it on demand — you
can export the full audit log at `/app/audit`. Click **Export** →
**CSV**. The resulting file has every event for your tenant: logins,
chat turns, enquiries, approvals, driver calls, accounting writes.

---

## Where to next?

* **Connect your first driver** → [`DRIVERS.md`](./DRIVERS.md)
* **Onboarding a real vendor** → [`VENDOR_ONBOARDING.md`](./VENDOR_ONBOARDING.md)
* **What's happening under the hood** → [`ARCHITECTURE.md`](./ARCHITECTURE.md)
* **Security posture** → [`SECURITY.md`](./SECURITY.md)
* **Day-2 operations (runbook)** → [`RUNBOOK.md`](./RUNBOOK.md)
