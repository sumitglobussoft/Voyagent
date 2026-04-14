/**
 * Approvals inbox.
 *
 * Server component. Renders the full pending queue plus a recent-history
 * tail. All resolve interactions go through the server action in
 * ./actions.ts; this page stays pure server-render.
 */
import { apiGet } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import {
  StatusBadge,
  formatDateTime,
  formatRelative,
  isPast,
  truncate,
} from "@/lib/formatting";

import { resolveApprovalAction } from "./actions";

export const metadata = {
  title: "Approvals · Voyagent",
};

type Approval = {
  id: string;
  session_id: string;
  tool_name: string;
  summary: string;
  requested_at: string;
  expires_at: string;
  status: "pending" | "granted" | "rejected" | "expired";
  payload: Record<string, unknown>;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
};

type ApprovalList = {
  items: Approval[];
  total: number;
  limit: number;
  offset: number;
};

const ERROR_MESSAGES: Record<string, string> = {
  approval_already_resolved: "That approval was already resolved by someone else.",
  approval_not_found: "That approval no longer exists.",
  forbidden_cross_tenant: "You don't have permission to resolve that approval.",
  invalid_request: "The resolve request was malformed.",
};

function errorMessage(code: string | undefined): string | null {
  if (!code) return null;
  return ERROR_MESSAGES[code] ?? `Could not resolve approval (${code}).`;
}

export default async function ApprovalsPage({
  searchParams,
}: {
  searchParams?: Promise<{ err?: string }>;
}) {
  await requireUser();
  const params = (await searchParams) ?? {};
  const bannerError = errorMessage(params.err);

  const [pendingRes, recentRes] = await Promise.all([
    apiGet<ApprovalList>("/api/approvals?status=pending&limit=50&offset=0"),
    apiGet<ApprovalList>("/api/approvals?limit=20&offset=0"),
  ]);

  const pending = pendingRes.ok && pendingRes.data ? pendingRes.data.items : [];
  const pendingTotal = pendingRes.ok && pendingRes.data ? pendingRes.data.total : 0;
  const recentAll = recentRes.ok && recentRes.data ? recentRes.data.items : [];
  const recentNonPending = recentAll
    .filter((a) => a.status !== "pending")
    .slice(0, 20);

  const fetchFailed = !pendingRes.ok;

  return (
    <main
      style={{
        maxWidth: 1200,
        margin: "0 auto",
        padding: "24px",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 16,
        }}
      >
        <h1 style={{ fontSize: 24, margin: 0 }}>Approvals</h1>
        <span style={{ color: "#666", fontSize: 14 }}>
          {pendingTotal} pending
        </span>
      </div>

      {bannerError ? (
        <div
          role="alert"
          style={{
            padding: "10px 12px",
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#991b1b",
            borderRadius: 8,
            fontSize: 14,
            marginBottom: 16,
          }}
        >
          {bannerError}
        </div>
      ) : null}

      {fetchFailed ? (
        <div
          role="alert"
          style={{
            padding: "10px 12px",
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#991b1b",
            borderRadius: 8,
            fontSize: 14,
            marginBottom: 16,
          }}
        >
          Could not load approvals ({pendingRes.status || "network error"}).
        </div>
      ) : null}

      <section style={{ marginBottom: 40 }}>
        <h2 style={{ fontSize: 16, marginBottom: 8, color: "#444" }}>Pending</h2>
        <ApprovalTable items={pending} showActions />
      </section>

      <section>
        <h2 style={{ fontSize: 16, marginBottom: 8, color: "#444" }}>Recently resolved</h2>
        <ApprovalTable items={recentNonPending} showActions={false} />
      </section>
    </main>
  );
}

function ApprovalTable({
  items,
  showActions,
}: {
  items: Approval[];
  showActions: boolean;
}) {
  if (items.length === 0) {
    return (
      <div
        style={{
          padding: 24,
          textAlign: "center",
          border: "1px dashed #d4d4d8",
          borderRadius: 8,
          color: "#666",
          fontSize: 14,
          background: "#fff",
        }}
      >
        Nothing here.
      </div>
    );
  }

  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        overflow: "hidden",
        background: "#fff",
      }}
    >
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 14,
        }}
      >
        <thead>
          <tr style={{ background: "#f9fafb", textAlign: "left" }}>
            <Th>Tool</Th>
            <Th>Session</Th>
            <Th>Summary</Th>
            <Th>Requested</Th>
            <Th>Expires</Th>
            <Th>Status</Th>
            {showActions ? <Th>Actions</Th> : null}
          </tr>
        </thead>
        <tbody>
          {items.map((a) => {
            const expired = a.status === "pending" && isPast(a.expires_at);
            return (
              <tr key={a.id} style={{ borderTop: "1px solid #f1f5f9" }}>
                <Td>
                  <code style={{ fontSize: 13 }}>{a.tool_name}</code>
                </Td>
                <Td>
                  <code
                    title={a.session_id}
                    style={{ fontSize: 12, color: "#555" }}
                  >
                    {truncate(a.session_id, 10)}
                  </code>
                </Td>
                <Td>
                  <span style={{ color: "#111" }}>{a.summary}</span>
                </Td>
                <Td>
                  <span title={formatDateTime(a.requested_at)}>
                    {formatRelative(a.requested_at)}
                  </span>
                </Td>
                <Td>
                  <span title={formatDateTime(a.expires_at)}>
                    {expired ? "expired" : formatRelative(a.expires_at)}
                  </span>
                </Td>
                <Td>
                  <StatusBadge status={expired ? "expired" : a.status} />
                </Td>
                {showActions ? (
                  <Td>
                    {a.status === "pending" && !expired ? (
                      <div style={{ display: "flex", gap: 8 }}>
                        <ResolveButton id={a.id} granted label="Approve" />
                        <ResolveButton id={a.id} granted={false} label="Reject" />
                      </div>
                    ) : (
                      <span style={{ color: "#999", fontSize: 13 }}>—</span>
                    )}
                  </Td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ResolveButton({
  id,
  granted,
  label,
}: {
  id: string;
  granted: boolean;
  label: string;
}) {
  const bg = granted ? "#065f46" : "#b91c1c";
  return (
    <form action={resolveApprovalAction} method="post" style={{ margin: 0 }}>
      <input type="hidden" name="id" value={id} />
      <input type="hidden" name="granted" value={granted ? "true" : "false"} />
      <button
        type="submit"
        style={{
          background: bg,
          color: "#fff",
          border: "none",
          borderRadius: 6,
          padding: "4px 10px",
          fontSize: 13,
          cursor: "pointer",
        }}
      >
        {label}
      </button>
    </form>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        padding: "10px 12px",
        fontWeight: 600,
        fontSize: 12,
        color: "#555",
        textTransform: "uppercase",
        letterSpacing: 0.3,
      }}
    >
      {children}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return (
    <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>{children}</td>
  );
}
