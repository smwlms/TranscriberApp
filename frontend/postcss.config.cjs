// frontend/postcss.config.cjs
// Use CommonJS syntax for PostCSS config files
module.exports = {
  plugins: {
    tailwindcss: {}, // Integrate Tailwind CSS plugin
    autoprefixer: {}, // Add vendor prefixes automatically for browser compatibility
    // Add any other PostCSS plugins here if needed in the future
  },
};