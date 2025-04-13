import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    svelte() // Add the Svelte plugin
  ],
  server: {
    port: 5173, // Port for the Vite dev server (default)
    strictPort: true, // Exit if port is already in use
    proxy: {
      // Proxy requests starting with /api/v1 to the Flask backend
      // This avoids CORS issues during development.
      '/api/v1': { // Match the prefix set in app.py
        target: 'http://localhost:5001', // Your Flask backend address
        changeOrigin: true, // Needed for virtual hosted sites
        secure: false,      // Allow proxying to http target
        // No path rewrite needed as Flask routes already start with /api/v1
      }
    }
  },
  // Optional: Specify the build output directory
  build: {
     outDir: 'dist', // Directory for the production build output
     emptyOutDir: true, // Clear the directory before each build
  }
})