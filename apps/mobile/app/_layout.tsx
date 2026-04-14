import { Slot, Stack, Tabs, useRouter, useSegments } from "expo-router";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { useEffect, type ReactElement } from "react";

import { AuthProvider, useAuth } from "../lib/auth";

/**
 * Root layout.
 *
 * Wraps the app in `<AuthProvider>`, which hydrates the session from
 * SecureStore on mount (calling `/api/auth/me`, refreshing if needed).
 * A simple gate below routes between the authed tab stack and the
 * unauthed sign-in/sign-up stack based on `useAuth().user`.
 */
export default function RootLayout(): ReactElement {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  );
}

function AuthGate(): ReactElement {
  const { user, loading } = useAuth();
  const router = useRouter();
  const segments = useSegments();

  useEffect(() => {
    if (loading) return;
    const first = segments[0];
    const inAuthScreen = first === "sign-in" || first === "sign-up";
    if (!user && !inAuthScreen) {
      router.replace("/sign-in");
    } else if (user && inAuthScreen) {
      router.replace("/chat");
    }
  }, [loading, user, segments, router]);

  if (loading) {
    return (
      <View style={styles.container}>
        <ActivityIndicator />
      </View>
    );
  }

  if (!user) {
    return <SignedOutStack />;
  }
  return <AuthedTabs />;
}

function AuthedTabs(): ReactElement {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: "#111",
        headerStyle: { backgroundColor: "#fff" },
        headerTitleStyle: { fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Reports",
          tabBarLabel: "Reports",
          tabBarAccessibilityLabel: "Reports tab",
        }}
      />
      <Tabs.Screen
        name="chat"
        options={{
          title: "Chat",
          tabBarLabel: "Chat",
          tabBarAccessibilityLabel: "Chat tab",
        }}
      />
      <Tabs.Screen
        name="desktop-pair"
        options={{
          title: "Pair desktop",
          tabBarLabel: "Pair",
          tabBarAccessibilityLabel: "Desktop pairing tab",
        }}
      />
      <Tabs.Screen name="sign-in" options={{ href: null }} />
      <Tabs.Screen name="sign-up" options={{ href: null }} />
    </Tabs>
  );
}

function SignedOutStack(): ReactElement {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="sign-in" />
      <Stack.Screen name="sign-up" />
      <Slot />
    </Stack>
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
});
