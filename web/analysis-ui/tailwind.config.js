/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        surface: "#10131a",
        background: "#10131a",
        "on-surface": "#e1e2eb",
        "on-surface-variant": "#c2c6d6",
        primary: "#adc6ff",
        "primary-container": "#4c8eff",
        "on-primary-container": "#00285d",
        secondary: "#40e56c",
        outline: "#8c909f",
        "outline-variant": "#414754",
        "surface-container": "#1d2026",
        "surface-container-low": "#191c22",
        "surface-container-lowest": "#0b0e14",
        "surface-container-high": "#272a31",
        "surface-container-highest": "#32353c",
        error: "#ffb4ab",
        "error-container": "#93000a",
      },
      fontFamily: {
        headline: ["system-ui", "Segoe UI", "sans-serif"],
        body: ["system-ui", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
