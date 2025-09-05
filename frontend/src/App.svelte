<script>
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';

  // --- Stores ---
  import {
    configInfo,
    configLoaded,
    apiBaseUrl
  } from './lib/stores.js';

  // --- API Service ---
  import { getConfigInfo } from './lib/api.js';

  // --- UI Components ---
  import ThemeToggle     from './lib/components/ThemeToggle.svelte';
  import PresetSelector  from './lib/components/PresetSelector.svelte';
  import AudioUpload     from './lib/components/AudioUpload.svelte';
  import ConfigForm      from './lib/components/ConfigForm.svelte';
  import JobRunner       from './lib/components/JobRunner.svelte';
  import HealthIndicator from './lib/components/HealthIndicator.svelte';

  // --- Local state ---
  let errorLoadingConfig = null;

  // --- Logging helper ---
  function log(...args) {
    // Gebruik debug zodat je het filter in DevTools kunt instellen op 'Verbose'
    console.debug(
      '[App]',
      `(Base: ${get(apiBaseUrl)})`,
      ...args
    );
  }

  // --- Fetch config on mount ---
  onMount(async () => {
    log('App mounted, fetching configInfo...');
    try {
      const data = await getConfigInfo();
      log('Config info received:', data);

      configInfo.set({
        schema:           data.schema           || {},
        available_models: data.available_models || [],
        detected_device:  data.detected_device  || 'unknown'
      });
      configLoaded.set(true);
      errorLoadingConfig = null;
    } catch (e) {
      console.error('[App] Failed to load configInfo:', e);
      errorLoadingConfig = `
        Kon serverconfiguratie niet laden: ${e.message}.
        Controleer of de backend draait en toegankelijk is.
      `.trim();
      configLoaded.set(false);
    }
  });
</script>

<main class="app-page min-h-screen">
  <header class="flex items-center justify-between mb-6 sm:mb-8">
    <div class="title-stack">
      <h1 class="section-title">Transcriber App</h1>
      <p class="section-subtle">Upload audio, maak automatisch een transcript en ontvang een duidelijke samenvatting en inzichten.</p>
    </div>
    <div class="flex items-center gap-3">
      <HealthIndicator />
      <ThemeToggle />
    </div>
  </header>

  {#if errorLoadingConfig}
    <div
      class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-6
             dark:bg-red-900/30 dark:border-red-700 dark:text-red-300"
      role="alert"
    >
      <strong class="font-bold">Error!</strong>
      <span class="block sm:inline"> {errorLoadingConfig}</span>
    </div>
  {:else if $configLoaded}
    <div class="space-y-6">
      <AudioUpload />
      <PresetSelector />
      <ConfigForm />
      <JobRunner />
    </div>
  {:else}
    <div class="text-center text-gray-600 dark:text-gray-400 py-10">
      Loading configuration from server…
    </div>
  {/if}
</main>

<style lang="postcss">
/* Houd hier je eventueel bestaande custom styles */
</style>
