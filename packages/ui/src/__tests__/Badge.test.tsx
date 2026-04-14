import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge } from "../Badge.js";

describe("Badge", () => {
  it("renders children", () => {
    render(<Badge>New</Badge>);
    expect(screen.getByText("New")).toBeInTheDocument();
  });

  it("applies the neutral variant by default", () => {
    render(<Badge data-testid="b">Default</Badge>);
    expect(screen.getByTestId("b").className).toMatch(/bg-neutral-100/);
  });

  it("applies the requested variant classes", () => {
    render(
      <Badge variant="danger" data-testid="b">
        Oops
      </Badge>,
    );
    expect(screen.getByTestId("b").className).toMatch(/bg-red-100/);
    expect(screen.getByTestId("b").className).toMatch(/text-red-800/);
  });

  it("merges consumer className", () => {
    render(
      <Badge className="my-badge" data-testid="b">
        X
      </Badge>,
    );
    expect(screen.getByTestId("b")).toHaveClass("my-badge");
  });
});
