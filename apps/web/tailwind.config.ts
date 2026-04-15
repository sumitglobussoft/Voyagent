import type { Config } from "tailwindcss";

/**
 * Tailwind config for apps/web.
 *
 * Scans the web app's own source AND `packages/chat/src` because the
 * chat package ships Tailwind utility classes in its JSX and relies on
 * the consuming app's Tailwind pipeline to generate the matching CSS.
 * If you add another workspace package that ships Tailwind classes,
 * add its src dir to `content`.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "../../packages/chat/src/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "'Segoe UI'",
          "Roboto",
          "'Helvetica Neue'",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "'SF Mono'",
          "Menlo",
          "Consolas",
          "'Liberation Mono'",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
