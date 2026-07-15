/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        meesho: {
          jamuni: "#9F2089",  // primary brand purple
          aam: "#FC8B16",     // accent mango/orange
          pink: "#F43397",    // decorative thread highlights
          teal: "#42BC9E",    // success rivet teal
          dark: "#1E1E24",    // neutral text/dark contrast
          light: "#F7F7FA",   // surface gray background
          white: "#FFFFFF"
        }
      },
      fontFamily: {
        sans: ["'Roboto Slab'", "serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      boxShadow: {
        tactile: "0 4px 0px 0px #1E1E24",
        "tactile-active": "0 1px 0px 0px #1E1E24",
      }
    },
  },
  plugins: [],
}
