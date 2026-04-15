"use client";

/**
 * Per-message action toolbar (copy / regenerate).
 *
 * Rendered below user and assistant bubbles. Copy writes the raw markdown
 * text to the system clipboard; regenerate is only offered on completed
 * assistant messages and fires back up to the parent hook so it can re-run
 * the preceding user turn.
 */
import { useCallback, useState, type ReactElement } from "react";

export interface MessageActionsProps {
  /** Raw text to copy — the markdown source, not the rendered HTML. */
  text: string;
  /** If true, show a Regenerate button. */
  canRegenerate?: boolean;
  onRegenerate?: () => void | Promise<void>;
  /** Forces the toolbar to be always visible (for the latest message). */
  alwaysVisible?: boolean;
}

export function MessageActions(props: MessageActionsProps): ReactElement {
  const { text, canRegenerate, onRegenerate, alwaysVisible } = props;
  const [copied, setCopied] = useState(false);

  const onCopy = useCallback(async () => {
    try {
      // `navigator.clipboard` is the modern API; tests stub it.
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard APIs throw in insecure contexts (e.g. http://). We
      // intentionally swallow and rely on the lack of feedback as the
      // "failed" state — logging to console would be noisy.
    }
  }, [text]);

  const visibility = alwaysVisible
    ? "flex"
    : "hidden group-hover:flex focus-within:flex";

  return (
    <div
      className={`${visibility} mt-1 gap-2 text-xs text-neutral-500`}
      data-testid="message-actions"
    >
      <button
        type="button"
        onClick={() => {
          void onCopy();
        }}
        className="rounded px-2 py-0.5 hover:bg-neutral-200"
        aria-label="Copy message"
      >
        {copied ? "Copied" : "Copy"}
      </button>
      {canRegenerate && onRegenerate ? (
        <button
          type="button"
          onClick={() => {
            void onRegenerate();
          }}
          className="rounded px-2 py-0.5 hover:bg-neutral-200"
          aria-label="Regenerate response"
        >
          Regenerate
        </button>
      ) : null}
    </div>
  );
}
