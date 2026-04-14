/**
 * Integration-ish test for `client.sendMessage` — ties together the SSE
 * parser and the chat-surface event coercion.
 *
 * We mock the *global* `fetch` here (not the injected one) because
 * `streamSSE` does not route through `fetchImpl` in the current
 * implementation — see `src/sse.ts` where `runOneStream` calls `fetch`
 * directly. Flagged in the test report.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { VoyagentClient } from "../src/client.js";
import type { AgentEvent } from "../src/chat.js";

function makeStream(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(enc.encode(chunks[i] ?? ""));
      i += 1;
    },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("VoyagentClient.sendMessage", () => {
  it("yields only agent_event frames (heartbeats are filtered)", async () => {
    const wire =
      "event: heartbeat\ndata: {}\n\n" +
      'event: agent_event\ndata: {"kind":"text_delta","session_id":"s","turn_id":"t","timestamp":"0","text":"hello"}\n\n' +
      'event: agent_event\ndata: {"kind":"final","session_id":"s","turn_id":"t","timestamp":"0"}\n\n';

    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(makeStream([wire]), {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );

    const client = new VoyagentClient({ baseUrl: "http://x" });
    const seen: AgentEvent[] = [];
    for await (const ev of client.sendMessage("sess-1", { message: "hi" })) {
      seen.push(ev);
    }

    expect(seen.map((e) => e.kind)).toEqual(["text_delta", "final"]);
    expect(seen[0]?.text).toBe("hello");
  });

  it("serializes the request body as JSON with message + approvals keys", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          makeStream([
            'event: agent_event\ndata: {"kind":"final","session_id":"s","turn_id":"t","timestamp":"0"}\n\n',
          ]),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const client = new VoyagentClient({ baseUrl: "http://x" });
    for await (const _ of client.sendMessage("sess-1", {
      message: "hello",
      approvals: { "appr-1": true },
    })) {
      void _;
    }

    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    const parsed = JSON.parse(init.body as string);
    expect(parsed).toEqual({
      message: "hello",
      approvals: { "appr-1": true },
    });
    expect(new Headers(init.headers).get("Content-Type")).toBe(
      "application/json",
    );
    expect(new Headers(init.headers).get("Accept")).toBe("text/event-stream");
  });

  it("defaults approvals to null when caller omits them", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          makeStream([
            'event: agent_event\ndata: {"kind":"final","session_id":"s","turn_id":"t","timestamp":"0"}\n\n',
          ]),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const client = new VoyagentClient({ baseUrl: "http://x" });
    for await (const _ of client.sendMessage("sess-1", { message: "hi" })) {
      void _;
    }

    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    const parsed = JSON.parse(init.body as string);
    expect(parsed.approvals).toBeNull();
  });

  it("attaches Authorization header on the SSE request when authToken is set", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          makeStream([
            'event: agent_event\ndata: {"kind":"final","session_id":"s","turn_id":"t","timestamp":"0"}\n\n',
          ]),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const client = new VoyagentClient({
      baseUrl: "http://x",
      authToken: "sse-tok",
    });
    for await (const _ of client.sendMessage("sess-1", { message: "hi" })) {
      void _;
    }

    const headers = new Headers(
      (fetchSpy.mock.calls[0]?.[1] as RequestInit).headers,
    );
    expect(headers.get("Authorization")).toBe("Bearer sse-tok");
  });
});
