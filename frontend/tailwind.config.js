/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      // Mirrors the custom properties in src/index.css so one-off utilities
      // can reach the same surface tokens the component classes use.
      colors: {
        chassis: {
          DEFAULT: "#0d0f11",
          high: "#14171a",
        },
        well: {
          DEFAULT: "#000000",
          raise: "#0a0c0e",
        },
      },
      borderColor: {
        rule: "rgba(255,255,255,0.07)",
        edge: "rgba(255,255,255,0.09)",
      },
      fontFamily: {
        sans: [
          "IBM Plex Sans",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "IBM Plex Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
