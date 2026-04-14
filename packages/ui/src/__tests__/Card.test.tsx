import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card } from "../Card.js";

describe("Card", () => {
  it("renders children", () => {
    render(<Card>Hello</Card>);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("renders header + footer slots", () => {
    render(
      <Card header="Top" footer="Bot">
        Middle
      </Card>,
    );
    expect(screen.getByText("Top")).toBeInTheDocument();
    expect(screen.getByText("Middle")).toBeInTheDocument();
    expect(screen.getByText("Bot")).toBeInTheDocument();
  });

  it("merges consumer className", () => {
    render(
      <Card className="my-card" data-testid="card">
        X
      </Card>,
    );
    expect(screen.getByTestId("card")).toHaveClass("my-card");
  });

  it("drops body padding when flush", () => {
    render(
      <Card flush data-testid="card">
        <span>inner</span>
      </Card>,
    );
    const body = screen.getByText("inner").parentElement;
    // The flush branch should not include the p-4 class.
    expect(body?.className ?? "").not.toMatch(/\bp-4\b/);
  });
});
