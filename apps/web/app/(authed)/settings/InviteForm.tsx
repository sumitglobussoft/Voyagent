"use client";

import { createInviteAction } from "./actions";

export function InviteForm() {
  return (
    <form
      action={createInviteAction}
      style={{
        display: "flex",
        gap: 8,
        alignItems: "flex-end",
        flexWrap: "wrap",
      }}
    >
      <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 240 }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>Email</span>
        <input
          type="email"
          name="email"
          required
          style={{
            padding: "8px 10px",
            border: "1px solid #d4d4d8",
            borderRadius: 6,
            fontSize: 14,
          }}
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>Role</span>
        <select
          name="role"
          defaultValue="agent"
          style={{
            padding: "8px 10px",
            border: "1px solid #d4d4d8",
            borderRadius: 6,
            fontSize: 14,
            background: "#fff",
          }}
        >
          <option value="agent">Agent</option>
          <option value="ticketing_lead">Ticketing lead</option>
          <option value="accounting_lead">Accounting lead</option>
          <option value="viewer">Viewer</option>
          <option value="agency_admin">Agency admin</option>
        </select>
      </label>
      <button
        type="submit"
        style={{
          padding: "8px 16px",
          background: "#18181b",
          color: "#fafafa",
          border: "none",
          borderRadius: 6,
          fontSize: 14,
          cursor: "pointer",
        }}
      >
        Send invite
      </button>
    </form>
  );
}
