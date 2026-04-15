/**
 * Enquiries list page.
 *
 * Server component with a status filter, keyword search, and basic
 * offset pagination. The filter bar is a plain <form method="get"> so
 * submitting just reloads the same URL with updated query params —
 * no client JS.
 */
import Link from "next/link";

import { apiGet } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import {
  StatusBadge,
  formatBudget,
  formatDate,
  formatDateTime,
} from "@/lib/formatting";

export const metadata = {
  title: "Enquiries · Voyagent",
};

type Enquiry = {
  id: string;
  tenant_id: string;
  created_by_user_id: string;
  customer_name: string;
  customer_email: string | null;
  customer_phone: string | null;
  origin: string | null;
  destination: string | null;
  depart_date: string | null;
  return_date: string | null;
  pax_count: number;
  budget_amount: string | null;
  budget_currency: string | null;
  status: "new" | "quoted" | "booked" | "cancelled";
  notes: string | null;
  session_id: string | null;
  created_at: string;
  updated_at: string;
};

type EnquiryList = {
  items: Enquiry[];
  total: number;
  limit: number;
  offset: number;
};

const PAGE_SIZE = 50;
const STATUS_OPTIONS = ["all", "new", "quoted", "booked", "cancelled"] as const;

function parseOffset(v: string | undefined): number {
  if (!v) return 0;
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

export default async function EnquiriesPage({
  searchParams,
}: {
  searchParams?: Promise<{ status?: string; q?: string; offset?: string }>;
}) {
  await requireUser();
  const params = (await searchParams) ?? {};
  const status = params.status && STATUS_OPTIONS.includes(params.status as (typeof STATUS_OPTIONS)[number])
    ? params.status
    : "all";
  const q = (params.q ?? "").trim();
  const offset = parseOffset(params.offset);

  const qs = new URLSearchParams();
  qs.set("limit", String(PAGE_SIZE));
  qs.set("offset", String(offset));
  if (status !== "all") qs.set("status", status);
  if (q) qs.set("q", q);

  const res = await apiGet<EnquiryList>(`/api/enquiries?${qs.toString()}`);
  const items = res.ok && res.data ? res.data.items : [];
  const total = res.ok && res.data ? res.data.total : 0;
  const fetchFailed = !res.ok;

  const prevOffset = Math.max(0, offset - PAGE_SIZE);
  const nextOffset = offset + PAGE_SIZE;
  const hasPrev = offset > 0;
  const hasNext = nextOffset < total;

  const buildHref = (o: number): string => {
    const u = new URLSearchParams();
    if (status !== "all") u.set("status", status);
    if (q) u.set("q", q);
    u.set("offset", String(o));
    const s = u.toString();
    return s ? `/enquiries?${s}` : "/enquiries";
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
        <h1 style={{ fontSize: 24, margin: 0 }}>Enquiries</h1>
        <Link
          href="/enquiries/new"
          style={{
            background: "#111",
            color: "#fff",
            textDecoration: "none",
            padding: "8px 14px",
            borderRadius: 8,
            fontSize: 14,
          }}
        >
          New enquiry
        </Link>
      </div>

      {/*
       * Responsive filter bar.
       *
       * Below sm: (640px) everything stacks into a column so on a
       * Pixel 5 (393px) the search input can't overflow across the
       * Apply button and swallow clicks. Each control is full-width
       * on mobile; Apply stays full-width on mobile, auto on desktop.
       * At sm and up the original horizontal row is restored.
       */}
      <form
        method="get"
        action="/app/enquiries"
        className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center"
      >
        <label
          htmlFor="status"
          className="text-[13px] text-neutral-600 sm:mr-1"
        >
          Status
        </label>
        <select
          id="status"
          name="status"
          defaultValue={status}
          className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm sm:w-auto"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label
          htmlFor="q"
          className="text-[13px] text-neutral-600 sm:mr-1"
        >
          Search
        </label>
        <input
          id="q"
          name="q"
          type="search"
          defaultValue={q}
          placeholder="name, destination…"
          className="w-full rounded-md border border-neutral-300 px-2.5 py-1.5 text-sm sm:w-auto sm:min-w-[220px]"
        />
        <button
          type="submit"
          className="w-full cursor-pointer rounded-md border border-neutral-300 bg-neutral-100 px-3 py-1.5 text-sm sm:w-auto"
        >
          Apply
        </button>
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
          Could not load enquiries ({res.status || "network error"}).
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
            No enquiries match the current filter.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ background: "#f9fafb", textAlign: "left" }}>
                <Th>Customer</Th>
                <Th>Route</Th>
                <Th>Depart</Th>
                <Th>Pax</Th>
                <Th>Budget</Th>
                <Th>Status</Th>
                <Th>Created</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr
                  key={e.id}
                  style={{ borderTop: "1px solid #f1f5f9" }}
                >
                  <Td>
                    <Link
                      href={`/enquiries/${e.id}`}
                      style={{ color: "#111", fontWeight: 500, textDecoration: "none" }}
                    >
                      {e.customer_name}
                    </Link>
                  </Td>
                  <Td>
                    <span style={{ color: "#444" }}>
                      {(e.origin ?? "—")} → {(e.destination ?? "—")}
                    </span>
                  </Td>
                  <Td>{formatDate(e.depart_date)}</Td>
                  <Td>{e.pax_count}</Td>
                  <Td>{formatBudget(e.budget_amount, e.budget_currency)}</Td>
                  <Td>
                    <StatusBadge status={e.status} />
                  </Td>
                  <Td>
                    <span title={formatDateTime(e.created_at)}>
                      {formatDate(e.created_at)}
                    </span>
                  </Td>
                </tr>
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
