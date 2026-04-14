import { ChatWindow } from "@voyagent/chat";
import { StyleSheet, View } from "react-native";
import type { ReactElement } from "react";

import { actorId, tenantId, useVoyagentClient } from "../lib/sdk";

/**
 * Chat tab — renders the RN build of `@voyagent/chat` against a Voyagent
 * client wired to the current Clerk session. Metro's platform-extension
 * resolution picks `ChatWindow.native.tsx` automatically thanks to the
 * `react-native` conditional export in the package's `exports` map.
 */
export default function ChatScreen(): ReactElement {
  const client = useVoyagentClient();
  return (
    <View style={styles.container}>
      <ChatWindow client={client} tenantId={tenantId} actorId={actorId} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#ffffff",
  },
});
