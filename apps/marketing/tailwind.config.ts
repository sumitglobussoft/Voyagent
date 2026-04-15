import type { Config } from "tailwindcss";
import preset from "@voyagent/config/tailwind/preset";

/**
 * Marketing-site Tailwind config.
 *
 * Extends the shared Voyagent preset with a marketing-only design system:
 *   - `primary`  — deep teal-blue, the product's signature color.
 *   - `accent`   — warm amber used sparingly for CTAs and highlights.
 *   - `ink`/`paper`/`muted` mirror the shared tokens so component-library
 *     primitives imported from `@voyagent/ui` stay visually coherent.
 *
 * Everything is exposed as CSS custom properties in `app/globals.css` so a
 * future dark-mode flip only requires toggling the variable block.
 */
const config: Config = {
  darkMode: "class",
  presets: [preset as Partial<Config>],
  content: ["./src/**/*.{ts,tsx,md,mdx}", "./app/**/*.{ts,tsx,md,mdx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#0B4F71",
          50: "#F0F7FB",
          100: "#D9EAF3",
          200: "#B3D4E6",
          300: "#7FB3D1",
          400: "#4A8AB4",
          500: "#0B4F71",
          600: "#093E5A",
          700: "#072F45",
          800: "#052231",
          900: "#03161F",
        },
        accent: {
          DEFAULT: "#F59E0B",
          50: "#FFF8EB",
          100: "#FEEDC7",
          200: "#FDDA8A",
          300: "#FBC04D",
          400: "#F59E0B",
          500: "#D98706",
          600: "#B06B04",
          700: "#854F03",
        },
      },
      backgroundImage: {
        "hero-glow":
          "radial-gradient(60% 50% at 50% 0%, rgba(11,79,113,0.18) 0%, rgba(11,79,113,0) 70%)",
        "soft-gradient":
          "linear-gradient(180deg, rgba(11,79,113,0.04) 0%, rgba(255,255,255,0) 100%)",
      },
      maxWidth: {
        prose: "720px",
        shell: "1200px",
      },
      letterSpacing: {
        tighter: "-0.02em",
      },
      boxShadow: {
        "soft-lg": "0 20px 60px -20px rgba(11,79,113,0.25)",
        "soft-md": "0 10px 30px -10px rgba(11,79,113,0.15)",
      },
      keyframes: {
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
      animation: {
        marquee: "marquee 40s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
