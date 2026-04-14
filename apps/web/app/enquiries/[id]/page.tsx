/**
 * Enquiry detail / edit page.
 *
 * Server component. Everything mutates through server actions in
 * ../actions.ts. Error banners come through `?err=<code>` on the URL
 * (actions redirect with that set on failure); the confirm step for
 * cancel uses `?confirm=1`.
 */
import Link from "next/link";
import { notFound } from "next/navigation";

import { apiGet } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import {
  StatusBadge,
  formatBudget,
  formatDate,
  formatDateTime,
} from "@/lib/formatting";

import {
  cancelEnquiryAction,
  changeStatusAction,
  patchEnquiryAction,
  promoteEnquiryAction,
} from "../actions";

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

const ERROR_MESSAGES: Record<string, string> = {
  invalid_status_transition:
    "That status change isn't allowed from the current state.",
  enquiry_not_found: "That enquiry no longer exists.",
  forbidden_cross_tenant: "You don't have permission to modify this enquiry.",
  invalid_request: "The request was malformed.",
};

function errorMessage(code: string | undefined): string | null {
  if (!code) return null;
  return ERROR_MESSAGES[code] ?? `Request failed (${code}).`;
}

function nextStatusOptions(
  current: Enquiry["status"],
): Enquiry["status"][] {
  // Booked and cancelled are terminal. Otherwise show all statuses the
  // API will accept; the action relies on the server to enforce exact
  // transition rules.
  if (current === "booked" || current === "cancelled") return [current];
  if (current === "new") return ["new", "quoted", "cancelled"];
  if (current === "quoted") return ["quoted", "booked", "cancelled"];
  return [current];
}

const row: React.CSSProperties = {
  display: "flex",
  gap: 12,
  flexWrap: "wrap",
};
const field: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  flex: "1 1 220px",
};
const input: React.CSSProperties = {
  padding: "8px 10px",
  border: "1px solid #d4d4d8",
  borderRadius: 6,
  fontSize: 14,
  background: "#fff",
};
const lbl: React.CSSProperties = { fontSize: 13, fontWeight: 500 };

