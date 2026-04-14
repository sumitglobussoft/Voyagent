/**
 * Tests for <ApprovalPrompt /> — the blocking gate shown whenever the
 * runtime pauses for human approval.
 *
 * The component contract:
 *   - Shows the tool summary prominently.
 *   - Approve + Deny each call `onRespond(approvalId, granted)`.
 *   - `busy` disables both buttons (we don't let an operator double-click
 *     while the previous response is still in flight).
 *   - Autofocuses Approve for keyboard operators.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ApprovalPrompt } from "../src/ApprovalPrompt.web.js";
import type { ApprovalRequest } from "../src/types.js";

const APPROVAL: ApprovalRequest = {
  approval_id: "appr-42",
  summary: "Issue EMD-A for passenger John Doe on flight AI-101",
  turn_id: "turn-1",
};

describe("ApprovalPrompt", () => {
  it("renders the summary text", () => {
    render(
      <ApprovalPrompt
        approval={APPROVAL}
        busy={false}
        onRespond={vi.fn()}
      />,
    );
    expect(screen.getByText(APPROVAL.summary)).toBeInTheDocument();
  });

  it("wires Approve → onRespond(approvalId, true)", () => {
    const onRespond = vi.fn();
    render(
      <ApprovalPrompt approval={APPROVAL} busy={false} onRespond={onRespond} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onRespond).toHaveBeenCalledWith("appr-42", true);
  });

  it("wires Deny → onRespond(approvalId, false)", () => {
    const onRespond = vi.fn();
    render(
      <ApprovalPrompt approval={APPROVAL} busy={false} onRespond={onRespond} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /deny/i }));
    expect(onRespond).toHaveBeenCalledWith("appr-42", false);
  });

  it("disables both buttons when busy=true", () => {
    render(
      <ApprovalPrompt approval={APPROVAL} busy={true} onRespond={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /approve/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /deny/i })).toBeDisabled();
  });

  it("autofocuses the Approve button on mount", () => {
    render(
      <ApprovalPrompt approval={APPROVAL} busy={false} onRespond={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /approve/i })).toHaveFocus();
  });

  it("uses an alertdialog role so assistive tech surfaces it", () => {
    render(
      <ApprovalPrompt approval={APPROVAL} busy={false} onRespond={vi.fn()} />,
    );
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });
});
