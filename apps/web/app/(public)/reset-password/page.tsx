import Link from "next/link";

import { resetPasswordAction } from "./actions";

export const metadata = { title: "Reset password · Voyagent" };

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams?: Promise<{ token?: string; error?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const token = params.token ?? "";
  const error = params.error ?? null;

  if (!token) {
    return (
      <main style={_shell}>
        <div style={_card}>
          <h1 style={{ fontSize: 22, marginTop: 0 }}>Invalid reset link</h1>
          <p>
            The reset link is missing its token. Please request a new one.
          </p>
          <p>
            <Link href="/forgot-password">Request a new link</Link>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main style={_shell}>
      <div style={_card}>
        <h1 style={{ fontSize: 22, marginTop: 0 }}>Choose a new password</h1>
        {error ? (
          <div
            style={{
              marginBottom: 12,
              padding: "10px 12px",
              background: "#fef2f2",
              border: "1px solid #fecaca",
              color: "#991b1b",
              borderRadius: 8,
              fontSize: 14,
            }}
          >
            {error}
          </div>
        ) : null}
        <form
          action={resetPasswordAction}
          style={{ display: "flex", flexDirection: "column", gap: 12 }}
        >
          <input type="hidden" name="token" value={token} />
          <label style={_label}>
            <span style={_labelText}>New password</span>
            <input
              type="password"
              name="new_password"
              minLength={12}
              required
              style={_input}
            />
          </label>
          <label style={_label}>
            <span style={_labelText}>Confirm new password</span>
            <input
              type="password"
              name="confirm_password"
              minLength={12}
              required
              style={_input}
            />
          </label>
          <button type="submit" style={_button}>
            Update password
          </button>
        </form>
      </div>
    </main>
  );
}

const _shell: React.CSSProperties = {
  minHeight: "calc(100dvh - 56px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 24,
  fontFamily: "system-ui, sans-serif",
};

const _card: React.CSSProperties = {
  width: "100%",
  maxWidth: 420,
  padding: 32,
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  background: "#fff",
};

const _label: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const _labelText: React.CSSProperties = { fontSize: 13, fontWeight: 600 };

const _input: React.CSSProperties = {
  padding: "8px 10px",
  border: "1px solid #d4d4d8",
  borderRadius: 6,
  fontSize: 14,
};

const _button: React.CSSProperties = {
  padding: "10px 16px",
  background: "#18181b",
  color: "#fafafa",
  border: "none",
  borderRadius: 6,
  fontSize: 14,
  cursor: "pointer",
};
