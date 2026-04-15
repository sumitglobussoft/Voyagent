/**
 * Tests for the <Markdown /> renderer.
 *
 * Contract:
 *   - bold/italic render as <strong>/<em>
 *   - fenced code blocks render as <pre><code>
 *   - GFM tables render as <table>
 *   - raw <script> is dropped (no script element in the DOM)
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { Markdown } from "../src/Markdown.web.js";

describe("Markdown", () => {
  it("renders **bold** and *italic* with semantic tags", () => {
    const { container } = render(
      <Markdown text="**bold** and *italic*" />,
    );
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("em")?.textContent).toBe("italic");
  });

  it("renders a fenced code block as <pre><code>", () => {
    const md = "```\nconst x = 1;\n```";
    const { container } = render(<Markdown text={md} />);
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    expect(pre?.querySelector("code")?.textContent).toContain("const x = 1;");
  });

  it("renders a GFM table", () => {
    const md =
      "| h1 | h2 |\n| --- | --- |\n| a | b |\n";
    const { container } = render(<Markdown text={md} />);
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.querySelectorAll("th").length).toBe(2);
    expect(table?.querySelectorAll("td").length).toBe(2);
  });

  it("renders unordered lists", () => {
    const md = "- one\n- two\n- three";
    const { container } = render(<Markdown text={md} />);
    expect(container.querySelectorAll("li").length).toBe(3);
  });

  it("drops raw <script> tags (no script element lands in the DOM)", () => {
    const md = "<script>alert('pwned')</script>hello";
    const { container } = render(<Markdown text={md} />);
    expect(container.querySelector("script")).toBeNull();
  });
});
