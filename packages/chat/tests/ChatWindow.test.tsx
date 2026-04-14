/**
 * Tests for <ChatWindow /> — the session-bootstrapping shell.
 *
 * We don't spin up a full SDK here; instead we pass a partial stub that
 * matches the narrow surface ChatWindow touches (`createSession`). That
 * keeps these tests about component behavior, not SDK round-trips (which
 * are covered in @voyagent/sdk's own suite).
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { ChatWindow } from "../src/ChatWindow.web.js";
import type { VoyagentClient } from "@voyagent/sdk";

type PartialClient = Pick<
  VoyagentClient,
  "createSession" | "getSession" | "sendMessage"
>;

function makeClient(overrides: Partial<PartialClient> = {}): VoyagentClient {
  const base: PartialClient = {
    createSession: vi.fn(async () => ({ session_id: "sess-new" })),
    getSession: vi.fn(async () => ({
      session_id: "sess-new",
      tenant_id: "t",
      actor_id: "a",
      message_count: 0,
      pending_approvals: [],
    })),
    // Empty async iterable by default — no events means no streaming.
    sendMessage: (async function* () {
      /* no events */
    }) as unknown as VoyagentClient["sendMessage"],
    ...overrides,
  };
  return base as unknown as VoyagentClient;
}

describe("ChatWindow", () => {
  it("shows a 'Starting session...' placeholder while createSession is in flight", () => {
    const client = makeClient({
      createSession: vi.fn(() => new Promise(() => {})),
    });

    render(<ChatWindow client={client} tenantId="t" actorId="a" />);

    expect(screen.getByRole("status")).toHaveTextContent(/starting session/i);
  });

  it("skips createSession when a sessionId is provided", async () => {
    const createSession = vi.fn();
    const client = makeClient({ createSession });

    render(
      <ChatWindow
        client={client}
        sessionId="sess-existing"
        tenantId="t"
        actorId="a"
      />,
    );

    // Composer should appear once no bootstrap is needed.
    await waitFor(() => {
      expect(screen.getByLabelText("Message input")).toBeInTheDocument();
    });
    expect(createSession).not.toHaveBeenCalled();
  });

  it("calls createSession with the given tenantId + actorId", async () => {
    const createSession = vi.fn(async () => ({ session_id: "sess-new" }));
    const client = makeClient({ createSession });

    render(<ChatWindow client={client} tenantId="tenant-X" actorId="actor-Y" />);

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledWith({
        tenant_id: "tenant-X",
        actor_id: "actor-Y",
      });
    });
  });

  it("surfaces an init error if createSession rejects", async () => {
    const client = makeClient({
      createSession: vi.fn(async () => {
        throw new Error("network down");
      }),
    });

    render(<ChatWindow client={client} tenantId="t" actorId="a" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/network down/i);
  });
});
