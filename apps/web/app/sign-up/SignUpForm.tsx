"use client";

import { useFormState, useFormStatus } from "react-dom";

import { signUpAction, type SignUpState } from "./actions";

const initialState: SignUpState = { error: null };

const inputStyle: React.CSSProperties = {
  padding: "10px 12px",
  border: "1px solid #d4d4d8",
  borderRadius: 8,
  fontSize: 14,
};

const labelStyle: React.CSSProperties = { fontSize: 13, fontWeight: 500 };

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      style={{
        width: "100%",
        padding: "10px 16px",
        background: "#111",
        color: "#fff",
        border: "none",
        borderRadius: 8,
        fontSize: 15,
        cursor: pending ? "wait" : "pointer",
      }}
    >
      {pending ? "Creating account…" : "Create account"}
    </button>
  );
}

export function SignUpForm() {
  const [state, formAction] = useFormState(signUpAction, initialState);

  return (
    <form action={formAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
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

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <label htmlFor="full_name" style={labelStyle}>Full name</label>
        <input id="full_name" name="full_name" type="text" autoComplete="name" required style={inputStyle} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <label htmlFor="email" style={labelStyle}>Work email</label>
        <input id="email" name="email" type="email" autoComplete="email" required style={inputStyle} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <label htmlFor="agency_name" style={labelStyle}>Agency name</label>
        <input id="agency_name" name="agency_name" type="text" autoComplete="organization" required style={inputStyle} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <label htmlFor="password" style={labelStyle}>Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          required
          style={inputStyle}
        />
        <span style={{ fontSize: 12, color: "#777" }}>At least 12 characters.</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <label htmlFor="confirm_password" style={labelStyle}>Confirm password</label>
        <input
          id="confirm_password"
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          required
          style={inputStyle}
        />
      </div>

      <SubmitButton />
    </form>
  );
}
