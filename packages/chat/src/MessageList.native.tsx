/**
 * React Native message transcript.
 *
 * Uses `FlatList` for windowed rendering — important on mobile where long
 * transcripts would crush layout if rendered in a plain `<ScrollView>`.
 * Accessibility mirrors the web build: the list itself has
 * `accessibilityRole="list"` and each bubble is a `listitem`.
 */
import { useEffect, useRef, type ReactElement } from "react";
import {
  FlatList,
  StyleSheet,
  Text,
  View,
  type ListRenderItem,
} from "react-native";

import { ToolCallCard } from "./ToolCallCard.native.js";
import type { ChatMessage } from "./types.js";

export interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps): ReactElement {
  const listRef = useRef<FlatList<ChatMessage> | null>(null);

  useEffect(() => {
    if (messages.length === 0) return;
    listRef.current?.scrollToEnd({ animated: true });
  }, [messages.length]);

  const renderItem: ListRenderItem<ChatMessage> = ({ item }) =>
    item.kind === "user" ? (
      <UserBubble text={item.text} />
    ) : (
      <AssistantBubble message={item} />
    );

  return (
    <FlatList
      ref={listRef}
      data={messages}
      keyExtractor={(m) => m.id}
      renderItem={renderItem}
      contentContainerStyle={styles.listContent}
      accessibilityRole="list"
      accessibilityLabel="Agent conversation"
      accessibilityLiveRegion="polite"
    />
  );
}

function UserBubble({ text }: { text: string }): ReactElement {
  return (
    <View style={styles.userRow} accessibilityRole="text">
      <View style={styles.userBubble}>
        <Text style={styles.userText}>{text}</Text>
      </View>
    </View>
  );
}

function AssistantBubble({
  message,
}: {
  message: Extract<ChatMessage, { kind: "assistant" }>;
}): ReactElement {
  return (
    <View style={styles.assistantRow}>
      <View style={styles.assistantBubble}>
        {message.text.length > 0 ? (
          <Text style={styles.assistantText}>{message.text}</Text>
        ) : null}
        {message.toolCalls.map((call) => (
          <ToolCallCard key={call.tool_call_id} call={call} />
        ))}
        {message.error !== undefined ? (
          <View style={styles.assistantError} accessibilityRole="alert">
            <Text style={styles.assistantErrorText}>{message.error}</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  listContent: {
    padding: 12,
    gap: 8,
  },
  userRow: {
    alignItems: "flex-end",
  },
  userBubble: {
    maxWidth: "80%",
    backgroundColor: "#111",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
    marginVertical: 4,
  },
  userText: {
    color: "#f9fafb",
    fontSize: 14,
  },
  assistantRow: {
    alignItems: "flex-start",
  },
  assistantBubble: {
    maxWidth: "90%",
    backgroundColor: "#f5f5f5",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
    marginVertical: 4,
  },
  assistantText: {
    color: "#111827",
    fontSize: 14,
    lineHeight: 20,
  },
  assistantError: {
    marginTop: 6,
    padding: 6,
    backgroundColor: "#fef2f2",
    borderRadius: 4,
  },
  assistantErrorText: {
    color: "#991b1b",
    fontSize: 11,
  },
});
