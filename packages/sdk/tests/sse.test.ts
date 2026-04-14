/**
 * Tests for the SSE parser.
 *
 * We feed `streamSSE` a mocked `globalThis.fetch` whose `body` is a
 * hand-rolled `ReadableStream<Uint8Array>` — exactly what a browser
 * (or Node 20+) would produce over the wire. This lets us exercise the
 * wire parser without pretending to have a real HTTP server around.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { streamSSE } from "../src/sse.js";
import { VoyagentApiError } from "../src/errors.js";

function makeStream(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      const chunk = chunks[i] ?? "";
      controller.enqueue(enc.encode(chunk));
      i += 1;
    },
  });
}

function mockSSEResponse(chunks: string[], status = 200): Response {
  return new Response(makeStream(chunks), {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("streamSSE — wire parsing", () => {
  it("parses multiple framed events (event + data + blank line)", async () => {
    const wire =
      "event: agent_event\ndata: {\"kind\":\"text_delta\",\"text\":\"hi\"}\n\n" +
      "event: agent_event\ndata: {\"kind\":\"final\",\"text\":\"done\"}\n\n";

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockSSEResponse([wire])),
    );

    const events: Array<{ event: string; data: unknown }> = [];
    for await (const ev of streamSSE("http://x/stream")) {
      events.push({ event: ev.event, data: ev.data });
    }

    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({
      event: "agent_event",
      data: { kind: "text_delta", text: "hi" },
    });
    expect(events[1]).toEqual({
      event: "agent_event",
      data: { kind: "final", text: "done" },
    });
  });

  it("defaults event name to 'message' when server omits it", async () => {
    const wire = 'data: {"hello":"world"}\n\n';
    vi.stubGlobal("fetch", vi.fn(async () => mockSSEResponse([wire])));

    const out: Array<{ event: string; data: unknown }> = [];
    for await (const ev of streamSSE("http://x")) {
      out.push({ event: ev.event, data: ev.data });
    }

    expect(out).toEqual([{ event: "message", data: { hello: "world" } }]);
  });

  it("captures id: and forwards to onLastEventId", async () => {
    const wire =
      'id: 42\nevent: agent_event\ndata: {"kind":"text_delta"}\n\n' +
      'id: 43\nevent: agent_event\ndata: {"kind":"final"}\n\n';

    vi.stubGlobal("fetch", vi.fn(async () => mockSSEResponse([wire])));

    const seenIds: string[] = [];
    const events: Array<{ id?: string }> = [];
    for await (const ev of streamSSE("http://x", undefined, {
      onLastEventId: (id) => seenIds.push(id),
    })) {
      events.push({ id: ev.id });
    }

    expect(seenIds).toEqual(["42", "43"]);
    expect(events.map((e) => e.id)).toEqual(["42", "43"]);
  });

  it("skips comment lines starting with ':'", async () => {
    const wire =
      ": heartbeat comment\n" +
      'event: agent_event\ndata: {"kind":"final"}\n\n';

    vi.stubGlobal("fetch", vi.fn(async () => mockSSEResponse([wire])));

    const out: unknown[] = [];
    for await (const ev of streamSSE("http://x")) {
      out.push(ev.data);
    }
    expect(out).toEqual([{ kind: "final" }]);
  });

  it("joins multi-line data: with '\\n' before JSON-parsing", async () => {
    // Two data: lines forming a single JSON object split across lines.
    const wire = "event: agent_event\ndata: {\"kind\":\ndata: \"final\"}\n\n";
    vi.stubGlobal("fetch", vi.fn(async () => mockSSEResponse([wire])));

    const out: unknown[] = [];
    for await (const ev of streamSSE("http://x")) {
      out.push(ev.data);
    }
    expect(out).toEqual([{ kind: "final" }]);
  });

  it("falls back to raw string data when payload isn't JSON", async () => {
    const wire = "event: raw\ndata: hello, world\n\n";
    vi.stubGlobal("fetch", vi.fn(async () => mockSSEResponse([wire])));

    const out: Array<{ event: string; data: unknown }> = [];
    for await (const ev of streamSSE("http://x")) {
      out.push({ event: ev.event, data: ev.data });
    }
    expect(out).toEqual([{ event: "raw", data: "hello, world" }]);
  });

  it("re-assembles frames split across multiple stream chunks", async () => {
    // Split a single frame in the middle of the data JSON.
    const chunks = [
      "event: agent_event\ndata: {\"kind\":",
      "\"text_delta\",\"text\":\"hi\"}\n\n",
    ];
    vi.stubGlobal("fetch", vi.fn(async () => mockSSEResponse(chunks)));

    const out: unknown[] = [];
    for await (const ev of streamSSE("http://x")) {
      out.push(ev.data);
    }
    expect(out).toEqual([{ kind: "text_delta", text: "hi" }]);
  });

  it("throws VoyagentApiError on non-2xx without iterating events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response('{"detail":"nope"}', {
            status: 401,
          }),
      ),
    );

    const iter = streamSSE("http://x");
    await expect(async () => {
      for await (const _ of iter) {
        void _;
      }
    }).rejects.toBeInstanceOf(VoyagentApiError);
  });

  it("routes typed events into the default isTerminal predicate — stops after final", async () => {
    // Stream closes cleanly after a final event; with reconnect enabled
    // the loop should NOT reopen because the terminator was seen.
    const wire =
      'event: agent_event\ndata: {"kind":"text_delta"}\n\n' +
      'event: agent_event\ndata: {"kind":"final"}\n\n';

    const fetchMock = vi.fn(async () => mockSSEResponse([wire]));
    vi.stubGlobal("fetch", fetchMock);

    const events: unknown[] = [];
    for await (const ev of streamSSE<{ kind: string }>(
      "http://x",
      undefined,
      { reconnect: {} },
    )) {
      events.push(ev.data);
    }

    expect(events).toHaveLength(2);
    // Exactly one underlying fetch — no reconnect attempt after terminator.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
