/**
 * SSE (Server-Sent Events) helper.
 *
 * Parses the SSE wire format using `fetch` + the streams API. Works in
 * browsers, Node 20+, and React Native (where `ReadableStream` is available).
 *
 * Reconnection
 * ------------
 * The browser-native `EventSource` auto-retries on connection drop. This
 * helper doesn't — it's a `fetch`-based iterator — so it reimplements the
 * important part explicitly. On an unexpected stream close (no terminal
 * event observed), `streamSSE` opens a new request with the last seen
 * `id:` forwarded as the `Last-Event-ID` header, with exponential backoff
 * and a caller-supplied "is this event a terminator?" predicate. Aborting
 * via `init.signal` short-circuits reconnect.
 */
import { VoyagentApiError } from "./errors.js";

export interface SSEEvent<T = unknown> {
  /** `event:` field, defaulting to `"message"` if the server omits it. */
  event: string;
  /** Parsed JSON payload from the `data:` field(s). */
  data: T;
  /** Raw `id:` field, if supplied. */
  id?: string;
}

/** Options controlling automatic reconnection on unexpected stream close. */
export interface SSEReconnectOptions<T = unknown> {
  /** Maximum number of retry attempts after an unexpected close. Default 5. */
  maxRetries?: number;
  /**
   * Backoff computed from the attempt number (1-indexed). Default is
   * exponential with jitter: `200 * 2**(attempt-1) + rand(0..200)`
   * clamped to 5 s.
   */
  backoffMs?: (attempt: number) => number;
  /**
   * Predicate: does this event terminate the logical stream? When it
   * returns true, `streamSSE` stops reconnecting even if the server
   * closes the underlying connection.
   *
   * Default: `event.event === "agent_event"` AND the payload has
   * `kind === "final"` — matches the Voyagent chat contract. Callers
   * outside the chat surface should override.
   */
  isTerminalEvent?: (event: SSEEvent<T>) => boolean;
}

export interface StreamSSEOptions<T = unknown> {
  /** Called once with each new `id:` value seen on the wire. */
  onLastEventId?: (id: string) => void;
  /** Called once per event (in addition to being yielded). */
  onEvent?: (ev: SSEEvent<T>) => void;
  /** Reconnect configuration. Omit to disable automatic reconnection. */
  reconnect?: SSEReconnectOptions<T>;
}

const DEFAULT_MAX_RETRIES = 5;

function defaultBackoffMs(attempt: number): number {
  const base = 200 * Math.pow(2, attempt - 1);
  const jitter = Math.floor(Math.random() * 200);
  return Math.min(5000, base + jitter);
}

function defaultIsTerminal<T>(ev: SSEEvent<T>): boolean {
  if (ev.event !== "agent_event") return false;
  const data = ev.data as { kind?: string } | null;
  return !!data && data.kind === "final";
}

async function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) return;
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    if (signal) {
      const onAbort = () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      };
      if (signal.aborted) onAbort();
      else signal.addEventListener("abort", onAbort, { once: true });
    }
  });
}

/**
 * Stream SSE events from `url` as an async iterable.
 *
 * On unexpected stream close (no terminal event seen, and the caller
 * hasn't aborted), `streamSSE` retries with `Last-Event-ID` set to the
 * last seen id.
 */
