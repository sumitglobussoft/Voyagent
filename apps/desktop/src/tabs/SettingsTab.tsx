/**
 * Settings tab — account, session, about, diagnostics.
 *
 * Account fields are read-only: there's no `/api/auth/profile` PATCH
 * endpoint yet. When that ships we'll add an Edit affordance; until
 * then this surface exists to confirm identity + sign out.
 *
 * Session row shows relative JWT expiry by decoding the access token's
 * `exp` claim client-side. That decode is duplicated (tiny) from the
 * private helper in `VoyagentAuthClient` because the helper is not
 * exported; see the report for the call-site.
 */
import {
  useCallback,
  useEffect,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

import { VoyagentClient } from "@voyagent/sdk";

import { useAuth } from "../auth/AuthProvider.js";
import { apiBaseUrl, apiUrl, useVoyagentClient } from "../sdk.js";

const APP_VERSION: string =
  typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "0.0.0-dev";
const BUILD_DATE: string =
  typeof __BUILD_DATE__ === "string" ? __BUILD_DATE__ : "—";

// Public repo / changelog links. If these change the constants below
// are the single place to edit them.
const REPO_URL = "https://github.com/anthropics/gbs-agentic-travel";
const CHANGELOG_URL = `${REPO_URL}/blob/main/CHANGELOG.md`;

interface MeResponse {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tenant_id: string;
  tenant_name: string;
  created_at: string;
}

/**
 * Decode the `exp` claim (ms since epoch) from a JWT access token.
 * Returns 0 on any parse failure so callers can treat it as "expired".
 * Mirrors the private `jwtExpMs` helper inside `VoyagentAuthClient`.
 */
function jwtExpMs(token: string): number {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return 0;
    const payloadB64 = parts[1]!.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(payloadB64);
    const payload = JSON.parse(json) as { exp?: number };
    if (typeof payload.exp !== "number") return 0;
    return payload.exp * 1000;
  } catch {
    return 0;
  }
}

function formatRelativeFromNow(targetMs: number): string {
  if (targetMs <= 0) return "unknown";
  const deltaMs = targetMs - Date.now();
  const absMin = Math.round(Math.abs(deltaMs) / 60_000);
  if (deltaMs <= 0) return `expired ${absMin} min ago`;
  if (absMin < 60) return `expires in ${absMin} min`;
  const hours = Math.floor(absMin / 60);
  const remMin = absMin % 60;
  if (hours < 24) return `expires in ${hours}h ${remMin}m`;
  const days = Math.floor(hours / 24);
  return `expires in ${days}d`;
}

