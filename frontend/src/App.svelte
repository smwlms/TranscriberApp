<script>
    import { onMount, onDestroy } from 'svelte';
    // Import stores and the API base URL
    import { configInfo, configLoaded, apiBaseUrl } from './lib/stores.js';
  
    // --- Import UI components ---
    import ThemeToggle from './lib/components/ThemeToggle.svelte';
    import PresetSelector from './lib/components/PresetSelector.svelte'; // Import PresetSelector
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
      // Small delay to ensure baseUrl might be set if readable store takes a moment
      if (!baseUrl) {
          log("API Base URL not set yet, slight delay before config fetch.");
          await new Promise(resolve => setTimeout(resolve, 50));
          if (!baseUrl) {
               errorLoadingConfig = "API configuration could not be determined.";
               configLoaded.set(false);
               return;
          }
      }
      try {
        const response = await fetch(`${baseUrl}/config_info`);
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({})); // Try to get error details
          throw new Error(errorData.error || `HTTP error! Status: ${response.status}`);
        }
        const data = await response.json();
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
        console.error("Failed to fetch config info:", error);
        errorLoadingConfig = `Failed to load server configuration: ${error.message}. Please ensure the backend is running and accessible via proxy.`;
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
           console.log('[App]', ...args);
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
        <PresetSelector /> <ConfigForm />
        <JobRunner />
      </div>
    {:else}
      <div class="text-center text-gray-600 dark:text-gray-400 py-10">
        Loading configuration from server...
      </div>
    {/if}
  
  </main>
  
  <style lang="postcss">
  </style>