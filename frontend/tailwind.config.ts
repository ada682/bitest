/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg:      "#0B0F1A",
        surface: "#111827",
        card:    "#151D2E",
        border:  "#1E2D45",
        accent:  "#1D6FD8",
        "accent-dim": "#1A3A6B",
        muted:   "#4B6280",
        text:    "#E2EAF4",
        subtle:  "#8CA4BE",
        success: "#10B981",
        danger:  "#EF4444",
        warning: "#F59E0B",
      },
      fontFamily: {
        sans: ["var(--font-sora)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
