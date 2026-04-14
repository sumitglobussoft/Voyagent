import { StyleSheet, Text, View } from "react-native";
import type { ReactElement } from "react";

/**
 * Desktop pairing placeholder.
 *
 * Real pairing will scan a QR code emitted by the desktop app (a short
 * one-time code signed by the Voyagent backend), establish a channel via
 * the backend's relay, and then surface approvals / chat transcripts on
 * the phone. Not implemented in this skeleton.
 *
 * TODO: integrate `expo-barcode-scanner` or `expo-camera` for QR scanning;
 * wire through the pairing endpoint on @voyagent/sdk once it exists.
 */
export default function DesktopPairScreen(): ReactElement {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Pair with your desktop</Text>
      <Text style={styles.body}>
        Open the Voyagent desktop app, go to Settings, and scan the QR
        code with this screen. Once paired, approvals from the agent will
        appear here so you can respond from your phone.
      </Text>
      <View style={styles.placeholder} accessibilityRole="image">
        <Text style={styles.placeholderText}>QR scanner coming soon</Text>
      </View>
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
    marginBottom: 24,
    lineHeight: 20,
  },
  placeholder: {
    width: 240,
    height: 240,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#ddd",
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#fafafa",
  },
  placeholderText: {
    fontSize: 12,
    color: "#888",
  },
});
