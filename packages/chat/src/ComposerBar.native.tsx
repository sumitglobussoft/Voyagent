/**
 * React Native composer. `TextInput` + `Pressable` substitute for the web
 * `<textarea>` / `<button>`. The web keyboard shortcut (Cmd/Ctrl+Enter)
 * becomes `returnKeyType="send"` + `onSubmitEditing` on native.
 */
import { useCallback, useState, type ReactElement } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

export interface ComposerBarProps {
  disabled: boolean;
  disabledReason?: string;
  onSubmit: (text: string) => void | Promise<void>;
  placeholder?: string;
}

export function ComposerBar(props: ComposerBarProps): ReactElement {
  const {
    disabled,
    disabledReason,
    onSubmit,
    placeholder = "Message the agent...",
  } = props;
  const [value, setValue] = useState("");

  const submit = useCallback(async () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    setValue("");
    await onSubmit(trimmed);
  }, [disabled, onSubmit, value]);

  const sendDisabled = disabled || value.trim().length === 0;

  return (
    <View style={styles.row}>
      <TextInput
        style={[styles.input, disabled && styles.inputDisabled]}
        value={value}
        onChangeText={setValue}
        editable={!disabled}
        placeholder={disabled && disabledReason ? disabledReason : placeholder}
        placeholderTextColor="#9ca3af"
        multiline
        numberOfLines={2}
        returnKeyType="send"
        blurOnSubmit
        onSubmitEditing={() => {
          void submit();
        }}
        accessibilityLabel="Message input"
        accessibilityHint="Type a message to the agent and press send"
      />
      <Pressable
        style={[styles.button, sendDisabled && styles.buttonDisabled]}
        onPress={() => {
          void submit();
        }}
        disabled={sendDisabled}
        accessibilityRole="button"
        accessibilityLabel="Send message"
        accessibilityHint={disabledReason}
      >
        <Text style={styles.buttonText}>Send</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 8,
    padding: 8,
    borderTopWidth: 1,
    borderTopColor: "#e5e7eb",
    backgroundColor: "#ffffff",
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    borderWidth: 1,
    borderColor: "#d4d4d8",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 14,
    color: "#111827",
    backgroundColor: "#ffffff",
  },
  inputDisabled: {
    backgroundColor: "#f4f4f5",
    color: "#6b7280",
  },
  button: {
    height: 40,
    paddingHorizontal: 14,
    borderRadius: 8,
    backgroundColor: "#111",
    alignItems: "center",
    justifyContent: "center",
  },
  buttonDisabled: {
    backgroundColor: "#9ca3af",
  },
  buttonText: {
    color: "#f9fafb",
    fontSize: 13,
    fontWeight: "600",
  },
});
