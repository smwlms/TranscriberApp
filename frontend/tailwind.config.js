// File: tailwind.config.cjs
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,svelte,js,ts}'],
  theme: {
    extend: {},
  },
  plugins: [],
  safelist: [
    'highlight', // for karaoke word-highlighting
  ],
};