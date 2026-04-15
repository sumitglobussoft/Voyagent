/**
 * Dynamic 32x32 favicon — renders the Voyagent "V" wordmark in the
 * same black-to-dark-grey gradient used by the chat empty-state badge.
 *
 * Next 15 generates the PNG on demand and serves it from `/icon` (plus
 * the usual `<link rel="icon">` injected into `<head>` automatically).
 */
import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(135deg, #18181b 0%, #3f3f46 100%)",
          borderRadius: 6,
          color: "#fafafa",
          fontSize: 22,
          fontWeight: 700,
          letterSpacing: -1,
          fontFamily: "system-ui, sans-serif",
        }}
      >
        V
      </div>
    ),
    { ...size },
  );
}
