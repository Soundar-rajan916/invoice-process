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
        ring: "var(--accent-strong)",
        background: "var(--bg-app)",
        foreground: "var(--text)",
        ink: {
          DEFAULT: "var(--ink)",
          hover: "var(--ink-hover)",
        },
        primary: {
          DEFAULT: "var(--ink)",
          foreground: "#ffffff",
        },
        secondary: {
          DEFAULT: "var(--bg-card)",
          foreground: "var(--text)",
        },
        destructive: {
          DEFAULT: "var(--danger)",
          foreground: "var(--ink)",
        },
        muted: {
          DEFAULT: "var(--bg-card)",
          foreground: "var(--text-muted)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--ink)",
          soft: "var(--accent-soft)",
          strong: "var(--accent-strong)",
        },
        success: {
          DEFAULT: "var(--success)",
          foreground: "var(--ink)",
          soft: "var(--success-soft)",
          strong: "var(--success-strong)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          foreground: "var(--ink)",
          soft: "var(--danger-soft)",
          strong: "var(--danger-strong)",
        },
        warning: {
          DEFAULT: "var(--warning)",
          foreground: "var(--ink)",
          soft: "var(--warning-soft)",
          strong: "var(--warning-strong)",
        },
        card: {
          DEFAULT: "var(--bg-card)",
          foreground: "var(--text)",
        },
        // Semantic tokens mapped strictly to Reference B pastel palette
        findeck: {
          app: "var(--bg-app)",
          sidebar: "var(--bg-card)",
          card: "var(--bg-card)",
          inset: "var(--bg-inset)",
          disabled: "var(--bg-disabled)",
          border: "var(--border)",
          ink: "var(--ink)",
          "ink-hover": "var(--ink-hover)",
          text: "var(--text)",
          "text-secondary": "var(--text-secondary)",
          muted: "var(--text-muted)",
          accent: "var(--accent)",
          "accent-soft": "var(--accent-soft)",
          "accent-strong": "var(--accent-strong)",
          success: "var(--success)",
          "success-soft": "var(--success-soft)",
          "success-strong": "var(--success-strong)",
          danger: "var(--danger)",
          "danger-soft": "var(--danger-soft)",
          "danger-strong": "var(--danger-strong)",
          warning: "var(--warning)",
          "warning-soft": "var(--warning-soft)",
          "warning-strong": "var(--warning-strong)",
        },
      },
      borderRadius: {
        card: "var(--radius-card)",
        btn: "var(--radius-btn)",
        pill: "var(--radius-pill)",
        lg: "var(--radius-card)",
        md: "var(--radius-btn)",
        sm: "calc(var(--radius-btn) - 2px)",
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
