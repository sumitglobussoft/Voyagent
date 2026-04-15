/**
 * Sidebar user card.
 *
 * Shows an initials avatar, the user's name, the tenant name, a
 * coloured role badge and a sign-out button. Fully server-rendered —
 * the sign-out button is a plain HTML form that posts to the existing
 * ``/app/sign-out`` route handler.
 *
 * Note: ``form action="/app/sign-out"`` keeps the ``/app`` basePath
 * prefix explicitly — HTML form actions do NOT pass through Next's
 * automatic basePath prepending, unlike ``<Link href>``.
 */
import type { ReactElement } from "react";

import { LogOut } from "@voyagent/icons";

import type { PublicUser } from "@/lib/auth";

function initials(user: PublicUser): string {
  const source = (user.full_name ?? user.email ?? "").trim();
  if (!source) return "?";
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  if (parts.length === 0) return source.slice(0, 2).toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const ROLE_COLORS: Record<string, { bg: string; fg: string; border: string }> = {
  owner: { bg: "#ede9fe", fg: "#5b21b6", border: "#ddd6fe" },
  admin: { bg: "#dbeafe", fg: "#1e40af", border: "#bfdbfe" },
  agent: { bg: "#dcfce7", fg: "#166534", border: "#bbf7d0" },
  viewer: { bg: "#f3f4f6", fg: "#374151", border: "#e5e7eb" },
};

function roleColors(role: string): { bg: string; fg: string; border: string } {
  return ROLE_COLORS[role.toLowerCase()] ?? ROLE_COLORS.viewer;
}

export function UserCard({ user }: { user: PublicUser }): ReactElement {
  const ini = initials(user);
  const name = user.full_name ?? user.email;
  const rc = roleColors(user.role);

  return (
    <div
      style={{
        borderTop: "1px solid #e5e7eb",
        padding: "12px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        background: "#f4f4f5",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <div
          aria-hidden
          style={{
            flex: "0 0 auto",
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "#27272a",
            color: "#fafafa",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: 0.5,
          }}
        >
          {ini}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            title={name}
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "#18181b",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {name}
          </div>
          <div
            title={user.tenant_name}
            style={{
              fontSize: 12,
              color: "#71717a",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {user.tenant_name}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span
          style={{
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: 999,
            background: rc.bg,
            color: rc.fg,
            border: `1px solid ${rc.border}`,
            fontSize: 11,
            fontWeight: 500,
            textTransform: "capitalize",
            whiteSpace: "nowrap",
          }}
        >
          {user.role}
        </span>
        {/* Form action keeps the /app basePath explicitly — HTML form
            actions are not auto-prefixed. */}
        <form action="/app/sign-out" method="post" style={{ margin: 0 }}>
          <button
            type="submit"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              background: "transparent",
              border: "1px solid #d4d4d8",
              borderRadius: 6,
              padding: "4px 10px",
              cursor: "pointer",
              fontSize: 12,
              color: "#3f3f46",
            }}
          >
            <LogOut size={12} />
            Sign out
          </button>
        </form>
      </div>
    </div>
  );
}

export default UserCard;
