/**
 * Sign-in page.
 *
 * Server-rendered form posting to a server action. No client JS required
 * for the happy path — error state is rendered server-side from
 * `useFormState`'s state object.
 *
 * Demo account banner + `?demo=1` pre-fills the form so anyone can
 * poke at the live app without creating an account. The demo tenant
 * ("Voyagent Demo Agency") is deliberately isolated — no real customer
 * data.
 */
import Link from "next/link";

import { safeNextPath } from "@/lib/next-url";

import { SignInForm } from "./SignInForm";

// Public demo account. Deliberately exposed on the sign-in page so visitors
// can poke at the app without creating a tenant. Tenant is isolated.
const DEMO_EMAIL = "demo@voyagent.globusdemos.com";
const DEMO_PASSWORD = "DemoPassword123!";

export const metadata = {
  title: "Sign in · Voyagent",
};

// Next 15 made `searchParams` a Promise on server pages.
export default async function SignInPage({
  searchParams,
}: {
  searchParams?: Promise<{ next?: string; demo?: string }>;
}) {
  const params = (await searchParams) ?? {};
  // Validate `next` at the page layer too so the hidden input carries
  // only values we'd be willing to redirect to — defence in depth; the
  // server action validates again before the final `redirect()`.
  const next = safeNextPath(params.next);
  const prefillDemo = params.demo === "1";

  return (
    <main
      style={{
        minHeight: "calc(100dvh - 56px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 400,
          padding: 32,
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          background: "#fff",
        }}
      >
        <h1 style={{ fontSize: 24, marginTop: 0, marginBottom: 8 }}>Sign in</h1>
        <p style={{ marginTop: 0, marginBottom: 16, color: "#555" }}>
          Welcome back to Voyagent.
        </p>

        <div
          style={{
            marginBottom: 20,
            padding: "12px 14px",
            background: "#f0f9ff",
            border: "1px solid #bae6fd",
            borderRadius: 8,
            fontSize: 13,
            color: "#0c4a6e",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Try the demo</div>
          <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12, lineHeight: 1.6 }}>
            {DEMO_EMAIL}
            <br />
            {DEMO_PASSWORD}
          </div>
          {prefillDemo ? null : (
            <Link
              href="/sign-in?demo=1"
              style={{ display: "inline-block", marginTop: 8, color: "#0369a1", fontWeight: 500 }}
            >
              Use demo credentials →
            </Link>
          )}
        </div>

        <SignInForm
          next={next}
          defaultEmail={prefillDemo ? DEMO_EMAIL : ""}
          defaultPassword={prefillDemo ? DEMO_PASSWORD : ""}
        />
        <p style={{ marginTop: 24, fontSize: 14, color: "#555" }}>
          Don&apos;t have an account?{" "}
          <Link
            href={
              next && next !== "/chat"
                ? `/sign-up?next=${encodeURIComponent(next)}`
                : "/sign-up"
            }
          >
            Create one
          </Link>
        </p>
      </div>
    </main>
  );
}
