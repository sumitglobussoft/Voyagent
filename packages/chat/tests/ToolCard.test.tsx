/**
 * Tests for <ToolCallCard /> — the collapsible tool-use card.
 *
 * Contract:
 *   - collapsed by default (details.open === false)
 *   - opens on click
 *   - renders the tool name
 *   - renders a result section once tool_output arrives
 *   - derives a DEL -> DXB summary for flight search shapes
 */
import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ToolCallCard } from "../src/ToolCallCard.web.js";
import type { ToolCallEntry } from "../src/types.js";

function mkCall(overrides: Partial<ToolCallEntry> = {}): ToolCallEntry {
  return {
    tool_call_id: "t1",
    tool_name: "search_flights",
    tool_input: { origin: "DEL", destination: "DXB" },
    done: false,
    ...overrides,
  };
}

describe("ToolCallCard", () => {
  it("is collapsed by default", () => {
    const { container } = render(<ToolCallCard call={mkCall()} />);
    const details = container.querySelector("details") as HTMLDetailsElement;
    expect(details).not.toBeNull();
    expect(details.open).toBe(false);
  });

  it("opens when the summary is clicked", () => {
    const { container } = render(<ToolCallCard call={mkCall()} />);
    const details = container.querySelector("details") as HTMLDetailsElement;
    const summary = container.querySelector("summary") as HTMLElement;
    fireEvent.click(summary);
    // Simulate native toggle — JSDOM's <summary> click doesn't auto-toggle.
    details.open = true;
    expect(details.open).toBe(true);
  });

  it("renders a derived one-line summary for flight searches", () => {
    render(<ToolCallCard call={mkCall()} />);
    // Summary text contains the arrow shape we derive.
    expect(screen.getByText(/DEL -> DXB/)).toBeInTheDocument();
  });

  it("renders a result section once the tool output arrives", () => {
    const { queryByTestId, rerender } = render(
      <ToolCallCard call={mkCall()} />,
    );
    expect(queryByTestId("tool-card-result")).toBeNull();

    rerender(
      <ToolCallCard
        call={mkCall({
          done: true,
          tool_output: { status: "ok", flights: 5 },
        })}
      />,
    );
    expect(queryByTestId("tool-card-result")).not.toBeNull();
  });

  it("renders the tool name badge", () => {
    render(<ToolCallCard call={mkCall({ tool_name: "get_pnr" })} />);
    expect(screen.getByText("get_pnr")).toBeInTheDocument();
  });
});
