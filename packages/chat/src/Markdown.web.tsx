"use client";

/**
 * Safe markdown renderer for assistant messages.
 *
 * Uses `react-markdown` + `remark-gfm` (tables, task lists, strikethrough)
 * and `rehype-highlight` for fenced-code-block syntax highlighting. The
 * rehype plugin runs highlight.js against each `<code>` element, which
 * adds `hljs language-<lang>` class names so the theme CSS loaded in
 * `apps/web/app/globals.css` can style them.
 *
 * Unknown fence languages fall through to a plain `<code>` (highlight.js
 * ships with `ignoreMissing: true` behaviour via its auto-detection —
 * we pass an empty `languages` map so that unknown strings render as
 * plain text rather than throwing).
 *
 * Raw HTML is still blocked: no `rehype-raw`, plus an explicit deny list
 * of the usual dangerous elements so a runaway model can't inject a
 * `<script>` even if a future plugin starts parsing HTML.
 */
import type { ReactElement } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

export interface MarkdownProps {
  text: string;
}

export function Markdown({ text }: MarkdownProps): ReactElement {
  return (
    <div className="voyagent-markdown text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          // `ignoreMissing` lets unknown languages fall through to plain
          // text instead of throwing; `detect` stays false so we do not
          // auto-highlight unfenced inline code.
          [rehypeHighlight, { ignoreMissing: true, detect: false }],
        ]}
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
