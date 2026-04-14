import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "../EmptyState.js";

describe("EmptyState", () => {
  it("renders the title with minimum props", () => {
    render(<EmptyState title="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("renders a landmark via role=status", () => {
    render(<EmptyState title="Empty" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders description + action when supplied", () => {
    render(
      <EmptyState
        title="Empty"
        description="No reports yet"
        action={<button type="button">Go</button>}
      />,
    );
    expect(screen.getByText("No reports yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });

  it("merges consumer className", () => {
    render(<EmptyState title="Empty" className="my-empty" />);
    expect(screen.getByRole("status")).toHaveClass("my-empty");
  });
});