export function SettingsTab(): ReactElement {
  const { user, signOut, getToken } = useAuth();
  const client = useVoyagentClient();

  const [me, setMe] = useState<MeResponse | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [meLoading, setMeLoading] = useState<boolean>(true);

  const [tokenExpMs, setTokenExpMs] = useState<number>(0);
  // Re-render every 30 s so the relative expiry text stays fresh.
  const [, setNowTick] = useState<number>(0);

  const refreshTokenExpiry = useCallback(async (): Promise<void> => {
    const token = await getToken();
    setTokenExpMs(token ? jwtExpMs(token) : 0);
  }, [getToken]);

  const loadMe = useCallback(async (): Promise<void> => {
    setMeLoading(true);
    setMeError(null);
    try {
      const token = await getToken();
      if (!token) {
        setMeError("Not authenticated.");
        setMeLoading(false);
        return;
      }
      const res = await fetch(`${apiBaseUrl}/auth/me`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
      });
      if (!res.ok) {
        setMeError(`Failed to load profile (${res.status}).`);
        setMeLoading(false);
        return;
      }
      const data = (await res.json()) as MeResponse;
      setMe(data);
    } catch (err) {
      setMeError(err instanceof Error ? err.message : "Unexpected error.");
    } finally {
      setMeLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    void loadMe();
    void refreshTokenExpiry();
  }, [loadMe, refreshTokenExpiry]);

  useEffect(() => {
    const id = window.setInterval(() => {
      setNowTick((n) => n + 1);
    }, 30_000);
    return () => {
      window.clearInterval(id);
    };
  }, []);

  return (
    <div style={{ padding: 24, overflow: "auto", height: "100%" }}>
      <h2 style={{ marginTop: 0, marginBottom: 16 }}>Settings</h2>

      <AccountSection
        user={user}
        me={me}
        error={meError}
        loading={meLoading}
      />

      <SessionSection
        email={user?.email ?? null}
        tokenExpMs={tokenExpMs}
        onSignOut={() => {
          void signOut();
        }}
        onRefresh={() => {
          void refreshTokenExpiry();
        }}
      />

      <AboutSection />

      <DiagnosticsSection client={client} />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Account                                                                     //
// --------------------------------------------------------------------------- //

interface AccountSectionProps {
  user: ReturnType<typeof useAuth>["user"];
  me: MeResponse | null;
  error: string | null;
  loading: boolean;
}

function AccountSection({
  user,
  me,
  error,
  loading,
}: AccountSectionProps): ReactElement {
  const fullName = me?.full_name ?? user?.fullName ?? "—";
  const email = me?.email ?? user?.email ?? "—";
  const role = me?.role ?? user?.role ?? "—";
  const tenantName = me?.tenant_name ?? user?.tenantName ?? "—";
  const tenantId = me?.tenant_id ?? user?.tenantId ?? "—";
  const createdAt = me?.created_at
    ? new Date(me.created_at).toLocaleString()
    : "—";

  return (
    <Section title="Account">
      {loading ? (
        <div style={{ color: "#666" }}>Loading...</div>
      ) : null}
      {error ? <div style={{ color: "#b00020" }}>Error: {error}</div> : null}
      <Row label="Full name" value={fullName} />
      <Row label="Email" value={email} />
      <Row label="Role" value={role} />
      <Row label="Tenant" value={tenantName} />
      <Row
        label="Tenant id"
        value={
          <code style={{ fontSize: 12, fontFamily: "ui-monospace, monospace" }}>
            {tenantId}
          </code>
        }
      />
      <Row label="Account created" value={createdAt} />
    </Section>
  );
}

// --------------------------------------------------------------------------- //
// Session                                                                     //
// --------------------------------------------------------------------------- //

interface SessionSectionProps {
  email: string | null;
  tokenExpMs: number;
  onSignOut: () => void;
  onRefresh: () => void;
}

function SessionSection({
  email,
  tokenExpMs,
  onSignOut,
  onRefresh,
}: SessionSectionProps): ReactElement {
  return (
    <Section title="Session">
      <Row label="Signed in as" value={email ?? "—"} />
      <Row label="Access token" value={formatRelativeFromNow(tokenExpMs)} />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <SecondaryButton onClick={onRefresh}>Refresh now</SecondaryButton>
        <SecondaryButton onClick={onSignOut}>Sign out</SecondaryButton>
      </div>
    </Section>
  );
}

// --------------------------------------------------------------------------- //
// About                                                                       //
// --------------------------------------------------------------------------- //

function AboutSection(): ReactElement {
  return (
    <Section title="About">
      <Row label="App version" value={APP_VERSION} />
      <Row label="API endpoint" value={apiUrl} />
      <Row label="Build date" value={BUILD_DATE} />
      <Row
        label="Repository"
        value={
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            {REPO_URL}
          </a>
        }
      />
      <Row
        label="Changelog"
        value={
          <a href={CHANGELOG_URL} target="_blank" rel="noreferrer">
            {CHANGELOG_URL}
          </a>
        }
      />
    </Section>
  );
}

// --------------------------------------------------------------------------- //
// Diagnostics                                                                 //
// --------------------------------------------------------------------------- //

interface DiagnosticsSectionProps {
  client: VoyagentClient;
}

type HealthState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

function DiagnosticsSection({
  client,
}: DiagnosticsSectionProps): ReactElement {
  const [open, setOpen] = useState<boolean>(false);
  const [health, setHealth] = useState<HealthState>({ kind: "idle" });

  const runHealth = useCallback(async (): Promise<void> => {
    setHealth({ kind: "loading" });
    try {
      const result = await client.health();
      if (result.status === "ok") {
        setHealth({ kind: "ok" });
      } else {
        setHealth({ kind: "error", message: "Unexpected response." });
      }
    } catch (err) {
      setHealth({
        kind: "error",
        message: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }, [client]);

  return (
    <section
      style={{
        border: "1px solid #e5e5e5",
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
        background: "#fff",
      }}
    >
      <button
        type="button"
        onClick={() => {
          setOpen((prev) => !prev);
        }}
        aria-expanded={open}
        style={{
          background: "transparent",
          border: "none",
          padding: 0,
          fontSize: 14,
          fontWeight: 600,
          color: "#333",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span style={{ display: "inline-block", width: 10 }}>
          {open ? "v" : ">"}
        </span>
        Diagnostics
      </button>
      {open ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <SecondaryButton
              onClick={() => {
                void runHealth();
              }}
            >
              Test API connectivity
            </SecondaryButton>
            <HealthPill state={health} />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function HealthPill({ state }: { state: HealthState }): ReactElement | null {
  if (state.kind === "idle") return null;
  if (state.kind === "loading") {
    return <span style={{ fontSize: 13, color: "#666" }}>Checking...</span>;
  }
  if (state.kind === "ok") {
    return (
      <span style={{ fontSize: 13, color: "#2b7a3d" }}>
        OK — API is reachable.
      </span>
    );
  }
  return (
    <span style={{ fontSize: 13, color: "#b00020" }}>
      Error: {state.message}
    </span>
  );
}

// --------------------------------------------------------------------------- //
// Shared primitives (inline — no components/ dir exists yet)                  //
// --------------------------------------------------------------------------- //

interface SectionProps {
  title: string;
  children: ReactNode;
}

function Section({ title, children }: SectionProps): ReactElement {
  return (
    <section
      style={{
        border: "1px solid #e5e5e5",
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
        background: "#fff",
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 14 }}>{title}</h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {children}
      </div>
    </section>
  );
}

interface RowProps {
  label: string;
  value: ReactElement | string;
}

function Row({ label, value }: RowProps): ReactElement {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "160px 1fr",
        gap: 12,
        fontSize: 13,
      }}
    >
      <span style={{ color: "#666" }}>{label}</span>
      <span style={{ color: "#222" }}>{value}</span>
    </div>
  );
}

interface SecondaryButtonProps {
  onClick: () => void;
  children: string;
}

function SecondaryButton({
  onClick,
  children,
}: SecondaryButtonProps): ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: "5px 12px",
        borderRadius: 6,
        border: "1px solid #ddd",
        background: "#fafafa",
        color: "#333",
        fontSize: 13,
      }}
    >
      {children}
    </button>
  );
}
