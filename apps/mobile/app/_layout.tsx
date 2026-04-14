import { Tabs } from "expo-router";
import type { ReactElement } from "react";

/**
 * Root layout — an Expo Router Tabs navigator.
 *
 * Three tabs today: Reports (default), Chat, Desktop pair. Icons are kept
 * as emoji placeholders to avoid pulling a native icon library into this
 * skeleton; they'll be replaced with proper @voyagent/icons glyphs once
 * the RN icon story lands.
 */
export default function RootLayout(): ReactElement {
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
    </Tabs>
  );
}
