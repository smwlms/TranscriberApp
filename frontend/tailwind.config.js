/** @type {import('tailwindcss').Config} */
module.exports = {
  // Enable class-based dark mode (Tailwind will look for a `.dark` class on an ancestor, typically <html>)
  darkMode: 'selector',
  // Configure the paths to all of your template files that contain Tailwind classes
  content: [
    "./index.html",              // Scan the main HTML file in the frontend root
    "./src/**/*.{svelte,js,ts}"  // Scan all Svelte, JS, and TS files within the src folder and subfolders
  ],

  // Customize or extend the default Tailwind theme (optional)
  theme: {
    extend: {
      // Add custom values here if needed
      // Example:
      // colors: {
      //   'brand-primary': '#0056b3',
      // },
      // fontFamily: {
      //   'sans': ['Inter', 'system-ui', 'sans-serif'],
      // }
    },
  },

  // Add Tailwind plugins (optional)
  plugins: [
    // Example: Add plugin for better default form styles (might conflict/override custom styles)
    // require('@tailwindcss/forms'),
  ],
}