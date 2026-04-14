/**
 * First-launch sign-in surface. Deliberately minimal — a single "Sign in"
 * button that opens Clerk's hosted URL in the OS browser. Once the user
 * completes the flow, the deep-link handler captures the session and the
 * shell swaps to the authenticated chrome.
 */
import { useState, type ReactElement } from "react";

import { useAuth } from "./AuthProvider.js";

export function SignInScreen(): ReactElement {
  const { signIn, isReady } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onClick = async (): Promise<void> => {
    setBusy(true);
    setErr(null);
    try {
      await signIn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        height: "100%",
        alignItems: "center",
        justifyContent: "center",
        background: "#ffffff",
      }}
    >
      <div
        style={{
          maxWidth: 360,
          textAlign: "center",
          padding: 24,
          border: "1px solid #e5e5e5",
          borderRadius: 12,
        }}
        role="region"
        aria-labelledby="signin-title"
      >
        <h1 id="signin-title" style={{ margin: "0 0 8px", fontSize: 18 }}>
          Sign in to Voyagent
        </h1>
        <p style={{ color: "#555", margin: "0 0 16px", fontSize: 13 }}>
          We'll open your browser to complete sign-in. When you're done
          you'll be redirected back to the app automatically.
        </p>
        <button
          type="button"
          onClick={() => {
            void onClick();
          }}
          disabled={!isReady || busy}
          aria-busy={busy || undefined}
          style={{
            width: "100%",
            padding: "10px 16px",
            borderRadius: 6,
            border: "none",
            background: "#111",
            color: "#fff",
            fontSize: 14,
            cursor: busy ? "wait" : "pointer",
          }}
        >
          {busy ? "Opening browser..." : "Sign in"}
        </button>
        {err !== null ? (
          <p
            role="alert"
            style={{ color: "#b91c1c", marginTop: 12, fontSize: 12 }}
          >
            {err}
          </p>
        ) : null}
      </div>
    </div>
  );
}
