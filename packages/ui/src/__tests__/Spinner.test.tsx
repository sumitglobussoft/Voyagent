import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Spinner } from "../Spinner.js";

describe("Spinner", () => {
  it("renders with default label", () => {
    render(<Spinner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    // Default "Loading" label is present for SRs but visually hidden.
    expect(screen.getByText("Loading")).toBeInTheDocument();
  });

  it("honours a custom label", () => {
    render(<Spinner label="Saving" />);
    expect(screen.getByText("Saving")).toBeInTheDocument();
  });

  it("applies size-specific classes", () => {
    const { container } = render(<Spinner size="lg" />);
    // The inner decorative span is the sized element.
    const inner = container.querySelector("span > span[aria-hidden='true']");
    expect(inner?.className ?? "").toMatch(/h-6 w-6/);
  });

  it("merges consumer className on the outer span", () => {
    render(<Spinner className="outer-cls" />);
    expect(screen.getByRole("status")).toHaveClass("outer-cls");
  });
});
