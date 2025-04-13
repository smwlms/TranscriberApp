import { vitePreprocess } from '@sveltejs/vite-plugin-svelte'

export default {
  // Consult https://svelte.dev/docs#compile-time-svelte-preprocess
  // for more information about preprocessors
  // vitePreprocess() integrates with Vite's pipeline,
  // allowing things like PostCSS/Tailwind processing within <style> tags.
  preprocess: vitePreprocess(),
}