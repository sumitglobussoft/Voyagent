import { StyleSheet, Text, View } from "react-native";
import type { ReactElement } from "react";

/**
 * Chat tab placeholder.
 *
 * `@voyagent/chat` is web-first (uses DOM-specific Tailwind primitives).
 * An RN adaptation is tracked separately; until it lands we show a
 * placeholder pointing users at the desktop app.
 *
 * The desktop-pair tab will eventually let this surface remote-control a
 * signed-in desktop session; that's the primary mobile use case.
 */
export default function ChatScreen(): ReactElement {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Agent chat is desktop-first</Text>
      <Text style={styles.body}>
        We're adapting the Voyagent chat UI for mobile. In the meantime,
        open the Voyagent desktop app and pair it from the Pair tab — your
        phone will relay approvals and let you follow the conversation.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    backgroundColor: "#ffffff",
  },
  title: {
    fontSize: 18,
    fontWeight: "600",
    marginBottom: 12,
    color: "#111",
  },
  body: {
    fontSize: 14,
    color: "#555",
    textAlign: "center",
    maxWidth: 420,
    lineHeight: 20,
  },
});
