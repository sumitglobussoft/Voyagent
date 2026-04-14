import Link from "next/link";

import { SignUpForm } from "./SignUpForm";

export const metadata = {
  title: "Create your account · Voyagent",
};

export default function SignUpPage() {
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
        <SignUpForm />
        <p style={{ marginTop: 24, fontSize: 14, color: "#555" }}>
          Already have an account? <Link href="/app/sign-in">Sign in</Link>
        </p>
      </div>
    </main>
  );
}
