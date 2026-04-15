"use client";

/**
 * Textarea + Send composer. Submits on Cmd/Ctrl+Enter; disabled while the
 * agent is streaming or when at least one approval is pending (operators
 * must clear the approval queue before typing a fresh turn).
 */
import {
  useCallback,
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type ReactElement,
} from "react";

export interface ComposerBarProps {
  disabled: boolean;
  /** Human-readable reason the composer is disabled, shown in a tooltip. */
  disabledReason?: string;
  onSubmit: (text: string) => void | Promise<void>;
  placeholder?: string;
  /**
   * Optional externally-provided seed text (e.g. from clicking an empty-state
   * suggestion card). Whenever this changes to a non-empty value the composer
   * replaces its current content. Auto-submit is intentionally NOT wired —
   * the user still has to hit Send.
   */
  seedText?: string;
}

export function ComposerBar(props: ComposerBarProps): ReactElement {
  const {
    disabled,
    disabledReason,
    onSubmit,
    placeholder = "Message the agent...",
    seedText,
  } = props;
  const [value, setValue] = useState("");

  useEffect(() => {
    if (seedText && seedText.length > 0) setValue(seedText);
  }, [seedText]);

  const submit = useCallback(
    async (e?: FormEvent<HTMLFormElement>) => {
      if (e) e.preventDefault();
      const trimmed = value.trim();
      if (!trimmed || disabled) return;
      setValue("");
      await onSubmit(trimmed);
    },
    [disabled, onSubmit, value],
  );

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void submit();
      }
    },
    [submit],
  );

  const onChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
  }, []);

  return (
    <div className="border-t border-neutral-200 bg-gradient-to-t from-neutral-50 to-white px-4 py-4 md:px-6 md:py-5">
      <form
        className="mx-auto flex w-full max-w-3xl items-end gap-3"
        onSubmit={(e) => {
          void submit(e);
        }}
      >
        <div className="flex flex-1 items-end rounded-2xl border border-neutral-300 bg-white px-4 py-3 shadow-sm focus-within:border-neutral-500 focus-within:ring-2 focus-within:ring-neutral-200">
          <textarea
            className="flex-1 resize-none bg-transparent text-[15px] leading-relaxed placeholder:text-neutral-400 focus:outline-none disabled:text-neutral-400"
            rows={2}
            value={value}
            disabled={disabled}
            placeholder={disabled && disabledReason ? disabledReason : placeholder}
            onChange={onChange}
            onKeyDown={onKeyDown}
            aria-label="Message input"
          />
        </div>
        <button
          type="submit"
          disabled={disabled || value.trim().length === 0}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-neutral-900 text-white shadow-sm transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:bg-neutral-300 disabled:shadow-none"
          title={disabled ? disabledReason : "Send (Cmd/Ctrl + Enter)"}
          aria-label="Send message"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 19V5" />
            <path d="M5 12l7-7 7 7" />
          </svg>
        </button>
      </form>
      <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-neutral-400">
        Voyagent can make mistakes. Finance-critical actions require approval.
      </p>
    </div>
  );
}
