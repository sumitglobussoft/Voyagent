/**
 * Tenant settings page.
 *
 * Admin-only. Non-admins are redirected to ``/chat?error=forbidden``.
 * Sections: Agency metadata, Members list, Invites (pending + form).
 */
import { redirect } from "next/navigation";

import { apiGet, type InviteListResponse } from "@/lib/api";
import { requireUser } from "@/lib/auth";

import { InviteForm } from "./InviteForm";
import { revokeInviteAction } from "./actions";

export const metadata = { title: "Settings · Voyagent" };

type MembersResponse = {
  items: {
    id: string;
    email: string;
    full_name: string | null;
    role: string;
    created_at: string;
  }[];
};

export default async function SettingsPage({
  searchParams,
}: {
  searchParams?: Promise<{
    status?: string;
    msg?: string;
    invite_link?: string;
  }>;
}) {
  const user = await requireUser();
  if (user.role !== "agency_admin") {
    redirect("/chat?error=forbidden");
  }
  const params = (await searchParams) ?? {};
  const flash = params.msg ?? null;
  const flashOk = params.status === "ok";
  const inviteLink = params.invite_link ?? null;

  const invitesRes = await apiGet<InviteListResponse>(
    "/api/auth/invites?status=pending",
  );
  const invites = invitesRes.ok && invitesRes.data ? invitesRes.data.items : [];

  // Members list: the API surface is an internal helper today. We
  // expose it at ``/api/auth/members`` if it lands; for now fall back
  // to showing only the current user. TODO: wire a real endpoint.
  const membersRes = await apiGet<MembersResponse>("/api/auth/members");
  const members =
    membersRes.ok && membersRes.data
      ? membersRes.data.items
      : [
          {
            id: user.id,
            email: user.email,
            full_name: user.full_name,
            role: user.role,
            created_at: user.created_at,
          },
        ];

  return (
    <main
      style={{
        padding: 32,
        maxWidth: 820,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: 24, marginTop: 0 }}>Agency settings</h1>

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
          {inviteLink ? (
            <div
              style={{
                marginTop: 8,
                padding: "8px 10px",
                background: "#fff",
                border: "1px solid #d4d4d8",
                borderRadius: 6,
                fontFamily:
                  "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: 12,
                wordBreak: "break-all",
              }}
            >
              {inviteLink}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* --- Agency section --- */}
      <section style={_section}>
        <h2 style={_h2}>Agency</h2>
        <dl
          style={{
            display: "grid",
            gridTemplateColumns: "140px 1fr",
            rowGap: 6,
            fontSize: 13,
            margin: 0,
          }}
        >
          <dt style={{ color: "#666" }}>Name</dt>
          <dd style={{ margin: 0 }}>{user.tenant_name}</dd>
          <dt style={{ color: "#666" }}>Tenant ID</dt>
          <dd
            style={{
              margin: 0,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: 12,
            }}
          >
            {user.tenant_id}
          </dd>
        </dl>
        <p style={{ marginTop: 12, fontSize: 12, color: "#888" }}>
          TODO: rename-agency endpoint.
        </p>
      </section>

      {/* --- Members --- */}
      <section style={_section}>
        <h2 style={_h2}>Members ({members.length})</h2>
        <table style={_table}>
          <thead>
            <tr>
              <th style={_th}>Name</th>
              <th style={_th}>Email</th>
              <th style={_th}>Role</th>
              <th style={_th}>Joined</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td style={_td}>{m.full_name ?? "—"}</td>
                <td style={_td}>{m.email}</td>
                <td style={_td}>{m.role}</td>
                <td style={_td}>
                  {new Date(m.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={{ marginTop: 12, fontSize: 12, color: "#888" }}>
          TODO: edit / remove members.
        </p>
      </section>

      {/* --- Invites --- */}
      <section style={_section}>
        <h2 style={_h2}>Pending invites</h2>
        {invites.length === 0 ? (
          <p style={{ color: "#666", fontSize: 14 }}>No pending invites.</p>
        ) : (
          <table style={_table}>
            <thead>
              <tr>
                <th style={_th}>Email</th>
                <th style={_th}>Role</th>
                <th style={_th}>Expires</th>
                <th style={_th}></th>
              </tr>
            </thead>
            <tbody>
              {invites.map((inv) => (
                <tr key={inv.id}>
                  <td style={_td}>{inv.email}</td>
                  <td style={_td}>{inv.role}</td>
                  <td style={_td}>
                    {new Date(inv.expires_at).toLocaleDateString()}
                  </td>
                  <td style={_td}>
                    <form action={revokeInviteAction}>
                      <input type="hidden" name="invite_id" value={inv.id} />
                      <button type="submit" style={_linkBtn}>
                        Revoke
                      </button>
                    </form>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h3 style={{ fontSize: 15, marginTop: 24, marginBottom: 8 }}>
          Invite a teammate
        </h3>
        <InviteForm />
      </section>
    </main>
  );
}

const _section: React.CSSProperties = {
  marginTop: 24,
  padding: 20,
  background: "#fff",
  border: "1px solid #e5e7eb",
  borderRadius: 10,
};

const _h2: React.CSSProperties = {
  fontSize: 18,
  marginTop: 0,
  marginBottom: 12,
};

const _table: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 13,
};

const _th: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 6px",
  borderBottom: "1px solid #e5e7eb",
  color: "#52525b",
  fontWeight: 600,
};

const _td: React.CSSProperties = {
  padding: "8px 6px",
  borderBottom: "1px solid #f4f4f5",
};

const _linkBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#b91c1c",
  cursor: "pointer",
  padding: 0,
  fontSize: 13,
};
