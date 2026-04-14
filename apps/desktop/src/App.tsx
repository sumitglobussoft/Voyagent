import { useState, type ReactElement } from "react";

import { ChatWindow } from "@voyagent/chat";

import { AuthProvider, useAuth } from "./auth/AuthProvider.js";
import { SignInScreen } from "./auth/SignInScreen.js";
import { Updater } from "./Updater.js";
import { actorId, tenantId, useVoyagentClient } from "./sdk.js";

type Tab = "chat" | "reports" | "settings";

interface TabDef {
  id: Tab;
  label: string;
}

const TABS: readonly TabDef[] = [
  { id: "chat", label: "Chat" },
  { id: "reports", label: "Reports" },
  { id: "settings", label: "Settings" },
];

/**
 * Top-level desktop shell. A three-tab layout (Chat / Reports / Settings)
 * where only Chat is wired — Reports and Settings are placeholders.
 *
 * Auth: `<AuthProvider>` holds the Clerk client. Until the user has a
 * session the shell renders `<SignInScreen>` instead of the chrome. The
 * deep-link redirect back from Clerk's hosted UI triggers a re-render.
 */
export function App(): ReactElement {
  return (
    <AuthProvider>
      <AuthedRoot />
    </AuthProvider>
  );
}

function AuthedRoot(): ReactElement {
  const { isReady, isAuthenticated } = useAuth();

  if (!isReady) {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          display: "flex",
          height: "100%",
          alignItems: "center",
          justifyContent: "center",
          color: "#666",
          fontSize: 13,
        }}
      >
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <SignInScreen />;
  }

  return <Shell />;
}

function Shell(): ReactElement {
  const [active, setActive] = useState<Tab>("chat");
  const { user, signOut } = useAuth();
  const client = useVoyagentClient();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#ffffff",
      }}
    >
      <header
        role="banner"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "8px 16px",
          borderBottom: "1px solid #e5e5e5",
        }}
      >
        <strong style={{ fontSize: 14 }}>Voyagent</strong>
        <nav
          role="tablist"
          aria-label="Primary navigation"
          style={{ display: "flex", gap: 4 }}
        >
          {TABS.map((tab) => {
            const isActive = tab.id === active;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-controls={`panel-${tab.id}`}
                id={`tab-${tab.id}`}
                onClick={() => setActive(tab.id)}
                style={{
                  padding: "6px 12px",
                  borderRadius: 6,
                  border: "1px solid transparent",
                  background: isActive ? "#111" : "transparent",
                  color: isActive ? "#fff" : "#333",
                  fontSize: 13,
                }}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>
        <div style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "#555" }}>
            {user?.email ?? user?.fullName ?? "Signed in"}
          </span>
          <button
            type="button"
            onClick={() => {
              void signOut();
            }}
            style={{
              padding: "4px 10px",
              borderRadius: 4,
              border: "1px solid #ddd",
              background: "transparent",
              color: "#333",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <main style={{ flex: 1, overflow: "hidden" }}>
        <section
          id="panel-chat"
          role="tabpanel"
          aria-labelledby="tab-chat"
          hidden={active !== "chat"}
          style={{ height: "100%" }}
        >
          {active === "chat" ? (
            <ChatWindow
              client={client}
              tenantId={tenantId}
              actorId={actorId}
            />
          ) : null}
        </section>

        <section
          id="panel-reports"
          role="tabpanel"
          aria-labelledby="tab-reports"
          hidden={active !== "reports"}
          style={{ padding: 24 }}
        >
          <h2 style={{ marginTop: 0 }}>Reports</h2>
          <p style={{ color: "#666" }}>
            Reports are coming soon. This tab will surface Tally-driven
            receivables, payables, and itinerary summaries once the desktop
            Tally sidecar ships.
          </p>
        </section>

        <section
          id="panel-settings"
          role="tabpanel"
          aria-labelledby="tab-settings"
          hidden={active !== "settings"}
          style={{ padding: 24 }}
        >
          <h2 style={{ marginTop: 0 }}>Settings</h2>
          <p style={{ color: "#666" }}>
            Settings are coming soon. This will host preferences, driver
            configuration (Tally ODBC, GDS terminals, printers), and account
            management.
          </p>
        </section>
      </main>

      <Updater />
    </div>
  );
}
