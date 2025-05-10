// File: tailwind.config.cjs
/** @type {import('tailwindcss').Config} */
module.exports = {
  // Enable class-based dark mode support
  darkMode: 'class',

  // Paths to all of the template files in your project
  content: [
    './src/**/*.{html,svelte,js,ts}'
  ],

  theme: {
    extend: {
      // Voeg hier je eigen uitbreidingen toe (kleuren, fonts, spacing, etc.)
    },
  },

  plugins: [
    // Bijvoorbeeld: require('@tailwindcss/forms'),
  ],

  // Safelist voor CSS-klassen die dynamisch worden toegevoegd (zoals .highlight)
  safelist: [
    'highlight',
  ],
};
