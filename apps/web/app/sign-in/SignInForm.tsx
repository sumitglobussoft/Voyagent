"use client";

/**
 * Client form wrapper for sign-in.
 *
 * Uses `useFormState` so server-action errors (e.g. invalid_credentials)
 * render inline without a client-side fetch. The action itself still does
 * all the work server-side; this component is just the binding layer.
 */
import { useFormState, useFormStatus } from "react-dom";

import { signInAction, type SignInState } from "./actions";

const initialState: SignInState = { error: null };

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
      {pending ? "Signing in…" : "Sign in"}
    </button>
  );
}

export function SignInForm({
  next,
  defaultEmail = "",
  defaultPassword = "",
}: {
  next: string;
  defaultEmail?: string;
  defaultPassword?: string;
}) {
  const [state, formAction] = useFormState(signInAction, initialState);

  return (
    <form action={formAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <input type="hidden" name="next" value={next} />

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
        <label htmlFor="email" style={{ fontSize: 13, fontWeight: 500 }}>
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          defaultValue={defaultEmail}
          required
          style={{
            padding: "10px 12px",
            border: "1px solid #d4d4d8",
            borderRadius: 8,
            fontSize: 14,
          }}
        />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <label htmlFor="password" style={{ fontSize: 13, fontWeight: 500 }}>
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          defaultValue={defaultPassword}
          required
          style={{
            padding: "10px 12px",
            border: "1px solid #d4d4d8",
            borderRadius: 8,
            fontSize: 14,
          }}
        />
      </div>

      <SubmitButton />
    </form>
  );
}
