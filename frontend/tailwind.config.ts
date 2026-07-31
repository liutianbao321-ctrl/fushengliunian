import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1e1b16",
        mist: "#f5efe4",
        wine: "#6f2f24",
        moss: "#60705f",
        gold: "#c7943f",
        bark: "#8e6d4e",
      },
      fontFamily: {
        display: ["Georgia", "Songti SC", "serif"],
        body: ["ui-sans-serif", "system-ui", "PingFang SC", "sans-serif"],
      },
      boxShadow: {
        paper: "0 25px 80px rgba(49, 33, 18, 0.12)",
      },
    },
  },
  plugins: [],
};

export default config;
