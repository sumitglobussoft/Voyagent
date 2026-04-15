/**
 * User profile page.
 *
 * Server-rendered. Shows role + tenant as read-only metadata and
 * offers an editable form for ``full_name`` / ``email``. The "change
 * password" action is a plain link to the forgot-password flow so
 * we don't duplicate the reset plumbing.
 */
import Link from "next/link";

import { requireUser } from "@/lib/auth";

import { updateProfileAction } from "./actions";

export const metadata = { title: "Profile · Voyagent" };

export default async function ProfilePage({
  searchParams,
}: {
  searchParams?: Promise<{ status?: string; msg?: string }>;
}) {
  const user = await requireUser();
  const params = (await searchParams) ?? {};
  const flash = params.status === "ok"
    ? (params.msg ?? "Profile updated.")
    : params.status === "err"
    ? (params.msg ?? "Could not update profile.")
    : null;
  const flashOk = params.status === "ok";

  return (
    <main
      style={{
        padding: 32,
        maxWidth: 640,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: 24, marginTop: 0 }}>Your profile</h1>
      <p style={{ color: "#555" }}>
        Update your display name or email address. Role and tenant are
        managed by your agency admin.
      </p>

      {flash ? (
        <div
          style={{
            marginBottom: 16,
            padding: "10px 12px",
            borderRadius: 8,
            background: flashOk ? "#ecfdf5" : "#fef2f2",
            border: `1px solid ${flashOk ? "#a7f3d0" : "#fecaca"}`,
            color: flashOk ? "#065f46" : "#991b1b",
            fontSize: 14,
          }}
        >
          {flash}
        </div>
      ) : null}

      <form
        action={updateProfileAction}
        style={{ display: "flex", flexDirection: "column", gap: 14 }}
      >
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Full name</span>
          <input
            name="full_name"
            defaultValue={user.full_name ?? ""}
            required
            style={_inputStyle}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Email</span>
          <input
            name="email"
            type="email"
            defaultValue={user.email}
            required
            style={_inputStyle}
          />
          <span style={{ fontSize: 12, color: "#666" }}>
            Changing your email will require re-verification.
          </span>
        </label>

        <dl
          style={{
            margin: "8px 0 0 0",
            display: "grid",
            gridTemplateColumns: "140px 1fr",
            rowGap: 6,
            fontSize: 13,
          }}
        >
          <dt style={{ color: "#666" }}>Role</dt>
          <dd style={{ margin: 0 }}>{user.role}</dd>
          <dt style={{ color: "#666" }}>Agency</dt>
          <dd style={{ margin: 0 }}>{user.tenant_name}</dd>
          <dt style={{ color: "#666" }}>Member since</dt>
          <dd style={{ margin: 0 }}>
            {new Date(user.created_at).toLocaleDateString()}
          </dd>
        </dl>

        <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
          <button type="submit" style={_primaryBtn}>
            Save changes
          </button>
          <Link
            href={`/forgot-password?email=${encodeURIComponent(user.email)}`}
            style={_secondaryBtn}
          >
            Change password
          </Link>
        </div>
      </form>
    </main>
  );
}

const _inputStyle: React.CSSProperties = {
  padding: "8px 10px",
  border: "1px solid #d4d4d8",
  borderRadius: 6,
  fontSize: 14,
};

const _primaryBtn: React.CSSProperties = {
  padding: "8px 16px",
  background: "#18181b",
  color: "#fafafa",
  border: "none",
  borderRadius: 6,
  fontSize: 14,
  cursor: "pointer",
};

const _secondaryBtn: React.CSSProperties = {
  padding: "8px 16px",
  background: "#fff",
  color: "#111",
  border: "1px solid #d4d4d8",
  borderRadius: 6,
  fontSize: 14,
  textDecoration: "none",
  display: "inline-block",
};
