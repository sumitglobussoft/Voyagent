import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "../Button.js";

describe("Button", () => {
  it("renders with minimum props", () => {
    render(<Button>Save</Button>);
    const btn = screen.getByRole("button", { name: "Save" });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveAttribute("type", "button");
  });

  it("merges consumer className", () => {
    render(<Button className="custom-hook">Hi</Button>);
    expect(screen.getByRole("button")).toHaveClass("custom-hook");
  });

  it("applies variant + size classes", () => {
    render(
      <Button variant="secondary" size="lg">
        Big
      </Button>,
    );
    const btn = screen.getByRole("button");
    // secondary variant uses bg-neutral-100; lg size uses h-12.
    expect(btn.className).toMatch(/bg-neutral-100/);
    expect(btn.className).toMatch(/h-12/);
  });

  it("disables and sets aria-busy when loading", () => {
    render(<Button loading>Saving</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
  });

  it("respects explicit disabled prop", () => {
    render(<Button disabled>Nope</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
