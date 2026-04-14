/**
 * Email-code sign-in via `useSignIn()` from @clerk/clerk-expo.
 *
 * Two-step flow:
 *   1. User enters email. We call `signIn.create({ identifier })` then
 *      `prepareFirstFactor({ strategy: "email_code" })`.
 *   2. User enters the 6-digit code from their inbox. We call
 *      `attemptFirstFactor({ strategy: "email_code", code })` and, on
 *      success, `setActive({ session })` to activate the session.
 *
 * Clerk handles token rotation and the Keychain write via the tokenCache
 * we plumbed in `_layout.tsx`.
 */
import { useSignIn } from "@clerk/clerk-expo";
import { Link, useRouter } from "expo-router";
import { useState, type ReactElement } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

export default function SignInScreen(): ReactElement {
  const { signIn, setActive, isLoaded } = useSignIn();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"email" | "code">("email");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submitEmail = async (): Promise<void> => {
    if (!isLoaded) return;
    setBusy(true);
    setErr(null);
    try {
      await signIn.create({ identifier: email });
      const emailFactor = signIn.supportedFirstFactors?.find(
        (f) => f.strategy === "email_code",
      );
      if (!emailFactor || emailFactor.strategy !== "email_code") {
        throw new Error("Email-code sign-in isn't enabled on this instance.");
      }
      await signIn.prepareFirstFactor({
        strategy: "email_code",
        emailAddressId: emailFactor.emailAddressId,
      });
      setStage("code");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (): Promise<void> => {
    if (!isLoaded) return;
    setBusy(true);
    setErr(null);
    try {
      const attempt = await signIn.attemptFirstFactor({
        strategy: "email_code",
        code,
      });
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
      <Text style={styles.title}>Sign in to Voyagent</Text>
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
            accessibilityHint="Enter the email you sign in with"
            editable={!busy}
          />
          <Pressable
            style={[styles.button, busy && styles.buttonDisabled]}
            onPress={() => {
              void submitEmail();
            }}
            disabled={busy || email.length === 0}
            accessibilityRole="button"
            accessibilityLabel="Send sign-in code"
          >
            <Text style={styles.buttonText}>
              {busy ? "Sending..." : "Send code"}
            </Text>
          </Pressable>
        </>
      ) : (
        <>
          <Text style={styles.body}>
            We sent a 6-digit code to {email}. Enter it below.
          </Text>
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
              void submitCode();
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
      <Link href="/sign-up" style={styles.link}>
        <Text style={styles.linkText}>New here? Create an account</Text>
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
