// Voyagent Tailwind preset.
//
// Defines the shared design-token scaffold. Apps supply their own `content`
// globs; everything else (colors, fonts) inherits from here so surfaces stay
// visually consistent.

/** @type {import("tailwindcss").Config} */
const preset = {
  content: [],
  theme: {
    extend: {
      colors: {
        voyagent: {
          ink: "hsl(222 47% 11%)",
          paper: "hsl(0 0% 100%)",
          accent: "hsl(262 83% 58%)",
          muted: "hsl(215 16% 47%)",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default preset;
