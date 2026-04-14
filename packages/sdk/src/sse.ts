/**
 * SSE (Server-Sent Events) helper.
 *
 * Scaffolding for the future agent-runtime streaming endpoint. NO server
 * endpoint currently emits SSE — this lands first so the client surface is
 * ready the day the agent-runtime endpoint does.
 *
 * Parses the SSE wire format using `fetch` + the streams API. Works in
 * browsers, Node 20+, and React Native (where `ReadableStream` is available).
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

/**
 * Stream SSE events from `url` as an async iterable. `onEvent` (if supplied) is
 * invoked for each event in addition to being yielded — handy for callers that
 * want a pure callback style.
 *
 * The returned async iterable completes when the server closes the stream.
 * Consumers can abort via `init.signal`.
 */
export async function* streamSSE<T = unknown>(
  url: string,
  init?: RequestInit,
  onEvent?: (ev: SSEEvent<T>) => void,
): AsyncIterable<SSEEvent<T>> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) headers.set("Accept", "text/event-stream");

  const response = await fetch(url, { ...init, headers });

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
      // Fall back to the raw string when payload isn't JSON.
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
          if (ev) {
            onEvent?.(ev);
            yield ev;
          }
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
    if (tail) {
      onEvent?.(tail);
      yield tail;
    }
  } finally {
    reader.releaseLock();
  }
}
