<script>
    import { onMount } from 'svelte';
    // Import stores and the API base URL
    import { configInfo, configLoaded, apiBaseUrl } from './lib/stores.js';
    // Import sub-components we will create later
    import ConfigForm from './lib/components/ConfigForm.svelte';
    import AudioUpload from './lib/components/AudioUpload.svelte';
    import JobRunner from './lib/components/JobRunner.svelte';
  
    let appTitle = 'Transcriber App';
    let errorLoadingConfig = null; // To display errors if config load fails
    let baseUrl; // Variable to hold the API base URL from the store
  
    // Subscribe to the apiBaseUrl store
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => {
      baseUrl = value;
    });
  
    // Fetch configuration from the backend when the component mounts
    onMount(async () => {
      log('App mounted, fetching config info...'); // Use browser console log
      try {
        const response = await fetch(`${baseUrl}/config_info`); // Use stored base URL
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || `HTTP error! Status: ${response.status}`);
        }
        const data = await response.json();
        log('Config info received:', data);
        // Update the stores
        configInfo.set({
           schema: data.schema || {},
           available_models: data.available_models || []
        });
        configLoaded.set(true); // Mark config as loaded
        errorLoadingConfig = null; // Clear any previous error
      } catch (error) {
        console.error("Failed to fetch config info:", error);
        errorLoadingConfig = `Failed to load server configuration: ${error.message}. Please ensure the backend is running.`;
        configLoaded.set(false); // Ensure loaded state is false on error
      }
    });
  
    // Cleanup subscription when component is destroyed
    import { onDestroy } from 'svelte';
    onDestroy(() => {
      unsubscribeApiBase();
    });
  
    // Helper for logging to browser console
    function log(...args) {
        console.log('[Frontend Log]', ...args);
    }
  
  </script>
  
  <main class="container mx-auto p-8 max-w-4xl">
    <h1 class="text-3xl font-bold text-center text-indigo-700 mb-6">
      { appTitle }
    </h1>
  
    {#if errorLoadingConfig}
      <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-6" role="alert">
        <strong class="font-bold">Error!</strong>
        <span class="block sm:inline"> {errorLoadingConfig}</span>
      </div>
    {:else if $configLoaded}
      <div class="space-y-6">
        <div class="bg-white p-4 rounded shadow"><AudioUpload /></div>
  
        <div class="bg-white p-4 rounded shadow"><ConfigForm /></div>
  
        <div class="bg-white p-4 rounded shadow"><JobRunner /></div>
      </div>
    {:else}
      <div class="text-center text-gray-600">
        Loading configuration from server...
      </div>
    {/if}
  
  </main>
  
  <style lang="postcss">
    /* Add global styles or component specific ones here */
  </style>