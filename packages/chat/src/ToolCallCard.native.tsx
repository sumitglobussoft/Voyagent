/**
 * React Native collapsible tool-call card. Same user-visible behaviour as
 * the web build — tap the header to toggle the JSON input/output — but
 * rendered with `Pressable` and scrollable `Text` blocks.
 */
import { useState, type ReactElement } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { ToolCallEntry } from "./types.js";

export interface ToolCallCardProps {
  call: ToolCallEntry;
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function ToolCallCard({ call }: ToolCallCardProps): ReactElement {
  const [open, setOpen] = useState(false);
  const status = call.done ? "done" : "running";

  return (
    <View
      style={styles.card}
      accessibilityRole="summary"
      accessibilityLabel={`Tool call ${call.tool_name}`}
    >
      <Pressable
        style={styles.header}
        onPress={() => setOpen((v) => !v)}
        accessibilityRole="button"
        accessibilityLabel={`Toggle details for ${call.tool_name}`}
        accessibilityState={{ expanded: open }}
      >
        <Text style={styles.headerText}>
          {call.tool_name}
          <Text style={styles.status}> ({status})</Text>
        </Text>
        <Text style={styles.toggle}>{open ? "-" : "+"}</Text>
      </Pressable>
      {open ? (
        <View style={styles.body}>
          <Text style={styles.label}>Input</Text>
          <ScrollView horizontal style={styles.code}>
            <Text style={styles.codeText}>{prettyJson(call.tool_input)}</Text>
          </ScrollView>
          {call.tool_output !== undefined ? (
            <>
              <Text style={styles.label}>Output</Text>
              <ScrollView horizontal style={styles.code}>
                <Text style={styles.codeText}>
                  {prettyJson(call.tool_output)}
                </Text>
              </ScrollView>
            </>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginVertical: 6,
    borderWidth: 1,
    borderColor: "#d4d4d8",
    backgroundColor: "#fafafa",
    borderRadius: 6,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  headerText: {
    fontSize: 13,
    fontFamily: "monospace",
    color: "#111827",
  },
  status: {
    fontSize: 11,
    color: "#6b7280",
    fontFamily: "monospace",
  },
  toggle: {
    fontSize: 14,
    color: "#6b7280",
  },
  body: {
    borderTopWidth: 1,
    borderTopColor: "#e5e7eb",
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 4,
  },
  label: {
    fontSize: 10,
    textTransform: "uppercase",
    letterSpacing: 1,
    color: "#6b7280",
    marginTop: 4,
  },
  code: {
    backgroundColor: "#f4f4f5",
    padding: 6,
    borderRadius: 4,
  },
  codeText: {
    fontFamily: "monospace",
    fontSize: 11,
    color: "#111827",
  },
});
