import Link from "next/link";

import { safeNextPath } from "@/lib/next-url";

import { SignUpForm } from "./SignUpForm";

export const metadata = {
  title: "Create your account · Voyagent",
};

// Next 15 made `searchParams` a Promise on server pages.
export default async function SignUpPage({
  searchParams,
}: {
  searchParams?: Promise<{ next?: string }>;
}) {
  const params = (await searchParams) ?? {};
  // Validate at the page boundary; the action validates again. If the
  // visitor arrived here via an unauth deep link (middleware routes to
  // /app/sign-in, but they might click through to /app/sign-up) we
  // forward `next` so a freshly-created account can land on the
  // originally requested page.
  const next = safeNextPath(params.next);
  // Only render the hidden input if the user actually arrived with a
  // next param; empty-string signals "no explicit destination" to the
  // server action and falls back to /chat?welcome=1.
  const hasExplicitNext = params.next !== undefined && next === params.next;

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
          maxWidth: 440,
          padding: 32,
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          background: "#fff",
        }}
      >
        <h1 style={{ fontSize: 24, marginTop: 0, marginBottom: 8 }}>Create your agency</h1>
        <p style={{ marginTop: 0, marginBottom: 24, color: "#555" }}>
          Spin up a Voyagent workspace for your team.
        </p>
        <SignUpForm next={hasExplicitNext ? next : ""} />
        <p style={{ marginTop: 24, fontSize: 14, color: "#555" }}>
          Already have an account?{" "}
          <Link
            href={
              hasExplicitNext
                ? `/sign-in?next=${encodeURIComponent(next)}`
                : "/sign-in"
            }
          >
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
