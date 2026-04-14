import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Stack } from "../Stack.js";

describe("Stack", () => {
  it("renders children", () => {
    render(
      <Stack>
        <span>a</span>
        <span>b</span>
      </Stack>,
    );
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("b")).toBeInTheDocument();
  });

  it("defaults to a column flex stack with md gap", () => {
    render(
      <Stack data-testid="stack">
        <span>x</span>
      </Stack>,
    );
    const el = screen.getByTestId("stack");
    expect(el.className).toMatch(/flex-col/);
    expect(el.className).toMatch(/gap-4/);
  });

  it("switches to row direction when requested", () => {
    render(
      <Stack direction="row" gap="sm" data-testid="stack">
        <span>x</span>
      </Stack>,
    );
    expect(screen.getByTestId("stack").className).toMatch(/flex-row/);
    expect(screen.getByTestId("stack").className).toMatch(/gap-2/);
  });

  it("applies align + justify modifiers", () => {
    render(
      <Stack align="center" justify="between" data-testid="stack">
        <span>x</span>
      </Stack>,
    );
    expect(screen.getByTestId("stack").className).toMatch(/items-center/);
    expect(screen.getByTestId("stack").className).toMatch(/justify-between/);
  });

  it("merges consumer className", () => {
    render(
      <Stack className="my-stack" data-testid="stack">
        <span>x</span>
      </Stack>,
    );
    expect(screen.getByTestId("stack")).toHaveClass("my-stack");
  });
});
