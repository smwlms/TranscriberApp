<script>
  import { onMount, onDestroy } from 'svelte';
  // Import stores and the API base URL (still needed for logging/understanding context)
  import { configInfo, configLoaded, apiBaseUrl } from './lib/stores.js';

  // Import the API service
  import { getConfigInfo } from './lib/api.js';

  // Import get helper for log function - MUST BE AT TOP LEVEL
  import { get } from 'svelte/store'; // <-- GECORRIGEERDE LOCATIE

  // --- Import UI components ---
  import ThemeToggle from './lib/components/ThemeToggle.svelte';
  import PresetSelector from './lib/components/PresetSelector.svelte';
  import AudioUpload from './lib/components/AudioUpload.svelte';
  import ConfigForm from './lib/components/ConfigForm.svelte';
  import JobRunner from './lib/components/JobRunner.svelte';

  let appTitle = 'Transcriber App';
  let errorLoadingConfig = null;
  let baseUrl; // Keep subscribed to for potential logging/display if needed
  const unsubscribeApiBase = apiBaseUrl.subscribe(value => { baseUrl = value; });


  // Fetch configuration from the backend when the component mounts
  onMount(async () => {
    log('App mounted, fetching config info...');

    // No longer need the manual delay/check for baseUrl here,
    // the api.js helper function gets the current value from the store when called.
    // If baseUrl is still somehow not set, the API call itself will likely fail.

    try {
      // Use the API service function to fetch config
      const data = await getConfigInfo();
      // Response handling is done inside getConfigInfo/handleResponse

      log('Config info received:', data);
      // Update the configInfo store with all fetched data
      configInfo.set({
         schema: data.schema || {},
         available_models: data.available_models || [],
         detected_device: data.detected_device || 'unknown'
      });
      configLoaded.set(true); // Mark config as loaded
      errorLoadingConfig = null; // Clear any previous error on success
    } catch (error) {
      // Catch errors thrown by getConfigInfo/handleResponse
      console.error("Failed to fetch config info:", error);
      errorLoadingConfig = `Failed to load server configuration: ${error.message}. Please ensure the backend is running and accessible.`;
      configLoaded.set(false); // Ensure loaded state is false on error
    }
  });

  // Cleanup store subscription when component is destroyed
  onDestroy(() => {
    unsubscribeApiBase();
  });

  // Helper for logging to browser console
  function log(...args) {
      if (typeof console !== 'undefined' && console.log) {
         // Use the current baseUrl in logs for context
         const currentBase = get(apiBaseUrl); // Get current value from store
         console.log('[App]', `(Base: ${currentBase})`, ...args);
      }
  }

</script>

<main class="container mx-auto p-4 sm:p-8 max-w-4xl min-h-screen">

  <div class="flex justify-between items-center mb-8 sm:mb-10">
    <h1 class="text-2xl sm:text-3xl font-bold text-indigo-700 dark:text-indigo-400 transition-colors duration-150">
      { appTitle }
    </h1>
    <ThemeToggle />
  </div>

  {#if errorLoadingConfig}
    <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-6 dark:bg-red-900/30 dark:border-red-700 dark:text-red-300" role="alert">
      <strong class="font-bold">Error!</strong> <span class="block sm:inline"> {errorLoadingConfig}</span>
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
      Loading configuration from server...
    </div>
  {/if}

</main>

<style lang="postcss">
/* Your existing styles from App.svelte style block */
</style>