# @voyagent/chat

React chat UI for the Voyagent agent runtime. Renders an accessible
streaming-agent transcript with human-in-the-loop approval prompts, backed
by `@voyagent/sdk`.

## Install

Workspace-linked from the monorepo root:

```json
"dependencies": {
  "@voyagent/chat": "workspace:*",
  "@voyagent/sdk": "workspace:*"
}
```

Peer deps: `react@^19`, `react-dom@^19`.

## Minimum markup

```tsx
"use client";
import { ChatWindow } from "@voyagent/chat";
import { VoyagentClient } from "@voyagent/sdk";

const client = new VoyagentClient({
  baseUrl: process.env.NEXT_PUBLIC_VOYAGENT_API_URL ?? "http://localhost:8000",
});

export default function ChatPage() {
  return (
    <main className="h-dvh">
      <ChatWindow
        client={client}
        tenantId="demo-tenant"
        actorId="demo-actor"
      />
    </main>
  );
}
```

`<ChatWindow>` handles session creation on mount if you don't pass
`sessionId`.

## Host with your own layout

Use the `useAgentStream` hook and compose the primitives yourself:

```tsx
"use client";
import { useAgentStream, MessageList, ComposerBar, ApprovalPrompt } from "@voyagent/chat";

export function MyChat({ client, sessionId }: { client: VoyagentClient; sessionId: string }) {
  const s = useAgentStream({ client, sessionId });
  return (
    <>
      <MessageList messages={s.messages} />
      {s.pendingApprovals[0] ? (
        <ApprovalPrompt approval={s.pendingApprovals[0]} busy={s.isStreaming} onRespond={s.respondToApproval} />
      ) : null}
      <ComposerBar disabled={s.isStreaming} onSubmit={(t) => s.send(t)} />
    </>
  );
}
```

## Approval flow

When the runtime emits an `approval_request` event it stops producing events
for the turn. `useAgentStream` surfaces the request via `pendingApprovals`
and the composer disables itself. Calling `respondToApproval(id, granted)`
opens a new SSE stream with body `{ message: "", approvals: { [id]: granted } }`
and the orchestrator resumes the turn.

## Accessibility

- Message list uses `role="log"` + `aria-live="polite"` so screen readers
  announce streaming text without stealing focus.
- Approval prompts render inside `role="alertdialog"` and autofocus the
  Approve button on mount; Tab reaches Deny.
- All interactive controls are real `<button>` / `<textarea>` elements and
  respond to keyboard activation (Enter/Space / Cmd+Enter to send).
- The composer is disabled while streaming or when approvals are pending —
  `disabled` state is reflected both visually and via the `disabled`
  attribute so assistive tech skips it.

## Styling

Components ship with minimal Tailwind utility classes. Host apps are
expected to have Tailwind configured (see `packages/config/tailwind/preset`).
If you don't use Tailwind, import `@voyagent/chat/styles.css` for baseline
layout styles and override as needed.
