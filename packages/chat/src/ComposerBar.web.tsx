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
    <form
      className="flex items-end gap-2 border-t border-neutral-200 bg-white p-3"
      onSubmit={(e) => {
        void submit(e);
      }}
    >
      <textarea
        className="flex-1 resize-none rounded border border-neutral-300 bg-white px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none disabled:bg-neutral-100 disabled:text-neutral-500"
        rows={2}
        value={value}
        disabled={disabled}
        placeholder={disabled && disabledReason ? disabledReason : placeholder}
        onChange={onChange}
        onKeyDown={onKeyDown}
        aria-label="Message input"
      />
      <button
        type="submit"
        disabled={disabled || value.trim().length === 0}
        className="rounded bg-neutral-900 px-3 py-2 text-sm text-neutral-50 disabled:cursor-not-allowed disabled:bg-neutral-400"
        title={disabled ? disabledReason : undefined}
      >
        Send
      </button>
    </form>
  );
}
