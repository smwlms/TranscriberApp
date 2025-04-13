/** @type {import('tailwindcss').Config} */
module.exports = {
    // Configure the paths to all of your template files
    content: [
      "./index.html",              // Scan the main HTML file
      "./src/**/*.{svelte,js,ts}"  // Scan all Svelte, JS, and TS files within the src folder
    ],
  
    // Customize or extend the default Tailwind theme (optional)
    theme: {
      extend: {
        // Example: Add custom colors, fonts, spacing, etc.
        // colors: {
        //   'brand-primary': '#0056b3', // Example custom color
        // },
        // fontFamily: {
        //   'sans': ['Inter', 'sans-serif'], // Example custom font stack
        // }
      },
    },
  
    // Add Tailwind plugins (optional)
    plugins: [
      // Example: Add plugin for better form styling
      // require('@tailwindcss/forms'),
    ],
  }