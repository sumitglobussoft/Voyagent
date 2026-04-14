import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Vite config for the Tauri shell.
 *
 * Tauri expects:
 *   - a fixed dev-server port (we match `tauri.conf.json`'s `build.devUrl`);
 *   - output at `dist/` relative to the web root (matches `frontendDist`).
 *
 * `clearScreen: false` keeps Rust compiler output visible when `tauri dev`
 * runs Vite as a subprocess.
 */
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    target: "esnext",
    sourcemap: true,
  },
});
