/**
 * Marketing-site favicon. Dark-grey Voyagent "V" on a white background —
 * higher contrast against the light marketing chrome than the gradient
 * used on the app surface.
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
          background: "#ffffff",
          color: "#18181b",
          fontSize: 24,
          fontWeight: 700,
          letterSpacing: -1,
          fontFamily: "system-ui, sans-serif",
          borderRadius: 4,
        }}
      >
        V
      </div>
    ),
    { ...size },
  );
}
