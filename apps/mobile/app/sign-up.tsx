/**
 * Email-code sign-up via `useSignUp()` from @clerk/clerk-expo.
 *
 * Same two-step shape as sign-in — email first, then verify the code
 * delivered to the inbox. On verification success we call
 * `setActive({ session: createdSessionId })` which activates the new
 * session and `SignedIn>` starts rendering the authed tabs.
 */
import { useSignUp } from "@clerk/clerk-expo";
import { Link, useRouter } from "expo-router";
import { useState, type ReactElement } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

export default function SignUpScreen(): ReactElement {
  const { signUp, setActive, isLoaded } = useSignUp();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"email" | "code">("email");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const startSignUp = async (): Promise<void> => {
    if (!isLoaded) return;
    setBusy(true);
    setErr(null);
    try {
      await signUp.create({ emailAddress: email });
      await signUp.prepareEmailAddressVerification({ strategy: "email_code" });
      setStage("code");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (): Promise<void> => {
    if (!isLoaded) return;
    setBusy(true);
    setErr(null);
    try {
      const attempt = await signUp.attemptEmailAddressVerification({ code });
      if (attempt.status === "complete") {
        await setActive({ session: attempt.createdSessionId });
        router.replace("/");
      } else {
        setErr(`Unexpected status: ${attempt.status}`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Create a Voyagent account</Text>
      {stage === "email" ? (
        <>
          <TextInput
            style={styles.input}
            placeholder="you@agency.com"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            accessibilityLabel="Email address"
            accessibilityHint="Enter the email address to register"
            editable={!busy}
          />
          <Pressable
            style={[styles.button, busy && styles.buttonDisabled]}
            onPress={() => {
              void startSignUp();
            }}
            disabled={busy || email.length === 0}
            accessibilityRole="button"
            accessibilityLabel="Create account"
          >
            <Text style={styles.buttonText}>
              {busy ? "Sending..." : "Send verification code"}
            </Text>
          </Pressable>
        </>
      ) : (
        <>
          <Text style={styles.body}>Enter the code sent to {email}.</Text>
          <TextInput
            style={styles.input}
            placeholder="123456"
            value={code}
            onChangeText={setCode}
            keyboardType="number-pad"
            accessibilityLabel="Verification code"
            accessibilityHint="Enter the 6-digit code from your email"
            editable={!busy}
          />
          <Pressable
            style={[styles.button, busy && styles.buttonDisabled]}
            onPress={() => {
              void verify();
            }}
            disabled={busy || code.length === 0}
            accessibilityRole="button"
            accessibilityLabel="Verify code"
          >
            <Text style={styles.buttonText}>
              {busy ? "Verifying..." : "Verify"}
            </Text>
          </Pressable>
        </>
      )}
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
  body: {
    fontSize: 13,
    color: "#555",
    marginBottom: 12,
    lineHeight: 18,
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
