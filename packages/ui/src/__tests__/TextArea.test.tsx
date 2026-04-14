import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TextArea } from "../TextArea.js";

describe("TextArea", () => {
  it("renders with minimum props", () => {
    render(<TextArea aria-label="note" />);
    expect(screen.getByRole("textbox", { name: "note" })).toBeInTheDocument();
  });

  it("merges consumer className", () => {
    render(<TextArea label="Notes" className="merge-me" />);
    expect(screen.getByLabelText("Notes")).toHaveClass("merge-me");
  });

  it("marks the field required on the native element + aria", () => {
    render(<TextArea label="Body" required />);
    const ta = screen.getByLabelText(/Body/);
    expect(ta).toBeRequired();
    expect(ta).toHaveAttribute("aria-required", "true");
  });

  it("exposes accessible description via aria-describedby", () => {
    render(<TextArea label="Body" description="Supports markdown" />);
    const ta = screen.getByLabelText("Body");
    const descId = ta.getAttribute("aria-describedby");
    expect(descId).not.toBeNull();
    expect(document.getElementById(descId ?? "")).toHaveTextContent(
      "Supports markdown",
    );
  });

  it("shows error via aria-invalid + role=alert", () => {
    render(<TextArea label="Body" error="Too short" />);
    expect(screen.getByLabelText("Body")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Too short");
  });

  it("is disabled when the prop is passed", () => {
    render(<TextArea label="Body" disabled />);
    expect(screen.getByLabelText("Body")).toBeDisabled();
  });
});
