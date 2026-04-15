/**
 * Tests for <MessageActions /> — the per-message copy/regenerate toolbar.
 *
 * Contract:
 *   - copy writes to navigator.clipboard
 *   - regenerate fires the callback
 *   - regenerate is hidden when `canRegenerate` is false (e.g. still streaming)
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { MessageActions } from "../src/MessageActions.web.js";

describe("MessageActions", () => {
  beforeEach(() => {
    // JSDOM doesn't ship a clipboard; install a stub per test.
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn(async () => {}) },
    });
  });

  it("copies the message text to the clipboard when Copy is clicked", async () => {
    const writeText = vi.fn(async () => {});
    Object.assign(navigator, { clipboard: { writeText } });

    render(<MessageActions text="hello world" alwaysVisible />);

    fireEvent.click(screen.getByRole("button", { name: /copy message/i }));

    expect(writeText).toHaveBeenCalledWith("hello world");
  });

  it("shows a Regenerate button when canRegenerate=true and fires the callback", () => {
    const onRegenerate = vi.fn();
    render(
      <MessageActions
        text="hi"
        canRegenerate
        onRegenerate={onRegenerate}
        alwaysVisible
      />,
    );

    const btn = screen.getByRole("button", { name: /regenerate response/i });
    fireEvent.click(btn);
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it("hides the Regenerate button when canRegenerate=false", () => {
    render(
      <MessageActions text="hi" canRegenerate={false} alwaysVisible />,
    );
    expect(
      screen.queryByRole("button", { name: /regenerate response/i }),
    ).toBeNull();
  });
});
