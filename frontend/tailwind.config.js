/** @type {import('tailwindcss').Config} */
module.exports = {
  // --- ADD THIS LINE ---
  darkMode: 'selector', // Enables class-based dark mode (looking for .dark class on html)
  // --------------------
  content: [
    "./index.html",
    "./src/**/*.{svelte,js,ts}"
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}