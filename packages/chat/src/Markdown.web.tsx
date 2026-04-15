"use client";

/**
 * Safe markdown renderer for assistant messages.
 *
 * Uses `react-markdown` + `remark-gfm` (tables, task lists, strikethrough).
 * Raw HTML is blocked: no `rehype-raw`, plus an explicit deny list of the
 * usual dangerous elements so a runaway model can't inject a `<script>`
 * even if a future plugin starts parsing HTML.
 *
 * Code blocks render as plain `<pre><code>` — syntax highlighting is a
 * deliberate v1 follow-up (would bloat the bundle by ~100kB gzipped and
 * needs a theme-matching step that isn't solved yet).
 */
import type { ReactElement } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface MarkdownProps {
  text: string;
}

// TODO(v1): wire `rehype-highlight` or `shiki` for syntax highlighting in
// fenced code blocks. Deferred — pick a theme that matches the rest of the
// chat palette before shipping.
export function Markdown({ text }: MarkdownProps): ReactElement {
  return (
    <div className="voyagent-markdown text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // Hard-block raw HTML injection paths; we don't use rehype-raw so
        // react-markdown already treats HTML as text, but being explicit
        // keeps the intent in-source for reviewers.
        disallowedElements={["script", "iframe", "style", "object", "embed"]}
        unwrapDisallowed={false}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
