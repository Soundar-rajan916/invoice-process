/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "var(--border)",
        input: "var(--border)",
        ring: "var(--accent)",
        background: "var(--bg-app)",
        foreground: "var(--text)",
        primary: {
          DEFAULT: "var(--accent)",
          foreground: "#ffffff",
        },
        secondary: {
          DEFAULT: "var(--bg-sidebar)",
          foreground: "var(--text)",
        },
        destructive: {
          DEFAULT: "var(--danger)",
          foreground: "#ffffff",
        },
        muted: {
          DEFAULT: "var(--bg-sidebar)",
          foreground: "var(--text-muted)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "#ffffff",
        },
        card: {
          DEFAULT: "var(--bg-card)",
          foreground: "var(--text)",
        },
        // Direct semantic tokens from Findeck design system
        findeck: {
          app: "var(--bg-app)",
          sidebar: "var(--bg-sidebar)",
          card: "var(--bg-card)",
          border: "var(--border)",
          text: "var(--text)",
          muted: "var(--text-muted)",
          accent: "var(--accent)",
          "accent-hover": "var(--accent-hover)",
          "accent-soft": "var(--accent-soft)",
          "accent-soft-border": "var(--accent-soft-border)",
          danger: "var(--danger)",
          "danger-soft": "var(--danger-soft)",
          warning: "var(--warning)",
          "warning-soft": "var(--warning-soft)",
          info: "var(--info)",
          "info-soft": "var(--info-soft)",
        },
      },
      borderRadius: {
        card: "var(--radius-card)",
        btn: "var(--radius-btn)",
        pill: "var(--radius-pill)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: [
          "'Inter Variable'",
          "-apple-system",
          "BlinkMacSystemFont",
          "'Segoe UI'",
          "Roboto",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
}
