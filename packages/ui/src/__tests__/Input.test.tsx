import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Input } from "../Input.js";

describe("Input", () => {
  it("renders with minimum props", () => {
    render(<Input aria-label="email" />);
    expect(screen.getByRole("textbox", { name: "email" })).toBeInTheDocument();
  });

  it("associates <label htmlFor> with the input id", () => {
    render(<Input label="Email" />);
    const input = screen.getByLabelText("Email");
    // The label is wired via htmlFor → the id the input ended up with.
    expect(input.id.length).toBeGreaterThan(0);
    const label = screen.getByText("Email").closest("label");
    expect(label).not.toBeNull();
    expect(label).toHaveAttribute("for", input.id);
  });

  it("merges consumer className on the input element", () => {
    render(<Input label="Name" className="extra-cls" />);
    expect(screen.getByLabelText("Name")).toHaveClass("extra-cls");
  });

  it("exposes required via native + aria attributes", () => {
    render(<Input label="Tenant" required />);
    const input = screen.getByLabelText(/Tenant/);
    expect(input).toBeRequired();
    expect(input).toHaveAttribute("aria-required", "true");
  });

  it("exposes error via aria-invalid + role=alert", () => {
    render(<Input label="Email" error="Required field" />);
    expect(screen.getByLabelText("Email")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Required field");
  });

  it("wires aria-describedby to the description when set", () => {
    render(<Input label="Email" description="We'll never share it" />);
    const input = screen.getByLabelText("Email");
    const descId = input.getAttribute("aria-describedby");
    expect(descId).not.toBeNull();
    expect(document.getElementById(descId ?? "")).toHaveTextContent(
      "We'll never share it",
    );
  });
});
