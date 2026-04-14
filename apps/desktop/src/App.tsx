import { useState, type ReactElement } from "react";

import { ChatWindow } from "@voyagent/chat";

import { actorId, tenantId, voyagentClient } from "./sdk.js";

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
 * TODO(auth): Clerk integration. The auth agent is landing Clerk for web
 * first; desktop will follow with `@clerk/clerk-react` + a Tauri deep
 * link for the OAuth handoff. Until then the shell uses a dev tenant /
 * actor injected via environment variables (see `./sdk.ts`).
 */
export function App(): ReactElement {
  const [active, setActive] = useState<Tab>("chat");

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
              client={voyagentClient}
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
            management once Clerk auth is wired in.
          </p>
        </section>
      </main>
    </div>
  );
}
