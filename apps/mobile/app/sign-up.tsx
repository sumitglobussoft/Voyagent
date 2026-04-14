import { Link, useRouter } from "expo-router";
import { useState, type ReactElement } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { useAuth } from "../lib/auth";

export default function SignUpScreen(): ReactElement {
  const { signUp } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [agencyName, setAgencyName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (): Promise<void> => {
    setBusy(true);
    setErr(null);
    try {
      const result = await signUp({
        email: email.trim(),
        password,
        full_name: fullName.trim(),
        agency_name: agencyName.trim(),
      });
      if (result) {
        setErr(
          result.error === "request_failed"
            ? "Something went wrong. Please try again."
            : result.error,
        );
        return;
      }
      router.replace("/chat");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const canSubmit =
    email.length > 0 &&
    password.length > 0 &&
    fullName.length > 0 &&
    agencyName.length > 0 &&
    !busy;

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Create a Voyagent account</Text>
      <TextInput
        style={styles.input}
        placeholder="Full name"
        value={fullName}
        onChangeText={setFullName}
        accessibilityLabel="Full name"
        editable={!busy}
      />
      <TextInput
        style={styles.input}
        placeholder="Agency name"
        value={agencyName}
        onChangeText={setAgencyName}
        accessibilityLabel="Agency name"
        editable={!busy}
      />
      <TextInput
        style={styles.input}
        placeholder="you@agency.com"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        accessibilityLabel="Email address"
        editable={!busy}
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoCapitalize="none"
        accessibilityLabel="Password"
        editable={!busy}
      />
      <Pressable
        style={[styles.button, !canSubmit && styles.buttonDisabled]}
        onPress={() => {
          void submit();
        }}
        disabled={!canSubmit}
        accessibilityRole="button"
        accessibilityLabel="Create account"
      >
        <Text style={styles.buttonText}>
          {busy ? "Creating..." : "Create account"}
        </Text>
      </Pressable>
      {err !== null ? (
        <Text style={styles.error} accessibilityLiveRegion="polite">
          {err}
        </Text>
      ) : null}
      <Link href="/sign-in" style={styles.link}>
        <Text style={styles.linkText}>Already have an account? Sign in</Text>
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    justifyContent: "center",
    backgroundColor: "#ffffff",
  },
  title: {
    fontSize: 22,
    fontWeight: "700",
    color: "#111",
    marginBottom: 16,
  },
  input: {
    height: 44,
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    paddingHorizontal: 12,
    marginBottom: 12,
    fontSize: 14,
    backgroundColor: "#fff",
    color: "#111",
  },
  button: {
    height: 44,
    borderRadius: 8,
    backgroundColor: "#111",
    alignItems: "center",
    justifyContent: "center",
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "600",
  },
  error: {
    color: "#b91c1c",
    fontSize: 12,
    marginTop: 12,
  },
  link: {
    marginTop: 16,
  },
  linkText: {
    color: "#2563eb",
    fontSize: 13,
    textAlign: "center",
  },
});
