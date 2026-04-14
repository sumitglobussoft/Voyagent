/**
 * React Native approval prompt.
 *
 * The web build uses `role="alertdialog"` — on native we use
 * `accessibilityViewIsModal` + `accessibilityLiveRegion` + an
 * auto-announced label to achieve an equivalent experience for
 * VoiceOver / TalkBack.
 */
import { type ReactElement } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { ApprovalRequest } from "./types.js";

export interface ApprovalPromptProps {
  approval: ApprovalRequest;
  busy: boolean;
  onRespond: (approvalId: string, granted: boolean) => void | Promise<void>;
}

export function ApprovalPrompt(props: ApprovalPromptProps): ReactElement {
  const { approval, busy, onRespond } = props;

  return (
    <View
      style={styles.root}
      accessibilityLiveRegion="polite"
      accessibilityViewIsModal
      accessibilityLabel={`Approval required: ${approval.summary}`}
    >
      <Text style={styles.title}>Approval required</Text>
      <Text style={styles.summary}>{approval.summary}</Text>
      <View style={styles.actions}>
        <Pressable
          style={[styles.approve, busy && styles.disabled]}
          onPress={() => {
            void onRespond(approval.approval_id, true);
          }}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="Approve the agent request"
        >
          <Text style={styles.approveText}>Approve</Text>
        </Pressable>
        <Pressable
          style={[styles.deny, busy && styles.disabled]}
          onPress={() => {
            void onRespond(approval.approval_id, false);
          }}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="Deny the agent request"
        >
          <Text style={styles.denyText}>Deny</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#fbbf24",
    backgroundColor: "#fffbeb",
  },
  title: {
    fontSize: 13,
    fontWeight: "700",
    color: "#78350f",
    marginBottom: 6,
  },
  summary: {
    fontSize: 13,
    color: "#111827",
    marginBottom: 10,
    lineHeight: 18,
  },
  actions: {
    flexDirection: "row",
    gap: 8,
  },
  approve: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 6,
    backgroundColor: "#059669",
    alignItems: "center",
  },
  approveText: {
    color: "#ffffff",
    fontSize: 13,
    fontWeight: "600",
  },
  deny: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 6,
    backgroundColor: "#dc2626",
    alignItems: "center",
  },
  denyText: {
    color: "#ffffff",
    fontSize: 13,
    fontWeight: "600",
  },
  disabled: {
    opacity: 0.5,
  },
});
