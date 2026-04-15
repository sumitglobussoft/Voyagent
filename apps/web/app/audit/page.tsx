/**
 * Audit log viewer.
 *
 * Server component with a filter bar (actor UUID, kind dropdown, date
 * range) and offset pagination. The filter is a plain <form method="get">
 * so submitting just reloads the same URL with updated query params —
 * no client JS. Each row expands inline via <details> to show the raw
 * JSON payload; again, no client JS.
 */
import Link from "next/link";

import { apiGet } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import {
  StatusBadge,
  formatDateTime,
  formatRelative,
  truncate,
} from "@/lib/formatting";

export const metadata = {
  title: "Audit log · Voyagent",
};

type AuditEvent = {
  id: string;
  tenant_id: string;
  actor_kind: string;
  actor_id: string | null;
  actor_email: string | null;
  kind: string;
  summary: string;
  payload: Record<string, unknown>;
  status: "ok" | "error";
  created_at: string;
};

type AuditList = {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
};

const PAGE_SIZE = 50;

// Common kinds we expect to see in the table. "All" leaves the filter
// unset. The server does not constrain ``kind`` to this list — any
// free-form string submitted via the UUID input works too; this is
// just the dropdown's set of quick picks. Seeded from the schema
// + runtime: ``auth.verify`` fires from the auth-failure middleware,
// ``issue_ticket`` / ``hold_fare`` / ``void_ticket`` are canonical
// tool names, ``approval.granted`` / ``approval.rejected`` are
// emitted by the approvals → audit hook. Badge colors for each of
// these live in ``lib/formatting.tsx`` (``BADGE_COLORS``).
const KIND_OPTIONS = [
  "all",
  "auth.verify",
  "issue_ticket",
  "hold_fare",
  "void_ticket",
  "refund_ticket",
  "approval.granted",
  "approval.rejected",
] as const;

