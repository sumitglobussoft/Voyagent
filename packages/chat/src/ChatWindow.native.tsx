/**
 * React Native build of the top-level chat container.
 *
 * Responsibilities are identical to the web variant — session bootstrap,
 * `useAgentStream` wiring, approval handling — only the rendering uses
 * `View`, `Text`, `SafeAreaView` instead of DOM elements. Styles come from
 * `StyleSheet.create` so we stay off of Tailwind / CSS on native.
 */
import { useEffect, useState, type ReactElement } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type { VoyagentClient } from "@voyagent/sdk";

import { ApprovalPrompt } from "./ApprovalPrompt.native.js";
import { ComposerBar } from "./ComposerBar.native.js";
import { MessageList } from "./MessageList.native.js";
import { useAgentStream } from "./useAgentStream.js";

export interface ChatWindowProps {
  client: VoyagentClient;
  sessionId?: string;
  tenantId: string;
  actorId: string;
}

export function ChatWindow(props: ChatWindowProps): ReactElement {
  const { client, tenantId, actorId } = props;
  const [sessionId, setSessionId] = useState<string | null>(
    props.sessionId && props.sessionId.length > 0 ? props.sessionId : null,
  );
  const [initError, setInitError] = useState<Error | null>(null);

  useEffect(() => {
    if (sessionId !== null) return;
    let cancelled = false;
    (async () => {
      try {
        const { session_id } = await client.createSession({
          tenant_id: tenantId,
          actor_id: actorId,
        });
        if (!cancelled) setSessionId(session_id);
      } catch (err) {
        if (!cancelled) {
          setInitError(err instanceof Error ? err : new Error(String(err)));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [actorId, client, sessionId, tenantId]);

  if (initError) {
    return (
      <View
        style={styles.alert}
        accessibilityRole="alert"
        accessibilityLiveRegion="polite"
      >
        <Text style={styles.alertText}>
          Failed to initialize chat session: {initError.message}
        </Text>
      </View>
    );
  }

  if (sessionId === null) {
    return (
      <View style={styles.loading} accessibilityLiveRegion="polite">
        <ActivityIndicator accessibilityLabel="Starting session" />
        <Text style={styles.loadingText}>Starting session...</Text>
      </View>
    );
  }

  return <ChatBody client={client} sessionId={sessionId} />;
}

function ChatBody({
  client,
  sessionId,
}: {
  client: VoyagentClient;
  sessionId: string;
}): ReactElement {
  const stream = useAgentStream({ client, sessionId });

  const disabled = stream.isStreaming || stream.pendingApprovals.length > 0;
  const disabledReason = stream.isStreaming
    ? "Agent is responding..."
    : stream.pendingApprovals.length > 0
      ? "Resolve the pending approval first."
      : undefined;

  const headApproval = stream.pendingApprovals[0];

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <MessageList messages={stream.messages} />
      {headApproval !== undefined ? (
        <ApprovalPrompt
          approval={headApproval}
          busy={stream.isStreaming}
          onRespond={stream.respondToApproval}
        />
      ) : null}
      {stream.error !== null ? (
        <View style={styles.alert} accessibilityRole="alert">
          <Text style={styles.alertText}>{stream.error.message}</Text>
        </View>
      ) : null}
      <ComposerBar
        disabled={disabled}
        disabledReason={disabledReason}
        onSubmit={async (text) => {
          await stream.send(text);
        }}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#ffffff",
  },
  alert: {
    marginHorizontal: 12,
    marginVertical: 8,
    padding: 10,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "#fca5a5",
    backgroundColor: "#fef2f2",
  },
  alertText: {
    fontSize: 12,
    color: "#991b1b",
  },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#ffffff",
  },
  loadingText: {
    fontSize: 13,
    color: "#6b7280",
    marginTop: 8,
  },
});
