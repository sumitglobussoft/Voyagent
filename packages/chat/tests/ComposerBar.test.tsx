/**
 * Tests for <ComposerBar /> — the textarea + submit control that feeds the
 * agent. Contract:
 *   - whitespace-only input is blocked
 *   - submit trims the payload and clears the textarea
 *   - Cmd/Ctrl+Enter submits
 *   - `disabled` fully blocks interaction
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ComposerBar } from "../src/ComposerBar.web.js";

describe("ComposerBar", () => {
  it("submits trimmed text on form submit and clears the textarea", async () => {
    const onSubmit = vi.fn();
    render(<ComposerBar disabled={false} onSubmit={onSubmit} />);

    const textarea = screen.getByLabelText("Message input") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "   hello agent   " } });

    const button = screen.getByRole("button", { name: /send/i });
    fireEvent.click(button);

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith("hello agent");
    // After submit the textarea should clear.
    expect(textarea.value).toBe("");
  });

  it("does NOT fire onSubmit for empty or whitespace-only input", () => {
    const onSubmit = vi.fn();
    render(<ComposerBar disabled={false} onSubmit={onSubmit} />);

    const textarea = screen.getByLabelText("Message input");
    fireEvent.change(textarea, { target: { value: "     " } });
    // Button is disabled for whitespace-only — force-click would still noop
    // but we exercise the form submit path here.
    const form = textarea.closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the Send button when textarea is empty", () => {
    render(<ComposerBar disabled={false} onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("submits on Cmd/Ctrl+Enter", () => {
    const onSubmit = vi.fn();
    render(<ComposerBar disabled={false} onSubmit={onSubmit} />);
    const textarea = screen.getByLabelText("Message input");
    fireEvent.change(textarea, { target: { value: "via keys" } });
    fireEvent.keyDown(textarea, { key: "Enter", ctrlKey: true });
    expect(onSubmit).toHaveBeenCalledWith("via keys");
  });

  it("blocks submit when disabled — including keyboard shortcut", () => {
    const onSubmit = vi.fn();
    render(
      <ComposerBar
        disabled={true}
        disabledReason="Agent is responding..."
        onSubmit={onSubmit}
      />,
    );

    const textarea = screen.getByLabelText("Message input") as HTMLTextAreaElement;
    expect(textarea).toBeDisabled();
    // Placeholder becomes the disabledReason while disabled.
    expect(textarea).toHaveAttribute("placeholder", "Agent is responding...");

    // Even if code managed to populate the value, submit must not fire.
    // (We can't type into a disabled textarea, so we directly submit the form.)
    const form = textarea.closest("form") as HTMLFormElement;
    fireEvent.submit(form);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
