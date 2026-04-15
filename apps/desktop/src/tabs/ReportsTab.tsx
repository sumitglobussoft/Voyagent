/**
 * Reports tab — finance aging reports surfaced from the API.
 *
 * Displays receivables (customer invoices) and payables (vendor bills)
 * as side-by-side cards with an aging breakdown (0-30 / 31-60 / 61-90 /
 * 90+) and the top 5 debtors / creditors by amount outstanding.
 *
 * Data source: `GET /api/reports/receivables` and `GET /api/reports/payables`,
 * both scoped to the authenticated tenant via the bearer token. The
 * date range defaults to the first day of the current month through
 * today; changing either date auto-refetches (Refresh button is also
 * provided for manual retry after an error).
 *
 * Intentionally plain tables. No charts — the operators we talked to
 * want to read the numbers, not squint at bars.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactElement,
} from "react";

import { useAuth } from "../auth/AuthProvider.js";
import { apiBaseUrl } from "../sdk.js";

interface Money {
  amount: string;
  currency: string;
}

interface AgingBucket {
  bucket: string;
  count: number;
  amount: Money;
}

interface PartyAmount {
  name: string;
  amount: Money;
}

interface AgingReport {
  tenant_id: string;
  period: { from: string; to: string };
  total_outstanding: Money;
  aging_buckets: AgingBucket[];
  top_debtors: PartyAmount[];
  top_creditors: PartyAmount[];
}

type ReportKind = "receivables" | "payables";

interface LoadState {
  loading: boolean;
  error: string | null;
  data: AgingReport | null;
}

const EMPTY_STATE: LoadState = { loading: false, error: null, data: null };

function firstOfMonth(today: Date): string {
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}-01`;
}

function isoDate(today: Date): string {
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, "0");
  const d = String(today.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function formatMoney(money: Money): string {
  // en-IN formatting is the correct default for our India-first GTM,
  // but currency code comes from the response — mixed-currency tenants
  // still render in their actual currency.
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: money.currency || "INR",
    }).format(Number(money.amount));
  } catch {
    return `${money.currency} ${money.amount}`;
  }
}

function isAllClear(report: AgingReport): boolean {
  // Pydantic's Decimal serializes as a string; "0.00" is the zero case.
  // Also treat numerically-zero variants (e.g. "0", "0.0") as all clear.
  const n = Number(report.total_outstanding.amount);
  return Number.isFinite(n) && n === 0;
}

export function ReportsTab(): ReactElement {
  const { getToken } = useAuth();

  const [fromDate, setFromDate] = useState<string>(() =>
    firstOfMonth(new Date()),
  );
  const [toDate, setToDate] = useState<string>(() => isoDate(new Date()));

  const [receivables, setReceivables] = useState<LoadState>(EMPTY_STATE);
  const [payables, setPayables] = useState<LoadState>(EMPTY_STATE);

  const fetchReport = useCallback(
    async (
      kind: ReportKind,
      from: string,
      to: string,
      setter: (s: LoadState) => void,
    ): Promise<void> => {
      setter({ loading: true, error: null, data: null });
      try {
        const token = await getToken();
        if (!token) {
          setter({
            loading: false,
            error: "Not authenticated.",
            data: null,
          });
          return;
        }
        const url = `${apiBaseUrl}/reports/${kind}?from=${encodeURIComponent(
          from,
        )}&to=${encodeURIComponent(to)}`;
        const res = await fetch(url, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "application/json",
          },
        });
        if (!res.ok) {
          const body = await res.text();
          let detail = `request failed (${res.status})`;
          try {
            const parsed = JSON.parse(body) as { detail?: unknown };
            if (typeof parsed.detail === "string") detail = parsed.detail;
          } catch {
            /* text body */
          }
          setter({ loading: false, error: detail, data: null });
          return;
        }
        const data = (await res.json()) as AgingReport;
        setter({ loading: false, error: null, data });
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Unexpected error";
        setter({ loading: false, error: message, data: null });
      }
    },
    [getToken],
  );

  const refresh = useCallback((): void => {
    void fetchReport("receivables", fromDate, toDate, setReceivables);
    void fetchReport("payables", fromDate, toDate, setPayables);
  }, [fetchReport, fromDate, toDate]);

  // Auto-refetch on mount and whenever the date range changes.
  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div style={{ padding: 24, overflow: "auto", height: "100%" }}>
      <h2 style={{ marginTop: 0, marginBottom: 16 }}>Reports</h2>

      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: 12,
          marginBottom: 20,
          flexWrap: "wrap",
        }}
      >
        <LabeledDate
          label="From"
          value={fromDate}
          onChange={setFromDate}
        />
        <LabeledDate label="To" value={toDate} onChange={setToDate} />
        <button
          type="button"
          onClick={refresh}
          style={{
            padding: "6px 12px",
            borderRadius: 6,
            border: "1px solid #ddd",
            background: "#fafafa",
            color: "#333",
            fontSize: 13,
          }}
        >
          Refresh
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 16,
        }}
      >
        <ReportCard
          title="Receivables"
          partyLabel="Top debtors"
          partyFieldKey="top_debtors"
          state={receivables}
        />
        <ReportCard
          title="Payables"
          partyLabel="Top creditors"
          partyFieldKey="top_creditors"
          state={payables}
        />
      </div>
    </div>
  );
}

