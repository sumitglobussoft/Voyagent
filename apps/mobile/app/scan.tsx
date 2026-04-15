import React from "react";
import { StyleSheet, View } from "react-native";
import PassportScanner from "../components/PassportScanner";

/**
 * Passport scan screen. Hosted at /scan — not a tab today (the app
 * uses stack routes, not a tab layout), so this is reachable via
 * router.push("/scan") from the reports or pair surfaces once they
 * need it.
 */
export default function ScanScreen() {
  return (
    <View style={styles.container}>
      <PassportScanner />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
});
