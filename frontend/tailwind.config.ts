import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        asx: {
          green: "#00843D",
          dark: "#0A1628",
          card: "#111827",
          border: "#1F2937",
          muted: "#6B7280",
        },
      },
    },
  },
  plugins: [],
};

export default config;
