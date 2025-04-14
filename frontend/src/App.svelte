<script>
    import { onMount, onDestroy } from 'svelte';
    // Import stores and the API base URL
    import { configInfo, configLoaded, apiBaseUrl } from './lib/stores.js';
    // Import sub-components
    import AudioUpload from './lib/components/AudioUpload.svelte';
    import ConfigForm from './lib/components/ConfigForm.svelte';
    import JobRunner from './lib/components/JobRunner.svelte';
  
    let appTitle = 'Transcriber App';
    let errorLoadingConfig = null;
    let baseUrl;
  
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => { baseUrl = value; });
  
    // Fetch configuration from the backend when the component mounts
    onMount(async () => {
      log('App mounted, fetching config info...');
      try {
        const response = await fetch(`${baseUrl}/config_info`);
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `HTTP error! Status: ${response.status}`);
        }
        const data = await response.json();
        log('Config info received:', data);
  
        // --- Store ALL received config info ---
        configInfo.set({
           schema: data.schema || {},
           available_models: data.available_models || [],
           detected_device: data.detected_device || 'unknown' // <-- Store detected device
        });
        // --------------------------------------
  
        configLoaded.set(true); // Mark config as loaded
        errorLoadingConfig = null; // Clear any previous error
      } catch (error) {
        console.error("Failed to fetch config info:", error);
        errorLoadingConfig = `Failed to load server configuration: ${error.message}. Please ensure the backend is running.`;
        configLoaded.set(false);
      }
    });
  
    onDestroy(() => { unsubscribeApiBase(); });
    function log(...args) { console.log('[App]', ...args); }
  
  </script>
  
  <main class="container mx-auto p-8 max-w-4xl">
    <h1 class="text-3xl font-bold text-center text-indigo-700 mb-6"> { appTitle } </h1>
  
    {#if errorLoadingConfig}
      <!-- Error Display -->
      <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-6" role="alert"> <strong class="font-bold">Error!</strong> <span class="block sm:inline"> {errorLoadingConfig}</span> </div>
    {:else if $configLoaded}
      <!-- Main UI Sections -->
      <div class="space-y-6">
        <AudioUpload />
        <ConfigForm />
        <JobRunner />
      </div>
    {:else}
      <!-- Loading Indicator -->
      <div class="text-center text-gray-600 py-10"> Loading configuration from server... </div>
    {/if}
  
  </main>
  
  <style lang="postcss"> /* ... */ </style>