interface LabeledDateProps {
  label: string;
  value: string;
  onChange: (next: string) => void;
}

function LabeledDate({ label, value, onChange }: LabeledDateProps): ReactElement {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 12, color: "#555" }}>{label}</span>
      <input
        type="date"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        style={{
          padding: "4px 8px",
          border: "1px solid #ddd",
          borderRadius: 4,
          fontSize: 13,
        }}
      />
    </label>
  );
}

interface ReportCardProps {
  title: string;
  partyLabel: string;
  partyFieldKey: "top_debtors" | "top_creditors";
  state: LoadState;
}

function ReportCard({
  title,
  partyLabel,
  partyFieldKey,
  state,
}: ReportCardProps): ReactElement {
  return (
    <div
      style={{
        border: "1px solid #e5e5e5",
        borderRadius: 8,
        padding: 16,
        background: "#fff",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <h3 style={{ margin: 0, fontSize: 15 }}>{title}</h3>
        {state.data ? (
          <span style={{ fontSize: 16, fontWeight: 600 }}>
            {formatMoney(state.data.total_outstanding)}
          </span>
        ) : null}
      </div>

      {state.loading ? <div style={{ color: "#666" }}>Loading...</div> : null}
      {state.error ? (
        <div style={{ color: "#b00020" }}>Error: {state.error}</div>
      ) : null}
      {state.data ? (
        isAllClear(state.data) ? (
          <div style={{ color: "#2b7a3d", fontSize: 13 }}>
            All clear — nothing outstanding for this period.
          </div>
        ) : (
          <ReportBody
            report={state.data}
            partyLabel={partyLabel}
            partyFieldKey={partyFieldKey}
          />
        )
      ) : null}
    </div>
  );
}

interface ReportBodyProps {
  report: AgingReport;
  partyLabel: string;
  partyFieldKey: "top_debtors" | "top_creditors";
}

function ReportBody({
  report,
  partyLabel,
  partyFieldKey,
}: ReportBodyProps): ReactElement {
  const parties = report[partyFieldKey];
  // Align the bucket rows to the fixed bucket order from the API so the
  // UI stays stable even if the backend reorders them.
  const ordered = useMemo(() => {
    const order = ["0-30", "31-60", "61-90", "90+"];
    const byName = new Map(report.aging_buckets.map((b) => [b.bucket, b]));
    return order.map(
      (name) =>
        byName.get(name) ?? {
          bucket: name,
          count: 0,
          amount: { amount: "0.00", currency: report.total_outstanding.currency },
        },
    );
  }, [report]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 13,
        }}
      >
        <thead>
          <tr style={{ textAlign: "left", color: "#666" }}>
            <th style={{ padding: "4px 6px", fontWeight: 500 }}>Age</th>
            <th style={{ padding: "4px 6px", fontWeight: 500, textAlign: "right" }}>
              Count
            </th>
            <th style={{ padding: "4px 6px", fontWeight: 500, textAlign: "right" }}>
              Amount
            </th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((bucket) => (
            <tr key={bucket.bucket} style={{ borderTop: "1px solid #f0f0f0" }}>
              <td style={{ padding: "4px 6px" }}>{bucket.bucket}</td>
              <td style={{ padding: "4px 6px", textAlign: "right" }}>
                {bucket.count}
              </td>
              <td style={{ padding: "4px 6px", textAlign: "right" }}>
                {formatMoney(bucket.amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div>
        <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
          {partyLabel}
        </div>
        {parties.length === 0 ? (
          <div style={{ color: "#888", fontSize: 13 }}>None.</div>
        ) : (
          <ul
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            {parties.slice(0, 5).map((party, idx) => (
              <li
                key={`${party.name}-${idx}`}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 13,
                  padding: "2px 0",
                }}
              >
                <span>{party.name}</span>
                <span style={{ color: "#333" }}>{formatMoney(party.amount)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