function parseOffset(v: string | undefined): number {
  if (!v) return 0;
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

function isUuidish(v: string): boolean {
  // Loose UUID shape — we let the API do the strict parse and return
  // 422, which we then surface as a banner. This is just to avoid
  // sending obvious garbage on every keystroke.
  return /^[0-9a-fA-F-]{8,}$/.test(v);
}

export default async function AuditPage({
  searchParams,
}: {
  searchParams?: Promise<{
    actor_id?: string;
    kind?: string;
    from?: string;
    to?: string;
    offset?: string;
  }>;
}) {
  await requireUser();
  const params = (await searchParams) ?? {};

  const actorId = (params.actor_id ?? "").trim();
  const kind =
    params.kind && KIND_OPTIONS.includes(params.kind as (typeof KIND_OPTIONS)[number])
      ? params.kind
      : "all";
  const fromDate = (params.from ?? "").trim();
  const toDate = (params.to ?? "").trim();
  const offset = parseOffset(params.offset);

  const qs = new URLSearchParams();
  qs.set("limit", String(PAGE_SIZE));
  qs.set("offset", String(offset));
  if (actorId && isUuidish(actorId)) qs.set("actor_id", actorId);
  if (kind !== "all") qs.set("kind", kind);
  if (fromDate) qs.set("from", fromDate);
  if (toDate) qs.set("to", toDate);

  const res = await apiGet<AuditList>(`/api/audit?${qs.toString()}`);
  const items = res.ok && res.data ? res.data.items : [];
  const total = res.ok && res.data ? res.data.total : 0;
  const fetchFailed = !res.ok;

  const prevOffset = Math.max(0, offset - PAGE_SIZE);
  const nextOffset = offset + PAGE_SIZE;
  const hasPrev = offset > 0;
  const hasNext = nextOffset < total;

  const buildHref = (o: number): string => {
    const u = new URLSearchParams();
    if (actorId) u.set("actor_id", actorId);
    if (kind !== "all") u.set("kind", kind);
    if (fromDate) u.set("from", fromDate);
    if (toDate) u.set("to", toDate);
    u.set("offset", String(o));
    const s = u.toString();
    return s ? `/audit?${s}` : "/audit";
  };

  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = Math.min(offset + items.length, total);

  return (
    <main
      style={{
        maxWidth: 1200,
        margin: "0 auto",
        padding: 24,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <h1 style={{ fontSize: 24, margin: 0 }}>Audit log</h1>
        <span style={{ color: "#666", fontSize: 14 }}>{total} events</span>
      </div>

      <form
        method="get"
        action="/app/audit"
        style={{
          display: "flex",
          gap: 8,
          marginBottom: 16,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <label htmlFor="actor_id" style={{ fontSize: 13, color: "#555" }}>
          Actor
        </label>
        <input
          id="actor_id"
          name="actor_id"
          type="text"
          defaultValue={actorId}
          placeholder="user UUID"
          style={{
            padding: "6px 10px",
            border: "1px solid #d4d4d8",
            borderRadius: 6,
            fontSize: 14,
            minWidth: 260,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          }}
        />
        <label htmlFor="kind" style={{ fontSize: 13, color: "#555" }}>
          Kind
        </label>
        <select
          id="kind"
          name="kind"
          defaultValue={kind}
          style={{
            padding: "6px 8px",
            border: "1px solid #d4d4d8",
            borderRadius: 6,
            fontSize: 14,
            background: "#fff",
          }}
        >
          {KIND_OPTIONS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <label htmlFor="from" style={{ fontSize: 13, color: "#555" }}>
          From
        </label>
        <input
          id="from"
          name="from"
          type="date"
          defaultValue={fromDate}
          style={{
            padding: "6px 8px",
            border: "1px solid #d4d4d8",
            borderRadius: 6,
            fontSize: 14,
          }}
        />
        <label htmlFor="to" style={{ fontSize: 13, color: "#555" }}>
          To
        </label>
        <input
          id="to"
          name="to"
          type="date"
          defaultValue={toDate}
          style={{
            padding: "6px 8px",
            border: "1px solid #d4d4d8",
            borderRadius: 6,
            fontSize: 14,
          }}
        />
        <button
          type="submit"
          style={{
            background: "#f3f4f6",
            border: "1px solid #d4d4d8",
            borderRadius: 6,
            padding: "6px 12px",
            fontSize: 14,
            cursor: "pointer",
          }}
        >
          Apply
        </button>
        {actorId || kind !== "all" || fromDate || toDate ? (
          <Link
            href="/audit"
            style={{
              fontSize: 13,
              color: "#555",
              textDecoration: "none",
              marginLeft: 4,
            }}
          >
            Clear
          </Link>
        ) : null}
      </form>

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
          Could not load audit log ({res.status || "network error"}).
        </div>
      ) : null}

      <div
        style={{
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          overflow: "hidden",
          background: "#fff",
        }}
      >
        {items.length === 0 ? (
          <div
            style={{
              padding: 24,
              textAlign: "center",
              color: "#666",
              fontSize: 14,
            }}
          >
            No audit events match the current filter.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ background: "#f9fafb", textAlign: "left" }}>
                <Th>When</Th>
                <Th>Kind</Th>
                <Th>Actor</Th>
                <Th>Summary</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <AuditRow key={e.id} event={e} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 12,
          fontSize: 13,
          color: "#555",
        }}
      >
        <span>
          Showing {shownFrom}–{shownTo} of {total}
        </span>
        <span style={{ display: "flex", gap: 12 }}>
          {hasPrev ? (
            <Link href={buildHref(prevOffset)}>← Prev</Link>
          ) : (
            <span style={{ color: "#bbb" }}>← Prev</span>
          )}
          {hasNext ? (
            <Link href={buildHref(nextOffset)}>Next →</Link>
          ) : (
            <span style={{ color: "#bbb" }}>Next →</span>
          )}
        </span>
      </div>
    </main>
  );
}

function AuditRow({ event }: { event: AuditEvent }) {
  const dot =
    event.status === "error" ? (
      <span
        title="error"
        style={{
          display: "inline-block",
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: "#dc2626",
          marginRight: 6,
          verticalAlign: "middle",
        }}
      />
    ) : (
      <span
        title="ok"
        style={{
          display: "inline-block",
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: "#16a34a",
          marginRight: 6,
          verticalAlign: "middle",
        }}
      />
    );

  const actorLabel = event.actor_email
    ? event.actor_email
    : event.actor_id
      ? truncate(event.actor_id, 10)
      : event.actor_kind;

  return (
    <>
      <tr style={{ borderTop: "1px solid #f1f5f9" }}>
        <Td>
          <span title={formatDateTime(event.created_at)}>
            {formatRelative(event.created_at)}
          </span>
        </Td>
        <Td>
          <StatusBadge status={event.kind} />
        </Td>
        <Td>
          {event.actor_email ? (
            <span style={{ color: "#111" }}>{actorLabel}</span>
          ) : (
            <code
              title={event.actor_id ?? event.actor_kind}
              style={{ fontSize: 12, color: "#555" }}
            >
              {actorLabel}
            </code>
          )}
        </Td>
        <Td>
          <details>
            <summary
              style={{
                cursor: "pointer",
                color: "#111",
                listStyle: "revert",
              }}
            >
              {event.summary}
            </summary>
            <pre
              style={{
                marginTop: 8,
                padding: 10,
                background: "#f8fafc",
                border: "1px solid #e5e7eb",
                borderRadius: 6,
                fontSize: 12,
                lineHeight: 1.4,
                overflowX: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </details>
        </Td>
        <Td>
          {dot}
          <span style={{ fontSize: 12, color: "#555", verticalAlign: "middle" }}>
            {event.status}
          </span>
        </Td>
      </tr>
    </>
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
    <td style={{ padding: "10px 12px", verticalAlign: "top" }}>{children}</td>
  );
}
