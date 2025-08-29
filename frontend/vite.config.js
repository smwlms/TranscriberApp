import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  server: {
    hmr: { overlay: false },
    proxy: {
      // stuur al je API‐calls door naar je Flask backend
      '/api/v1': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false
      },
      '/audio': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false
      },
      '/results': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false
      }
      ,
      '/transcripts': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false
      }
    }
  }
});
