# Vendor onboarding — what we need from your travel agency

To turn on real bookings, ticketing, accounting posting, and visa
automation in Voyagent, we need credentials from the B2B travel vendors
you already work with (or want to work with). This page lists each
vendor, what to acquire, where to sign up, and what to send back to us.

Most of these are partner programs that require an active travel-agency
relationship — IATA accreditation, GST registration, or an existing
agency account on the vendor's portal. Voyagent is the software layer;
the agency relationship is yours.

> **Sending credentials safely.** Never send passwords or API keys over
> WhatsApp, SMS, or unencrypted email. Use a password manager share
> (1Password, Bitwarden, Dashlane), an end-to-end encrypted message
> (Signal, ProtonMail), or a secure file drop. We'll set up an encrypted
> intake channel for you on request.

---

## 1. TBO Holidays — hotel inventory

**What it unlocks:** Real hotel search, price re-check, booking, and
cancellation across TBO's global hotel inventory. Without these, the
hotels agent can search and price but cannot book.

**Account type:** TBO B2B partner account. Requires a registered travel
agency (IATA / TAAI / TAFI accreditation in India; equivalent abroad).

**Steps:**

1. If you don't already have a TBO account, register at
   <https://www.tboholidays.com/> → "Register" / "Become a partner".
   Approval can take 3-7 business days; you'll need to upload your
   agency licence and GST certificate.
2. Once active, request **API access** from your TBO account manager.
   Mention you need both the **Hotel Search** and **Hotel Booking**
   endpoints, plus **sandbox (test) credentials** before going live.
3. The technical contact is typically `apisupport@tbotechnology.in`.

**What to send us:**
- TBO API username
- TBO API password
- Confirmation of which environment (sandbox or production)
- The base URL TBO assigned you (typically
  `https://api.tbotechnology.in/...`)

**Time from your side:** 30 minutes once the partner account is
approved.

---

## 2. Amadeus — flight inventory & ticketing

Amadeus has two tiers; both can be active in parallel.

### 2a. Self-service (sandbox) — already wired

**What it unlocks:** Fare search, fare rules, basic PNR creation against
Amadeus's test environment. Useful for development and demos but cannot
issue real tickets.

**Steps:**

1. Sign up at <https://developers.amadeus.com> (free, instant).
2. Create a new app in the developer portal.
3. Copy the **Client ID** and **Client Secret**.

**What to send us:**
- Amadeus self-service Client ID
- Amadeus self-service Client Secret

**Time from your side:** 10 minutes.

### 2b. Production / Enterprise tier — required for real ticketing

**What it unlocks:** Real ticket issuance, real PNR management, BSP
settlement integration. This is the credential that turns Voyagent into
a live ticketing system.

**Account type:** Amadeus Travel Agency (ATA) accreditation in your
operating country. In India, this goes through **Amadeus India** at
<https://amadeus.com/en/about/our-locations/asia-pacific/india>. In
other regions, your local Amadeus office.

**Steps:**

1. Contact Amadeus enterprise sales via
   <https://amadeus.com/en/contact-us> or your regional Amadeus office.
2. You'll go through their accreditation process (commercial paperwork,
   technical onboarding, training). This typically takes **2-6 weeks**.
3. Once accredited, request the **Amadeus Web Services** kit
   (production API credentials, Office ID, Pseudo-City Code).

**What to send us:**
- Amadeus production Client ID and Client Secret
- Office ID and Pseudo-City Code (PCC)
- Confirmation of which Amadeus node/region you're provisioned on

**Time from your side:** 2-6 weeks total. Start this early — it's the
slowest item on this list.

---

## 3. Tally Prime — desktop accounting integration

**What it unlocks:** Voyagent posts journals, vouchers, and invoices
directly into your Tally Prime ledger — no manual re-keying. Currently
the only fully wired accounting integration; Zoho Books, Busy, and
QuickBooks are roadmap.

**Account type:** Standard Tally Prime licence. The Educational version
will also work for testing but cannot post to production.

**Steps:**

1. If you don't have Tally Prime, download from
   <https://tallysolutions.com/download/>. Production licence is roughly
   ₹18,000-22,000 one-time (single user) — buy through any Tally partner
   in your city.
