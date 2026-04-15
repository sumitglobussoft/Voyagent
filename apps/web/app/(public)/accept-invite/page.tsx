import Link from "next/link";

import { acceptInviteAction } from "./actions";

export const metadata = { title: "Accept invite · Voyagent" };

type LookupMeta = {
  email: string;
  role: string;
  tenant_name: string;
  inviter_email: string;
  expires_at: string;
};

function apiBase(): string {
  return (
    process.env.VOYAGENT_INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_VOYAGENT_API_URL ??
    "http://localhost:8000"
  );
}

async function lookup(token: string): Promise<LookupMeta | { error: string }> {
  try {
    const res = await fetch(
      `${apiBase()}/api/auth/invites/lookup?token=${encodeURIComponent(token)}`,
      { cache: "no-store" },
    );
    if (!res.ok) {
      return { error: "invite_invalid" };
    }
    return (await res.json()) as LookupMeta;
  } catch (err) {
    console.error("invite lookup failed", err);
    return { error: "request_failed" };
  }
}

export default async function AcceptInvitePage({
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
          <h1 style={{ fontSize: 22, marginTop: 0 }}>Invalid invite link</h1>
          <p>Ask your agency admin for a new invite.</p>
          <p>
            <Link href="/sign-in">Sign in instead</Link>
          </p>
        </div>
      </main>
    );
  }

  const meta = await lookup(token);
  if ("error" in meta) {
    return (
      <main style={_shell}>
        <div style={_card}>
          <h1 style={{ fontSize: 22, marginTop: 0 }}>
            Invite unavailable
          </h1>
          <p>
            That invite link is invalid, revoked, or expired. Ask your
            agency admin for a new invite.
          </p>
          <p>
            <Link href="/sign-in">Sign in</Link>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main style={_shell}>
      <div style={_card}>
        <h1 style={{ fontSize: 22, marginTop: 0 }}>
          Join {meta.tenant_name}
        </h1>
        <p style={{ color: "#555", fontSize: 14 }}>
          <strong>{meta.inviter_email}</strong> invited you to join{" "}
          <strong>{meta.tenant_name}</strong> as{" "}
          <strong>{meta.role}</strong>. Set a password to activate your
          account.
        </p>
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
          action={acceptInviteAction}
          style={{ display: "flex", flexDirection: "column", gap: 12 }}
        >
          <input type="hidden" name="token" value={token} />
          <label style={_label}>
            <span style={_labelText}>Email</span>
            <input
              type="email"
              value={meta.email}
              readOnly
              style={{ ..._input, background: "#f4f4f5", color: "#52525b" }}
            />
          </label>
          <label style={_label}>
            <span style={_labelText}>Full name</span>
            <input type="text" name="full_name" required style={_input} />
          </label>
          <label style={_label}>
            <span style={_labelText}>Password</span>
            <input
              type="password"
              name="password"
              minLength={12}
              required
              style={_input}
            />
          </label>
          <label style={_label}>
            <span style={_labelText}>Confirm password</span>
            <input
              type="password"
              name="confirm_password"
              minLength={12}
              required
              style={_input}
            />
          </label>
          <button type="submit" style={_button}>
            Accept invite
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
  maxWidth: 440,
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