export default async function EnquiryDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ err?: string; confirm?: string }>;
}) {
  await requireUser();
  const { id } = await params;
  const sp = (await searchParams) ?? {};
  const bannerError = errorMessage(sp.err);
  const confirmingCancel = sp.confirm === "1";

  const res = await apiGet<Enquiry>(`/api/enquiries/${encodeURIComponent(id)}`);
  if (res.status === 404) {
    return (
      <main
        style={{
          maxWidth: 900,
          margin: "0 auto",
          padding: 24,
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <h1 style={{ fontSize: 24 }}>Not found</h1>
        <p>That enquiry doesn't exist or you don't have access to it.</p>
        <p>
          <Link href="/enquiries">← Back to enquiries</Link>
        </p>
      </main>
    );
  }
  if (!res.ok || !res.data) {
    return (
      <main
        style={{
          maxWidth: 900,
          margin: "0 auto",
          padding: 24,
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <h1 style={{ fontSize: 24 }}>Could not load enquiry</h1>
        <p>The API returned status {res.status || "network error"}.</p>
        <p>
          <Link href="/enquiries">← Back to enquiries</Link>
        </p>
      </main>
    );
  }

  const e: Enquiry = res.data;
  if (!e || typeof e.id !== "string") {
    notFound();
  }
  const statusOpts = nextStatusOptions(e.status);
  const terminal = e.status === "booked" || e.status === "cancelled";

  return (
    <main
      style={{
        maxWidth: 900,
        margin: "0 auto",
        padding: 24,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <p style={{ margin: "0 0 4px 0", fontSize: 13 }}>
        <Link href="/enquiries" style={{ color: "#555" }}>
          ← Enquiries
        </Link>
      </p>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <h1 style={{ fontSize: 24, margin: 0 }}>{e.customer_name}</h1>
        <StatusBadge status={e.status} />
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

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 12,
          marginBottom: 20,
          padding: 16,
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: 12,
        }}
      >
        <InfoItem label="Email" value={e.customer_email ?? "—"} />
        <InfoItem label="Phone" value={e.customer_phone ?? "—"} />
        <InfoItem
          label="Route"
          value={`${e.origin ?? "—"} → ${e.destination ?? "—"}`}
        />
        <InfoItem label="Depart" value={formatDate(e.depart_date)} />
        <InfoItem label="Return" value={formatDate(e.return_date)} />
        <InfoItem label="Pax" value={String(e.pax_count)} />
        <InfoItem
          label="Budget"
          value={formatBudget(e.budget_amount, e.budget_currency)}
        />
        <InfoItem label="Created" value={formatDateTime(e.created_at)} />
        <InfoItem label="Updated" value={formatDateTime(e.updated_at)} />
        <InfoItem
          label="Chat session"
          value={e.session_id ? e.session_id : "not promoted"}
        />
      </div>

      {/* Status + promote + cancel controls */}
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: 24,
          padding: 16,
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: 12,
        }}
      >
        {!terminal ? (
          <form
            action={changeStatusAction}
            method="post"
            style={{ display: "flex", gap: 8, alignItems: "center", margin: 0 }}
          >
            <input type="hidden" name="id" value={e.id} />
            <label htmlFor="status" style={lbl}>
              Status
            </label>
            <select
              id="status"
              name="status"
              defaultValue={e.status}
              style={{ ...input, padding: "6px 8px" }}
            >
              {statusOpts.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
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
              Save status
            </button>
          </form>
        ) : (
          <span style={{ fontSize: 13, color: "#666" }}>
            This enquiry is {e.status}; no further transitions are allowed.
          </span>
        )}

        <form action={promoteEnquiryAction} method="post" style={{ margin: 0 }}>
          <input type="hidden" name="id" value={e.id} />
          <button
            type="submit"
            style={{
              background: "#1e3a8a",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              padding: "6px 12px",
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            {e.session_id ? "Open chat session" : "Promote to chat session"}
          </button>
        </form>

        {!terminal ? (
          <form
            action={cancelEnquiryAction}
            method="post"
            style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}
          >
            <input type="hidden" name="id" value={e.id} />
            <input
              type="hidden"
              name="confirm"
              value={confirmingCancel ? "1" : ""}
            />
            <button
              type="submit"
              style={{
                background: confirmingCancel ? "#b91c1c" : "transparent",
                color: confirmingCancel ? "#fff" : "#b91c1c",
                border: "1px solid #b91c1c",
                borderRadius: 6,
                padding: "6px 12px",
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              {confirmingCancel ? "Click again to confirm cancel" : "Cancel enquiry"}
            </button>
          </form>
        ) : null}
      </div>

      <h2 style={{ fontSize: 16, margin: "0 0 8px 0", color: "#444" }}>Edit</h2>
      <form
        action={patchEnquiryAction}
        method="post"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 16,
          padding: 24,
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: 12,
        }}
      >
        <input type="hidden" name="id" value={e.id} />

        <div style={row}>
          <div style={field}>
            <label htmlFor="customer_name" style={lbl}>
              Customer name
            </label>
            <input
              id="customer_name"
              name="customer_name"
              defaultValue={e.customer_name}
              required
              style={input}
            />
          </div>
          <div style={field}>
            <label htmlFor="customer_email" style={lbl}>
              Email
            </label>
            <input
              id="customer_email"
              name="customer_email"
              type="email"
              defaultValue={e.customer_email ?? ""}
              style={input}
            />
          </div>
          <div style={field}>
            <label htmlFor="customer_phone" style={lbl}>
              Phone
            </label>
            <input
              id="customer_phone"
              name="customer_phone"
              defaultValue={e.customer_phone ?? ""}
              style={input}
            />
          </div>
        </div>

        <div style={row}>
          <div style={field}>
            <label htmlFor="origin" style={lbl}>
              Origin
            </label>
            <input
              id="origin"
              name="origin"
              defaultValue={e.origin ?? ""}
              style={input}
            />
          </div>
          <div style={field}>
            <label htmlFor="destination" style={lbl}>
              Destination
            </label>
            <input
              id="destination"
              name="destination"
              defaultValue={e.destination ?? ""}
              style={input}
            />
          </div>
          <div style={field}>
            <label htmlFor="pax_count" style={lbl}>
              Pax count
            </label>
            <input
              id="pax_count"
              name="pax_count"
              type="number"
              min={1}
              defaultValue={e.pax_count}
              style={input}
            />
          </div>
        </div>

        <div style={row}>
          <div style={field}>
            <label htmlFor="depart_date" style={lbl}>
              Depart date
            </label>
            <input
              id="depart_date"
              name="depart_date"
              type="date"
              defaultValue={e.depart_date ?? ""}
              style={input}
            />
          </div>
          <div style={field}>
            <label htmlFor="return_date" style={lbl}>
              Return date
            </label>
            <input
              id="return_date"
              name="return_date"
              type="date"
              defaultValue={e.return_date ?? ""}
              style={input}
            />
          </div>
        </div>

        <div style={row}>
          <div style={field}>
            <label htmlFor="budget_amount" style={lbl}>
              Budget amount
            </label>
            <input
              id="budget_amount"
              name="budget_amount"
              inputMode="decimal"
              defaultValue={e.budget_amount ?? ""}
              style={input}
            />
          </div>
          <div style={field}>
            <label htmlFor="budget_currency" style={lbl}>
              Currency
            </label>
            <input
              id="budget_currency"
              name="budget_currency"
              maxLength={3}
              defaultValue={e.budget_currency ?? ""}
              style={input}
            />
            <span style={{ fontSize: 12, color: "#777" }}>
              ISO code, e.g. INR
            </span>
          </div>
        </div>

        <div style={field}>
          <label htmlFor="notes" style={lbl}>
            Notes
          </label>
          <textarea
            id="notes"
            name="notes"
            rows={4}
            defaultValue={e.notes ?? ""}
            style={{ ...input, fontFamily: "inherit" }}
          />
        </div>

        <div>
          <button
            type="submit"
            style={{
              padding: "10px 16px",
              background: "#111",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              fontSize: 15,
              cursor: "pointer",
            }}
          >
            Save changes
          </button>
        </div>
      </form>
    </main>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: 11,
          color: "#888",
          textTransform: "uppercase",
          letterSpacing: 0.3,
          marginBottom: 2,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 14, color: "#111", wordBreak: "break-word" }}>
        {value}
      </div>
    </div>
  );
}
