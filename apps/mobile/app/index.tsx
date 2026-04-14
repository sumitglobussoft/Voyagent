import { StyleSheet, Text, View } from "react-native";
import type { ReactElement } from "react";

/**
 * Reports tab placeholder.
 *
 * v1 will surface Tally-backed receivables, payables, and itinerary
 * summaries pulled from the Voyagent API. Keeping this as a static
 * placeholder until the reports endpoints ship.
 */
export default function ReportsScreen(): ReactElement {
  return (
    <View style={styles.container} accessibilityRole="summary">
      <Text style={styles.title}>Reports</Text>
      <Text style={styles.body}>
        Reports are coming soon. You'll see receivables, payables, and
        itinerary summaries here once the Voyagent reports API lands.
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
    fontSize: 20,
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
