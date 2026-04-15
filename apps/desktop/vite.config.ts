import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
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
 *
 * `__APP_VERSION__` / `__BUILD_DATE__` are inlined at build time for the
 * Settings > About panel. They are typed in `src/vite-env.d.ts`.
 */
const pkgJsonUrl = new URL("./package.json", import.meta.url);
const pkg = JSON.parse(readFileSync(fileURLToPath(pkgJsonUrl), "utf-8")) as {
  version?: string;
};

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
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version ?? "0.0.0-dev"),
    __BUILD_DATE__: JSON.stringify(new Date().toISOString()),
  },
});
