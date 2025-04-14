<script>
    import { onMount, onDestroy } from 'svelte';
    import { configInfo, configLoaded, apiBaseUrl } from './lib/stores.js';
  
    // Import UI components
    import ThemeToggle from './lib/components/ThemeToggle.svelte';
    import AudioUpload from './lib/components/AudioUpload.svelte';
    import ConfigForm from './lib/components/ConfigForm.svelte';
    import JobRunner from './lib/components/JobRunner.svelte';
  
    let appTitle = 'Transcriber App';
    let errorLoadingConfig = null;
    let baseUrl;
  
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => { baseUrl = value; });
  
    onMount(async () => {
      log('App mounted, fetching config info...');
      if (!baseUrl) { await new Promise(resolve => setTimeout(resolve, 50)); }
      if (!baseUrl) { errorLoadingConfig = "API config missing."; configLoaded.set(false); return; }
      try {
        const response = await fetch(`${baseUrl}/config_info`);
        if (!response.ok) { const d = await response.json().catch(()=>({})); throw new Error(d.error || `HTTP ${response.status}`); }
        const data = await response.json();
        log('Config info received:', data);
        configInfo.set({ schema: data.schema || {}, available_models: data.available_models || [], detected_device: data.detected_device || 'unknown' });
        configLoaded.set(true); errorLoadingConfig = null;
      } catch (error) { console.error("Failed fetch config:", error); errorLoadingConfig = `Failed config load: ${error.message}.`; configLoaded.set(false); }
    });
  
    onDestroy(() => { unsubscribeApiBase(); });
    function log(...args) { if (typeof console !== 'undefined') { console.log('[App]', ...args); } }
  
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
        <ConfigForm />
        <JobRunner />
      </div>
    {:else}
      <div class="text-center text-gray-600 dark:text-gray-400 py-10"> Loading configuration... </div>
    {/if}
  </main>
  
  <style lang="postcss">
      /* Optional: Component-specific styles */
  </style>