export async function* streamSSE<T = unknown>(
  url: string,
  init?: RequestInit,
  options?: StreamSSEOptions<T> | ((ev: SSEEvent<T>) => void),
): AsyncIterable<SSEEvent<T>> {
  // Back-compat shim: the v0 signature took `(url, init, onEvent)`.
  const opts: StreamSSEOptions<T> =
    typeof options === "function" ? { onEvent: options } : options ?? {};

  const maxRetries = opts.reconnect?.maxRetries ?? DEFAULT_MAX_RETRIES;
  const backoffMs = opts.reconnect?.backoffMs ?? defaultBackoffMs;
  const isTerminal = opts.reconnect?.isTerminalEvent ?? defaultIsTerminal;
  const reconnectEnabled = opts.reconnect !== undefined;

  let lastEventId: string | undefined;
  let sawTerminal = false;
  let attempt = 0;

  while (true) {
    const attemptHeaders = new Headers(init?.headers);
    if (!attemptHeaders.has("Accept"))
      attemptHeaders.set("Accept", "text/event-stream");
    if (lastEventId !== undefined) {
      attemptHeaders.set("Last-Event-ID", lastEventId);
    }

    try {
      const iter = runOneStream<T>(url, {
        ...init,
        headers: attemptHeaders,
      });
      for await (const ev of iter) {
        if (ev.id !== undefined) {
          lastEventId = ev.id;
          opts.onLastEventId?.(ev.id);
        }
        opts.onEvent?.(ev);
        yield ev;
        if (isTerminal(ev)) {
          sawTerminal = true;
        }
      }
      // Stream closed cleanly. If we saw the terminator or reconnect is
      // off, we're done. Otherwise fall through to reconnect.
      if (sawTerminal || !reconnectEnabled) return;
    } catch (err) {
      // Aborts and HTTP-status errors should NOT trigger retry.
      if (
        err instanceof VoyagentApiError ||
        (err instanceof Error && err.name === "AbortError") ||
        !reconnectEnabled
      ) {
        throw err;
      }
      // Otherwise this is likely a network hiccup — fall through to retry.
    }

    if (!reconnectEnabled || sawTerminal) return;
    attempt += 1;
    if (attempt > maxRetries) return;
    try {
      await sleep(backoffMs(attempt), init?.signal ?? undefined);
    } catch {
      return; // aborted during backoff
    }
  }
}

/** One request, one iterator — no retry logic here. */
async function* runOneStream<T = unknown>(
  url: string,
  init?: RequestInit,
): AsyncIterable<SSEEvent<T>> {
  const response = await fetch(url, init);

  if (!response.ok) {
    const raw = await response.text().catch(() => "");
    throw new VoyagentApiError({
      status: response.status,
      method: init?.method ?? "GET",
      path: url,
      responseBodyPreview: raw.slice(0, 512),
    });
  }

  if (!response.body) {
    throw new Error("streamSSE: response has no body; SSE requires a streaming body.");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();

  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];
  let eventId: string | undefined;

  const flush = (): SSEEvent<T> | undefined => {
    if (dataLines.length === 0) {
      eventName = "message";
      eventId = undefined;
      return undefined;
    }
    const rawData = dataLines.join("\n");
    let parsed: T;
    try {
      parsed = JSON.parse(rawData) as T;
    } catch {
      parsed = rawData as unknown as T;
    }
    const ev: SSEEvent<T> = { event: eventName, data: parsed };
    if (eventId !== undefined) ev.id = eventId;

    eventName = "message";
    dataLines = [];
    eventId = undefined;
    return ev;
  };

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;

      let newlineIdx: number;
      while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
        const rawLine = buffer.slice(0, newlineIdx).replace(/\r$/, "");
        buffer = buffer.slice(newlineIdx + 1);

        if (rawLine === "") {
          const ev = flush();
          if (ev) yield ev;
          continue;
        }
        if (rawLine.startsWith(":")) continue; // comment

        const colonIdx = rawLine.indexOf(":");
        const field = colonIdx === -1 ? rawLine : rawLine.slice(0, colonIdx);
        const valueStr =
          colonIdx === -1
            ? ""
            : rawLine.slice(colonIdx + 1).replace(/^ /, "");

        if (field === "event") eventName = valueStr;
        else if (field === "data") dataLines.push(valueStr);
        else if (field === "id") eventId = valueStr;
        // retry / unknown fields ignored.
      }
    }

    // Flush a trailing event with no blank-line terminator.
    const tail = flush();
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}
