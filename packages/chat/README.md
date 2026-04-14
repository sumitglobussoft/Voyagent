# @voyagent/chat

React chat UI for the Voyagent agent runtime. Renders an accessible
streaming-agent transcript with human-in-the-loop approval prompts, backed
by `@voyagent/sdk`.

Ships **two builds**:

- **Web** (`dist/index.js`) — the DOM + Tailwind variant consumed by
  `apps/web` and `apps/desktop`.
- **React Native** (`dist/index.native.js`) — the `View` / `FlatList` /
  `TextInput` variant consumed by `apps/mobile`.

Both builds expose the same public surface — `ChatWindow`, `MessageList`,
`ComposerBar`, `ToolCallCard`, `ApprovalPrompt`, and the `useAgentStream`
hook — so hosts don't branch on platform.

## Install

Workspace-linked from the monorepo root:

```json
"dependencies": {
  "@voyagent/chat": "workspace:*",
  "@voyagent/sdk": "workspace:*"
}
```

Peer deps:

- `react@^19`
- `react-dom@^19` (optional; only needed on web)
- `react-native@*` (optional; only needed on native)

## Platform resolution

`package.json#exports` uses conditional subpath exports:

```json
{
  ".": {
    "types": "./dist/index.d.ts",
    "react-native": "./dist/index.native.js",
    "default": "./dist/index.js"
  }
}
```

Metro picks `dist/index.native.js` via the `react-native` condition;
everything else (Vite, Next.js, Node) falls through to `dist/index.js`.
That web entry imports from `*.web.js` component files, the native entry
imports from `*.native.js` — a single `tsc -p tsconfig.build.json` pass
compiles both entries out of the same `src/` tree.

The hook (`useAgentStream`) and the types are platform-agnostic and
shared verbatim between the two entries.

## Minimum markup (web)

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

## Minimum markup (React Native)

```tsx
import { ChatWindow } from "@voyagent/chat";
import { View } from "react-native";
import { useVoyagentClient } from "../lib/sdk";

export default function ChatScreen() {
  const client = useVoyagentClient();
  return (
    <View style={{ flex: 1 }}>
      <ChatWindow client={client} tenantId="demo-tenant" actorId="demo-actor" />
    </View>
  );
}
```

`<ChatWindow>` handles session creation on mount if you don't pass
`sessionId`.

## Prop parity

The component props are identical on both platforms — same names, same
types. Only the rendering primitives and styling layer differ:

| Surface          | Web                             | Native                               |
| ---------------- | ------------------------------- | ------------------------------------ |
| `ChatWindow`     | `div`, Tailwind                 | `View` + `KeyboardAvoidingView`      |
| `MessageList`    | `div` + `scrollIntoView`        | `FlatList` + `scrollToEnd`           |
| `ComposerBar`    | `<textarea>` + Cmd/Ctrl+Enter   | `TextInput` + `returnKeyType="send"` |
| `ApprovalPrompt` | `role="alertdialog"` + autofocus | `accessibilityViewIsModal`           |
| `ToolCallCard`   | `<button>` + `<pre>`            | `Pressable` + horizontal `ScrollView`|

## Approval flow

When the runtime emits an `approval_request` event it stops producing events
for the turn. `useAgentStream` surfaces the request via `pendingApprovals`
and the composer disables itself. Calling `respondToApproval(id, granted)`
opens a new SSE stream with body `{ message: "", approvals: { [id]: granted } }`
and the orchestrator resumes the turn.

## Accessibility

- Message list uses `role="log"` (web) / `accessibilityRole="list"` (native)
  with a polite live region so streaming text is announced without stealing
  focus.
- Approval prompts announce via `role="alertdialog"` on web and
  `accessibilityViewIsModal` on native.
- Every native touchable has `accessibilityLabel`; `TextInput` has
  `accessibilityHint`.
- The composer is disabled while streaming or when approvals are pending —
  that state is exposed both visually and via `disabled` / `editable`.

## Styling

- Web: minimal Tailwind utility classes. Host apps are expected to have
  Tailwind configured (see `packages/config/tailwind/preset`). Import
  `@voyagent/chat/styles.css` for baseline layout if you don't use
  Tailwind.
- Native: plain `StyleSheet.create`. No runtime styling dependency. The
  mobile build trades visual parity for reliability; dial it in later
  when the design system lands on native.
