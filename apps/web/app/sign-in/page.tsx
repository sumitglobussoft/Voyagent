/**
 * Sign-in page.
 *
 * Server-rendered form posting to a server action. No client JS required
 * for the happy path — error state is rendered server-side from
 * `useFormState`'s state object.
 */
import Link from "next/link";

import { SignInForm } from "./SignInForm";

export const metadata = {
  title: "Sign in · Voyagent",
};

export default function SignInPage({
  searchParams,
}: {
  searchParams?: { next?: string };
}) {
  const next = searchParams?.next ?? "/app/chat";

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
        <p style={{ marginTop: 0, marginBottom: 24, color: "#555" }}>
          Welcome back to Voyagent.
        </p>
        <SignInForm next={next} />
        <p style={{ marginTop: 24, fontSize: 14, color: "#555" }}>
          Don&apos;t have an account?{" "}
          <Link href="/app/sign-up">Create one</Link>
        </p>
      </div>
    </main>
  );
}
