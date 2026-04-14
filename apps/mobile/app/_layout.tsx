import { ClerkProvider, SignedIn, SignedOut } from "@clerk/clerk-expo";
import { Slot, Stack, Tabs } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import type { ReactElement } from "react";

import { tokenCache } from "../lib/tokenCache";

/**
 * Root layout.
 *
 * Wraps the app in `<ClerkProvider>` configured with the Expo secure-store
 * `tokenCache`. The auth state then decides which navigator mounts:
 *
 *  - `<SignedIn>`: the three-tab product chrome (Reports / Chat / Pair).
 *  - `<SignedOut>`: a tiny Stack that renders `sign-in` / `sign-up`.
 */
export default function RootLayout(): ReactElement {
  const publishableKey = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY;

  if (!publishableKey) {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Configuration missing</Text>
        <Text style={styles.body}>
          Set EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY in apps/mobile/.env.local
          then restart the Expo dev server.
        </Text>
      </View>
    );
  }

  return (
    <ClerkProvider publishableKey={publishableKey} tokenCache={tokenCache}>
      <SignedIn>
        <AuthedTabs />
      </SignedIn>
      <SignedOut>
        <SignedOutStack />
      </SignedOut>
    </ClerkProvider>
  );
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
      {/* Hide auth screens from the tab bar when signed in. */}
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
  title: {
    fontSize: 18,
    fontWeight: "600",
    marginBottom: 12,
    color: "#111",
  },
  body: {
    fontSize: 13,
    color: "#555",
    textAlign: "center",
    maxWidth: 420,
    lineHeight: 20,
  },
});
