"use client";

/**
 * Client form wrapper for creating an enquiry.
 *
 * Mirrors the sign-in pattern: a client form binds `useFormState` to a
 * server action, letting validation errors re-render inline without a
 * client-side fetch. The action itself runs on the server.
 */
import { useFormState, useFormStatus } from "react-dom";

import { createEnquiryAction, type CreateEnquiryState } from "../actions";

const initialState: CreateEnquiryState = { error: null, values: {} };

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      style={{
        padding: "10px 16px",
        background: "#111",
        color: "#fff",
        border: "none",
        borderRadius: 8,
        fontSize: 15,
        cursor: pending ? "wait" : "pointer",
      }}
    >
      {pending ? "Saving…" : "Create enquiry"}
    </button>
  );
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

const label: React.CSSProperties = { fontSize: 13, fontWeight: 500 };
const hint: React.CSSProperties = { fontSize: 12, color: "#777" };

export function NewEnquiryForm() {
  const [state, formAction] = useFormState(createEnquiryAction, initialState);
  const v = state.values;

  return (
    <form action={formAction} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {state.error ? (
        <div
          role="alert"
          style={{
            padding: "10px 12px",
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#991b1b",
            borderRadius: 8,
            fontSize: 14,
          }}
        >
          {state.error}
        </div>
      ) : null}

      <div style={row}>
        <div style={field}>
          <label htmlFor="customer_name" style={label}>
            Customer name *
          </label>
          <input
            id="customer_name"
            name="customer_name"
            required
            defaultValue={v.customer_name ?? ""}
            style={input}
          />
        </div>
        <div style={field}>
          <label htmlFor="customer_email" style={label}>
            Customer email
          </label>
          <input
            id="customer_email"
            name="customer_email"
            type="email"
            defaultValue={v.customer_email ?? ""}
            style={input}
          />
        </div>
        <div style={field}>
          <label htmlFor="customer_phone" style={label}>
            Customer phone
          </label>
          <input
            id="customer_phone"
            name="customer_phone"
            defaultValue={v.customer_phone ?? ""}
            style={input}
          />
        </div>
      </div>

      <div style={row}>
        <div style={field}>
          <label htmlFor="origin" style={label}>
            Origin
          </label>
          <input
            id="origin"
            name="origin"
            defaultValue={v.origin ?? ""}
            style={input}
          />
        </div>
        <div style={field}>
          <label htmlFor="destination" style={label}>
            Destination
          </label>
          <input
            id="destination"
            name="destination"
            defaultValue={v.destination ?? ""}
            style={input}
          />
        </div>
        <div style={field}>
          <label htmlFor="pax_count" style={label}>
            Pax count *
          </label>
          <input
            id="pax_count"
            name="pax_count"
            type="number"
            min={1}
            required
            defaultValue={v.pax_count ?? "1"}
            style={input}
          />
        </div>
      </div>

      <div style={row}>
        <div style={field}>
          <label htmlFor="depart_date" style={label}>
            Depart date
          </label>
          <input
            id="depart_date"
            name="depart_date"
            type="date"
            defaultValue={v.depart_date ?? ""}
            style={input}
          />
        </div>
        <div style={field}>
          <label htmlFor="return_date" style={label}>
            Return date
          </label>
          <input
            id="return_date"
            name="return_date"
            type="date"
            defaultValue={v.return_date ?? ""}
            style={input}
          />
        </div>
      </div>

      <div style={row}>
        <div style={field}>
          <label htmlFor="budget_amount" style={label}>
            Budget amount
          </label>
          <input
            id="budget_amount"
            name="budget_amount"
            inputMode="decimal"
            placeholder="12500.00"
            defaultValue={v.budget_amount ?? ""}
            style={input}
          />
        </div>
        <div style={field}>
          <label htmlFor="budget_currency" style={label}>
            Currency
          </label>
          <input
            id="budget_currency"
            name="budget_currency"
            maxLength={3}
            placeholder="INR"
            defaultValue={v.budget_currency ?? ""}
            style={input}
          />
          <span style={hint}>ISO code, e.g. INR</span>
        </div>
      </div>

      <div style={field}>
        <label htmlFor="notes" style={label}>
          Notes
        </label>
        <textarea
          id="notes"
          name="notes"
          rows={4}
          defaultValue={v.notes ?? ""}
          style={{ ...input, fontFamily: "inherit" }}
        />
      </div>

      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <SubmitButton />
        <a href="/app/enquiries" style={{ color: "#555", fontSize: 14 }}>
          Cancel
        </a>
      </div>
    </form>
  );
}
