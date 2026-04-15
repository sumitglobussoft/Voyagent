import Link from "next/link";

import { forgotPasswordAction } from "./actions";

export const metadata = { title: "Forgot password · Voyagent" };

export default async function ForgotPasswordPage({
  searchParams,
}: {
  searchParams?: Promise<{ email?: string; submitted?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const email = params.email ?? "";
  const submitted = params.submitted === "1";

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
          maxWidth: 420,
          padding: 32,
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          background: "#fff",
        }}
      >
        <h1 style={{ fontSize: 22, marginTop: 0 }}>Reset your password</h1>
        {submitted ? (
          <>
            <p style={{ color: "#555", fontSize: 14 }}>
              If that email is registered, you&apos;ll receive a reset link
              shortly. Follow the link to choose a new password.
            </p>
            <p style={{ marginTop: 24, fontSize: 14 }}>
              <Link href="/sign-in">Back to sign in</Link>
            </p>
          </>
        ) : (
          <>
            <p style={{ color: "#555", fontSize: 14 }}>
              Enter your email and we&apos;ll send you a link to set a new
              password.
            </p>
            <form
              action={forgotPasswordAction}
              style={{ display: "flex", flexDirection: "column", gap: 12 }}
            >
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Email</span>
                <input
                  type="email"
                  name="email"
                  defaultValue={email}
                  required
                  style={{
                    padding: "8px 10px",
                    border: "1px solid #d4d4d8",
                    borderRadius: 6,
                    fontSize: 14,
                  }}
                />
              </label>
              <button
                type="submit"
                style={{
                  padding: "10px 16px",
                  background: "#18181b",
                  color: "#fafafa",
                  border: "none",
                  borderRadius: 6,
                  fontSize: 14,
                  cursor: "pointer",
                }}
              >
                Send reset link
              </button>
            </form>
            <p style={{ marginTop: 16, fontSize: 14 }}>
              <Link href="/sign-in">Back to sign in</Link>
            </p>
          </>
        )}
      </div>
    </main>
  );
}