2. Install on the desktop machine that will be the "accounting host"
   (the machine where Voyagent's desktop app posts from).
3. In Tally Prime, enable the **Gateway Server**:
   - `Gateway of Tally → F1 (Help) → Settings → Connectivity → Client/Server configuration`
   - Set **TallyPrime is acting as → Both** (Client and Server)
   - Set **Port** → `9000`
   - Set **Enable ODBC server** → `Yes`
   - Save and restart Tally Prime.
4. Confirm Tally is listening: open a browser on the same machine and
   visit <http://localhost:9000>. You should see a basic XML response
   from Tally (not a connection error).

**What to send us:**
- Confirmation Tally is running and accessible at `http://localhost:9000`
  on the desktop host
- Your Company name as it appears in Tally (case-sensitive — we use this
  to scope which company's books we post into)
- A short test recording (Loom / screen capture, 2-3 minutes) showing
  Tally open with the Company you want us to integrate, so we can
  confirm voucher types and ledger structure

**Security note:** The Tally Gateway Server has no built-in authentication
(it trusts whatever connects on `localhost:9000`). Voyagent's desktop
bridge runs on the same machine and only ever posts on your behalf. Do
**NOT** expose port 9000 to the public internet.

**Time from your side:** 1 hour (install + configure + test).

---

## 4. VFS Global — visa portal automation

**What it unlocks:** Voyagent's browser-runner automates filling visa
applications, uploading documents, and booking appointments on VFS
Global portals. Each destination country / source country combination
(e.g. UAE visa for Indian applicants, UK visa for Indian applicants)
needs its own portal selectors.

**Account type:** Each visa portal requires either a personal
applicant account or a registered agency account on that specific portal.
VFS does not have a developer / API tier — automation is per-portal.

**Steps (per visa portal you want automated):**

1. Pick the portal you want first. Highest-volume options for Indian
   travel agencies:
   - **UAE visa via VFS** — <https://visa.vfsglobal.com/are/en/>
   - **UK visa via VFS** — <https://visa.vfsglobal.com/gbr/en/>
   - **Schengen via VFS** — <https://www.vfsglobal.com/en/individuals/index.html>
2. Confirm one of your test agencies has an **active account** on that
   portal — username + password that can log in and start an application.
3. Record a **2-5 minute screen capture** of one full application going
   through end-to-end (login → fill form → upload documents → pay /
   book appointment). This is what we turn into a Playwright handler.
4. Note any quirks: which fields are mandatory, which optional, what
   document formats the portal accepts, what the appointment-booking
   flow looks like.

**What to send us:**
- Which visa portal (destination + source country)
- Test account username + password (encrypted channel; see top of page)
- Screen recording of one end-to-end application
- A short note on any quirks you've observed in past applications

**Security note:** We store the credentials encrypted per tenant and
only use them to fill the same forms an agency staffer would manually
fill. We never share them across tenants and never send them anywhere
outside the browser-runner machine.

**Time from your side:** 1-2 hours per portal (account setup + recording).

---

## 5. Hotelbeds — second hotel vendor (optional)

**What it unlocks:** Hotelbeds covers 180k+ properties globally with
strong European inventory — useful as a fallback / comparison source
alongside TBO. Optional; only worth pursuing if your agencies sell
European leisure or if you want a redundant vendor.

**Account type:** Hotelbeds APItude developer access. Sandbox is
free and instant; production requires a partner contract.

**Steps:**

1. Sign up at <https://developer.hotelbeds.com/sign-up>.
2. Verify your email; the developer portal gives you instant sandbox
   API key + secret.
3. For production, contact Hotelbeds sales via
   <https://www.hotelbeds.com/> → "Become a partner".

**What to send us:**
- Hotelbeds API Key
- Hotelbeds Shared Secret
- Confirmation of which environment (sandbox `api.test.hotelbeds.com` or
  production `api.hotelbeds.com`)

**Time from your side:** 15 minutes (sandbox); production timeline
depends on Hotelbeds' partner team.

---

## What we will do once we have each credential

| Credential | What ships once we have it |
|---|---|
| TBO API user/pass | Hotel booking, cancellation, booking lookup go from "stubbed" to "live" |
| Amadeus self-service | Fare search + PNR creation in dev / demo flows |
| Amadeus production | Real ticket issuance, PNR management, BSP settlement |
| Tally Gateway running | Desktop bridge posts journals + vouchers from Voyagent into Tally |
| VFS portal recording + creds | Browser-runner automation for that visa portal |
| Hotelbeds API key | Second hotel vendor scaffolded in parallel with TBO |

## Suggested sequence

If you're starting from zero, this is the order we recommend chasing:

1. **Tally Prime** install + Gateway config (1 hour, no waiting on anyone)
2. **Amadeus self-service** key (10 minutes, instant)
3. **Hotelbeds sandbox** key (15 minutes, instant) — only if you want a second hotel vendor
4. **TBO partner registration** start in parallel (3-7 day approval)
5. **Amadeus enterprise** start in parallel (2-6 weeks — start now even if you're not ready to ship)
6. **VFS portal** recording per portal — only when you have a specific
   portal you want automated; not bulk

## Questions / send credentials

Reach out to your Voyagent contact when you have each item ready.
Voyagent will set up an encrypted intake channel for the credentials
themselves. The screen recordings can be shared via Loom, Google Drive,
or any private link.
