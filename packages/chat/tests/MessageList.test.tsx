/**
 * Tests for <MessageList /> — the transcript surface.
 *
 * Contract:
 *   - User and assistant bubbles render in the given order.
 *   - React keys (`message.id`) are stable, so appending a new message
 *     does NOT unmount existing DOM nodes — important for preserving
 *     scroll position / caret / animations.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { MessageList } from "../src/MessageList.web.js";
import type { ChatMessage } from "../src/types.js";

const user = (id: string, text: string): ChatMessage => ({
  kind: "user",
  id,
  text,
  timestamp: "0",
});

const assistant = (
  id: string,
  text: string,
  opts?: Partial<Extract<ChatMessage, { kind: "assistant" }>>,
): ChatMessage => ({
  kind: "assistant",
  id,
  text,
  timestamp: "0",
  toolCalls: [],
  complete: false,
  ...opts,
});

describe("MessageList", () => {
  it("renders user and assistant messages in order", () => {
    render(
      <MessageList
        messages={[
          user("u1", "hi there"),
          assistant("a1", "hello back"),
          user("u2", "thanks"),
        ]}
      />,
    );

    expect(screen.getByText("hi there")).toBeInTheDocument();
    expect(screen.getByText("hello back")).toBeInTheDocument();
    expect(screen.getByText("thanks")).toBeInTheDocument();
  });

  it("uses role=log with aria-live=polite for assistive tech", () => {
    render(<MessageList messages={[]} />);
    const log = screen.getByRole("log");
    expect(log).toHaveAttribute("aria-live", "polite");
  });

  it("keeps DOM nodes stable across rerenders when ids don't change (key stability)", () => {
    const initial: ChatMessage[] = [
      user("u1", "first"),
      assistant("a1", "second"),
    ];

    const { rerender } = render(<MessageList messages={initial} />);
    const firstNode = screen.getByText("first");
    const secondNode = screen.getByText("second");

    // Add a brand new message; the original DOM nodes for existing ids
    // must be the *same* JS references after the rerender.
    rerender(
      <MessageList
        messages={[...initial, user("u2", "appended")]}
      />,
    );

    expect(screen.getByText("first")).toBe(firstNode);
    expect(screen.getByText("second")).toBe(secondNode);
    expect(screen.getByText("appended")).toBeInTheDocument();
  });

  it("renders the assistant error slot when present", () => {
    render(
      <MessageList
        messages={[
          assistant("a1", "partial response", {
            error: "tool exploded",
            complete: true,
          }),
        ]}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("tool exploded");
  });

  it("tolerates an empty message list", () => {
    render(<MessageList messages={[]} />);
    const log = screen.getByRole("log");
    // Only the auto-scroll sentinel div should live inside an empty log.
    expect(log.querySelectorAll("div")).toHaveLength(1);
  });
});
