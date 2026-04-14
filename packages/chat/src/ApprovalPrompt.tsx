"use client";

/**
 * Blocking approval prompt. Rendered whenever `pendingApprovals` is non-empty.
 * Autofocuses the Approve button so keyboard operators can Enter/Space
 * through quickly; the Deny button is reachable via Tab.
 */
import { useEffect, useRef, type ReactElement } from "react";

import type { ApprovalRequest } from "./types.js";

export interface ApprovalPromptProps {
  approval: ApprovalRequest;
  busy: boolean;
  onRespond: (approvalId: string, granted: boolean) => void | Promise<void>;
}

export function ApprovalPrompt(props: ApprovalPromptProps): ReactElement {
  const { approval, busy, onRespond } = props;
  const approveRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    approveRef.current?.focus();
  }, [approval.approval_id]);

  return (
    <div
      role="alertdialog"
      aria-modal="false"
      aria-labelledby={`approval-${approval.approval_id}-title`}
      className="mx-4 mb-3 rounded border border-amber-400 bg-amber-50 p-3"
    >
      <div
        id={`approval-${approval.approval_id}-title`}
        className="mb-2 text-sm font-semibold text-amber-900"
      >
        Approval required
      </div>
      <p className="mb-3 text-sm text-neutral-800 whitespace-pre-wrap">
        {approval.summary}
      </p>
      <div className="flex gap-2">
        <button
          ref={approveRef}
          type="button"
          disabled={busy}
          onClick={() => {
            void onRespond(approval.approval_id, true);
          }}
          className="rounded bg-emerald-600 px-3 py-1.5 text-sm text-white disabled:bg-neutral-400"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            void onRespond(approval.approval_id, false);
          }}
          className="rounded bg-red-600 px-3 py-1.5 text-sm text-white disabled:bg-neutral-400"
        >
          Deny
        </button>
      </div>
    </div>
  );
}
