/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0a0b0e", 900: "#0f1116", 850: "#13151b", 800: "#181b22", 700: "#222631", 600: "#2e3340" },
        accent: { DEFAULT: "#8b8dff", dim: "#5b5ee0" },
        sev: { high: "#ff6b7a", medium: "#f5b84b", low: "#6bb8ff" },
      },
      fontFamily: {
        sans: ['"Inter"', "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        mono: ['"JetBrains Mono"', '"Cascadia Code"', "ui-monospace", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
