/**
 * Sign-in / sign-up surface for first launch. Plain email+password form
 * posting to the in-house Voyagent auth API via `VoyagentAuthClient`.
 */
import { useState, type FormEvent, type ReactElement } from "react";

import { useAuth } from "./AuthProvider.js";

type Mode = "sign-in" | "sign-up";

const cardStyle = {
  maxWidth: 360,
  width: "100%",
  padding: 24,
  border: "1px solid #e5e5e5",
  borderRadius: 12,
} as const;

const inputStyle = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid #ddd",
  fontSize: 13,
  boxSizing: "border-box" as const,
  marginBottom: 8,
};

const buttonStyle = {
  width: "100%",
  padding: "10px 16px",
  borderRadius: 6,
  border: "none",
  background: "#111",
  color: "#fff",
  fontSize: 14,
  cursor: "pointer",
} as const;

export function SignInScreen(): ReactElement {
  const { signIn, signUp, isReady } = useAuth();
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [agencyName, setAgencyName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      if (mode === "sign-in") {
        await signIn({ email, password });
      } else {
        await signUp({
          email,
          password,
          full_name: fullName,
          agency_name: agencyName,
        });
      }
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : String(e2));
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
      <div style={cardStyle} role="region" aria-labelledby="signin-title">
        <h1 id="signin-title" style={{ margin: "0 0 16px", fontSize: 18 }}>
          {mode === "sign-in" ? "Sign in to Voyagent" : "Create your Voyagent account"}
        </h1>
        <form
          onSubmit={(e) => {
            void onSubmit(e);
          }}
        >
          {mode === "sign-up" ? (
            <>
              <label style={{ fontSize: 12, color: "#555" }}>Full name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                style={inputStyle}
              />
              <label style={{ fontSize: 12, color: "#555" }}>Agency name</label>
              <input
                type="text"
                value={agencyName}
                onChange={(e) => setAgencyName(e.target.value)}
                required
                style={inputStyle}
              />
            </>
          ) : null}
          <label style={{ fontSize: 12, color: "#555" }}>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            style={inputStyle}
          />
          <label style={{ fontSize: 12, color: "#555" }}>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
            style={{ ...inputStyle, marginBottom: 12 }}
          />
          <button
            type="submit"
            disabled={!isReady || busy}
            aria-busy={busy || undefined}
            style={{ ...buttonStyle, cursor: busy ? "wait" : "pointer" }}
          >
            {busy
              ? "Working..."
              : mode === "sign-in"
                ? "Sign in"
                : "Create account"}
          </button>
        </form>
        <p style={{ marginTop: 12, fontSize: 12, color: "#555", textAlign: "center" }}>
          {mode === "sign-in" ? (
            <>
              No account?{" "}
              <button
                type="button"
                onClick={() => {
                  setMode("sign-up");
                  setErr(null);
                }}
                style={{
                  background: "none",
                  border: "none",
                  color: "#2563eb",
                  cursor: "pointer",
                  padding: 0,
                  fontSize: 12,
                }}
              >
                Create one
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => {
                  setMode("sign-in");
                  setErr(null);
                }}
                style={{
                  background: "none",
                  border: "none",
                  color: "#2563eb",
                  cursor: "pointer",
                  padding: 0,
                  fontSize: 12,
                }}
              >
                Sign in
              </button>
            </>
          )}
        </p>
        {err !== null ? (
          <p role="alert" style={{ color: "#b91c1c", marginTop: 12, fontSize: 12 }}>
            {err}
          </p>
        ) : null}
      </div>
    </div>
  );
}
