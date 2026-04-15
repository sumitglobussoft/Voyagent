import React, { useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Button,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
// expo-camera is a standard Expo module. `CameraView` is the v15+ API.
import { CameraView, useCameraPermissions } from "expo-camera";
import {
  extractPassport,
  type PassportFields,
  type CameraCapturedPicture,
} from "../lib/ocr";

/**
 * Passport scanner component.
 *
 * Opens the rear camera, lets the user snap a photo of a passport, and
 * runs the OCR helper against the capture. In v0 the OCR helper is
 * stubbed; this component's job is to wire the UX so that replacing the
 * stub with a real provider is a one-line change.
 *
 * TODO: `onSave` currently logs the extracted fields. When the
 * passenger-record API lands, call it from here (or lift the save into
 * the parent screen).
 */
export default function PassportScanner() {
  const [permission, requestPermission] = useCameraPermissions();
  // The camera ref is loosely typed — expo-camera's generated types
  // vary between minor versions, and we only touch takePictureAsync.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cameraRef = useRef<any>(null);
  const [busy, setBusy] = useState(false);
  const [fields, setFields] = useState<PassportFields | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!permission) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.centered}>
        <Text style={styles.body}>
          Voyagent needs camera access to scan passports.
        </Text>
        <Button title="Grant camera permission" onPress={requestPermission} />
      </View>
    );
  }

  async function onCapture() {
    if (!cameraRef.current) return;
    setBusy(true);
    setError(null);
    try {
      const photo: CameraCapturedPicture =
        await cameraRef.current.takePictureAsync({ quality: 0.8 });
      const result = await extractPassport(photo);
      if (result.ok && result.fields) {
        setFields(result.fields);
      } else {
        setError(result.error ?? "unknown_error");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function onRetry() {
    setFields(null);
    setError(null);
  }

  function onSave() {
    if (!fields) return;
    // TODO: POST to the passenger-record API once it lands. For v0 we
    // log and surface a confirmation — the screen's parent can lift
    // this into real state when the API is wired.
    // eslint-disable-next-line no-console
    console.log("[PassportScanner] save", fields);
    Alert.alert(
      "Saved (stub)",
      `Captured passport for ${fields.given_names} ${fields.surname}. The real save-to-API call is a follow-up.`,
    );
  }

  if (fields) {
    return (
      <ScrollView contentContainerStyle={styles.formContainer}>
        <Text style={styles.heading}>Review extracted fields</Text>
        <LabeledField label="Surname" value={fields.surname} />
        <LabeledField label="Given names" value={fields.given_names} />
        <LabeledField label="Document number" value={fields.document_number} />
        <LabeledField label="Nationality" value={fields.nationality} />
        <LabeledField label="Date of birth" value={fields.date_of_birth} />
        <LabeledField label="Sex" value={fields.sex} />
        <LabeledField label="Expiration" value={fields.expiration_date} />
        <View style={styles.buttonRow}>
          <Button title="Retry" onPress={onRetry} />
          <Button title="Save to passenger record" onPress={onSave} />
        </View>
      </ScrollView>
    );
  }

  if (error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.heading}>OCR failed</Text>
        <Text style={styles.body}>{error}</Text>
        <Button title="Retry" onPress={onRetry} />
      </View>
    );
  }

  return (
    <View style={styles.cameraContainer}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back" />
      <View style={styles.captureBar}>
        {busy ? (
          <ActivityIndicator />
        ) : (
          <Button title="Capture passport" onPress={onCapture} />
        )}
      </View>
    </View>
  );
}

function LabeledField({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput style={styles.fieldInput} value={value} editable />
    </View>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  cameraContainer: { flex: 1 },
  camera: { flex: 1 },
  captureBar: {
    padding: 16,
    backgroundColor: "#000",
    alignItems: "center",
  },
  formContainer: { padding: 16, gap: 12 },
  heading: { fontSize: 18, fontWeight: "600" },
  body: { fontSize: 14, textAlign: "center" },
  field: { gap: 4 },
  fieldLabel: { fontSize: 12, color: "#666" },
  fieldInput: {
    borderWidth: 1,
    borderColor: "#ccc",
    borderRadius: 6,
    padding: 8,
    fontSize: 14,
  },
  buttonRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 16,
  },
});
