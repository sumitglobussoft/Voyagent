import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Avatar } from "../Avatar.js";

describe("Avatar", () => {
  it("renders initials when no src is provided", () => {
    render(<Avatar name="Ada Lovelace" />);
    expect(screen.getByText("AL")).toBeInTheDocument();
  });

  it("renders a single-character initial for one-word names", () => {
    render(<Avatar name="Cher" />);
    expect(screen.getByText("C")).toBeInTheDocument();
  });

  it("renders the image when src is supplied and loads", () => {
    render(<Avatar name="Ada" src="https://example.com/a.png" />);
    const img = screen.getByRole("img", { name: "Ada" });
    expect(img).toHaveAttribute("src", "https://example.com/a.png");
  });

  it("falls back to initials when the image errors", () => {
    render(<Avatar name="Ada Lovelace" src="https://bad.example/404.png" />);
    const img = screen.getByRole("img");
    act(() => {
      fireEvent.error(img);
    });
    expect(screen.getByText("AL")).toBeInTheDocument();
  });

  it("applies size-specific classes", () => {
    render(<Avatar name="Ada" size="lg" data-testid="a" />);
    expect(screen.getByTestId("a").className).toMatch(/h-10 w-10/);
  });

  it("merges consumer className", () => {
    render(<Avatar name="Ada" className="my-avatar" data-testid="a" />);
    expect(screen.getByTestId("a")).toHaveClass("my-avatar");
  });
});
