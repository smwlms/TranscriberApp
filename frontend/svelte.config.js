// File: svelte.config.js
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('vite').UserConfig} */
export default {
  // Enables Tailwind & PostCSS processing
  preprocess: vitePreprocess(),
};