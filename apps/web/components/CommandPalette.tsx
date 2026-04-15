"use client";

/**
 * CommandPalette — the Cmd+K overlay UI.
 *
 * Pure presentation: receives an ``open`` flag and an ``onClose``
 * callback from its parent (``CommandPaletteProvider``). Renders a
 * centered dialog with an input and a filtered list of hard-coded
 * commands. Arrow keys move the selection, Enter runs, Escape closes.
 *
 * Fuzzy matcher (``matches``): lowercases both the query and the
 * label, then walks the label once requiring every query character to
 * appear in order. Substring matches count as fuzzy matches with the
 * same threshold, so typing "enq" hits "Enquiries".
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactElement,
} from "react";
import { useRouter } from "next/navigation";

import { useTranslations } from "./LocaleProvider";

export type CommandAction =
  | { kind: "navigate"; href: string }
  | { kind: "signout" };

export type Command = {
  id: string;
  label: string;
  hint?: string;
  action: CommandAction;
};

const BASE_COMMANDS: Command[] = [
  { id: "new-chat", label: "New chat", action: { kind: "navigate", href: "/chat?new=1" } },
  { id: "enquiries", label: "Enquiries", action: { kind: "navigate", href: "/enquiries" } },
  { id: "new-enquiry", label: "New enquiry", action: { kind: "navigate", href: "/enquiries/new" } },
  { id: "approvals", label: "Approvals", action: { kind: "navigate", href: "/approvals" } },
  { id: "audit", label: "Audit log", action: { kind: "navigate", href: "/audit" } },
  { id: "profile", label: "Profile", action: { kind: "navigate", href: "/profile" } },
  { id: "settings", label: "Settings", action: { kind: "navigate", href: "/settings" } },
  { id: "sign-out", label: "Sign out", action: { kind: "signout" } },
];

/**
 * Ordered-subsequence fuzzy matcher: returns true iff every char of
 * ``query`` appears in ``label`` in order (case-insensitive). An empty
 * query matches everything.
 */
export function matches(label: string, query: string): boolean {
  if (!query) return true;
  const l = label.toLowerCase();
  const q = query.toLowerCase();
  let i = 0;
  for (const ch of l) {
    if (ch === q[i]) i += 1;
    if (i === q.length) return true;
  }
  return false;
}

export function filterCommands(commands: Command[], query: string): Command[] {
  return commands.filter((c) => matches(c.label, query));
}

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}): ReactElement | null {
  const router = useRouter();
  const { t } = useTranslations();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Localize the hard-coded labels via the same translation keys the
  // sidebar uses so Hindi pickup is free.
  const commands = useMemo<Command[]>(() => {
    const tr: Record<string, string> = {
      "new-chat": t("sidebar.newChat"),
      enquiries: t("sidebar.enquiries"),
      "new-enquiry": t("enquiries.new"),
      approvals: t("sidebar.approvals"),
      audit: t("audit.title"),
      profile: t("sidebar.settings"),
      settings: t("sidebar.settings"),
      "sign-out": t("sidebar.signOut"),
    };
    return BASE_COMMANDS.map((c) => ({ ...c, label: tr[c.id] ?? c.label }));
  }, [t]);

  const filtered = useMemo(
    () => filterCommands(commands, query),
    [commands, query],
  );

  // Reset state every time the palette opens.
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      // Defer focus until the modal is actually in the DOM.
      queueMicrotask(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    setSelected(0);
  }, [query]);

  const runCommand = useCallback(
    (cmd: Command) => {
      onClose();
      if (cmd.action.kind === "navigate") {
        router.push(cmd.action.href);
      } else if (cmd.action.kind === "signout") {
        // Match the existing sign-out contract — the web app ships a
        // /sign-out POST endpoint that clears cookies and redirects.
        if (typeof document !== "undefined") {
          const form = document.createElement("form");
          form.method = "POST";
          form.action = "/sign-out";
          document.body.appendChild(form);
          form.submit();
        }
      }
    },
    [onClose, router],
  );

  const onKey = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(s + 1, Math.max(0, filtered.length - 1)));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(0, s - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const cmd = filtered[selected];
        if (cmd) runCommand(cmd);
      }
    },
    [filtered, onClose, runCommand, selected],
  );

  if (!open) return null;

  return (
    <div
      data-testid="command-palette-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(9, 9, 11, 0.45)",
        zIndex: 1000,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: "12vh",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        data-testid="command-palette"
        onKeyDown={onKey}
        style={{
          width: "min(560px, 92vw)",
          background: "#fff",
          borderRadius: 12,
          border: "1px solid #e5e7eb",
          boxShadow:
            "0 20px 50px rgba(0,0,0,0.18), 0 1px 3px rgba(0,0,0,0.08)",
          overflow: "hidden",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("palette.placeholder")}
          aria-label="Command palette search"
          data-testid="command-palette-input"
          style={{
            width: "100%",
            padding: "14px 16px",
            border: "none",
            outline: "none",
            fontSize: 15,
            borderBottom: "1px solid #e5e7eb",
            boxSizing: "border-box",
          }}
        />
        <ul
          role="listbox"
          style={{
            listStyle: "none",
            margin: 0,
            padding: 6,
            maxHeight: 360,
            overflowY: "auto",
          }}
        >
          {filtered.length === 0 ? (
            <li
              data-testid="command-palette-empty"
              style={{ padding: "14px 12px", color: "#71717a", fontSize: 13 }}
            >
              {t("palette.noMatches")}
            </li>
          ) : (
            filtered.map((cmd, i) => (
              <li
                key={cmd.id}
                role="option"
                aria-selected={i === selected}
                data-testid={`command-palette-item-${cmd.id}`}
                onMouseEnter={() => setSelected(i)}
                onClick={() => runCommand(cmd)}
                style={{
                  padding: "10px 12px",
                  borderRadius: 8,
                  cursor: "pointer",
                  background: i === selected ? "#f4f4f5" : "transparent",
                  fontSize: 14,
                  color: "#18181b",
                }}
              >
                {cmd.label}
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}

export default CommandPalette;
