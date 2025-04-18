// File: frontend/vite.config.js
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
      // Proxy API requests starting with /api/v1
      '/api/v1': {
        target: 'http://localhost:5000', // Your Flask backend address
        changeOrigin: true, // Needed for virtual hosted sites
        secure: false,      // Allow proxying to http target
      },
      // *** ADDED: Proxy static audio file requests ***
      '/audio': {
        target: 'http://localhost:5000', // Point to Flask backend
        changeOrigin: true,
        secure: false,
      },
      // *** ADDED: Proxy static result file requests ***
      '/results': {
        target: 'http://localhost:5000', // Point to Flask backend
        changeOrigin: true,
        secure: false,
      }
    }
  },
  build: {
     outDir: 'dist',
     emptyOutDir: true,
  }
})