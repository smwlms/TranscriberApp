<script>
    import { configInfo, jobConfigOverrides } from '../stores.js';
    import { tick, onDestroy } from 'svelte';
  
    // Reactive variables based on the store
    let schema = {};
    let detectedDevice = null;
    let overrides = {}; // Local copy to bind inputs
  
    // Subscribe to stores
    const unsubscribeConfig = configInfo.subscribe(value => {
        schema = value.schema || {};
        detectedDevice = value.detected_device;
    });
    const unsubscribeOverrides = jobConfigOverrides.subscribe(value => {
        // Sync local state when store changes (e.g., on reset)
        if (JSON.stringify(overrides) !== JSON.stringify(value)) {
           overrides = { ...value };
        }
    });
  
    // --- Define Compatibility Rules ---
    const COMPATIBILITY_RULES = {
        mps: ['int8', 'float32', 'int16'],
        cuda: ['float16', 'bfloat16', 'int8', 'float32', 'int16'],
        cpu: ['int8', 'float32', 'int16'],
        unknown: ['int8', 'float16', 'int16', 'bfloat16', 'float32'], // Show all if detection failed
        error: ['int8', 'float16', 'int16', 'bfloat16', 'float32'], // Show all on error
    };
  
    // --- Reactive Calculation for Available Compute Types & Default Adjustment ---
    let availableComputeTypes = [];
    $: {
        if (schema?.compute_type?.options && detectedDevice) {
            const compatibleTypes = COMPATIBILITY_RULES[detectedDevice] || COMPATIBILITY_RULES['unknown'];
            availableComputeTypes = schema.compute_type.options.filter(option => compatibleTypes.includes(option));
            log(`Device: ${detectedDevice}. Available compute types:`, availableComputeTypes);
  
            // --- Adjust Initial/Default Override Value ---
            const currentComputeOverride = $jobConfigOverrides['compute_type'];
            const schemaDefault = schema?.compute_type?.default;
  
            if ((currentComputeOverride && !availableComputeTypes.includes(currentComputeOverride)) ||
                (!currentComputeOverride && schemaDefault && !availableComputeTypes.includes(schemaDefault))) {
                const newDefault = availableComputeTypes.length > 0 ? availableComputeTypes[0] : schemaDefault;
                if (newDefault !== currentComputeOverride) {
                    log(`Adjusting compute_type default/override. Setting to '${newDefault}'.`);
                    tick().then(() => { jobConfigOverrides.update(o => ({ ...o, compute_type: newDefault })); });
                }
            } else if (!currentComputeOverride && schemaDefault && availableComputeTypes.includes(schemaDefault)) {
                 // Initialize with schema default if it's available and not set yet
                 tick().then(() => { jobConfigOverrides.update(o => ({ ...o, compute_type: schemaDefault })); });
            }
        } else {
            // Fallback if schema/device not loaded yet
            availableComputeTypes = schema?.compute_type?.options || [];
        }
    }
  
    // --- Initialize overrides with defaults when schema loads ---
    let initialized = false;
    $: {
        // Check store directly to see if it's already populated
        if (!initialized && schema && Object.keys(schema).length > 0 && Object.keys($jobConfigOverrides).length === 0) {
            const initialOverrides = {};
            const simpleTypes = ["string", "integer", "float", "bool", "enum"];
            for (const key in schema) {
                if (schema[key]?.default !== undefined && simpleTypes.includes(schema[key].type)) {
                    // Exclude compute_type initially, it's handled reactively above
                    if (key !== 'compute_type') {
                       initialOverrides[key] = schema[key].default;
                    }
                }
            }
            // Only set if initialOverrides has actual values
            if (Object.keys(initialOverrides).length > 0) {
                  jobConfigOverrides.set(initialOverrides);
                  log('Initialized overrides with defaults (excluding compute_type initially):', initialOverrides);
            }
            initialized = true; // Mark as initialized
        }
    }
  
    // --- Utility Functions ---
    function formatLabel(key) { return key.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').replace(/^./, (str) => str.toUpperCase()); }
    function log(...args) { console.log('[ConfigForm]', ...args); }
    onDestroy(() => { unsubscribeConfig(); unsubscribeOverrides(); }); // Cleanup subscriptions
  
    // --- Component Configuration ---
    const editableTypes = ["string", "integer", "float", "bool", "enum"];
    // Exclude keys handled elsewhere or too complex for this form
    const excludedKeys = ["input_audio", "intermediate_transcript_path", "llm_models", "hf_token", "llm_default_timeout", "llm_final_analysis_timeout"];
  
  </script>
  
  <div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md transition-colors duration-150">
    <h2 class="text-xl font-semibold mb-4 text-gray-700 dark:text-gray-200">2. Configure Pipeline</h2>
  
    {#if !schema || Object.keys(schema).length === 0}
      <p class="text-gray-500 dark:text-gray-400 italic">Loading configuration options...</p>
    {:else}
      <form class="space-y-4">
        {#each Object.entries(schema) as [key, spec] (key)}
          {#if editableTypes.includes(spec.type) && !excludedKeys.includes(key)}
            <div class="flex flex-col border-b border-gray-200 dark:border-gray-700 pb-3 last:border-b-0 transition-colors duration-150">
              <label for={key} class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {formatLabel(key)} {#if key === 'compute_type' && detectedDevice}(Detected: {detectedDevice || 'N/A'}){/if}
              </label>
  
              {#if spec.type === 'enum'}
                <select id={key} bind:value={$jobConfigOverrides[key]} class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm transition-colors duration-150 appearance-none">
                   {#if key === 'compute_type'}
                      {#each availableComputeTypes as option (option)} <option value={option}>{option}</option> {/each}
                   {:else}
                      {#each spec.options || [] as option (option)} <option value={option}>{option}</option> {/each}
                   {/if}
                </select>
              {:else if spec.type === 'bool'}
                <input id={key} type="checkbox" bind:checked={$jobConfigOverrides[key]} class="mt-1 h-4 w-4 text-indigo-600 border-gray-300 dark:border-gray-500 rounded focus:ring-indigo-500 bg-white dark:bg-gray-700 transition-colors duration-150">
              {:else if spec.type === 'integer' || spec.type === 'float'}
                <input id={key} type="number" step={spec.type === 'integer' ? '1' : 'any'} bind:value={$jobConfigOverrides[key]} placeholder="Default: {spec.default}" class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition-colors duration-150">
              {:else if key === 'extra_context_prompt'}
                  <textarea id={key} rows="3" bind:value={$jobConfigOverrides[key]} placeholder="Optional: Provide extra context..." class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition-colors duration-150"></textarea>
              {:else if spec.type === 'string'}
                   <input id={key} type="text" bind:value={$jobConfigOverrides[key]} placeholder={key === 'language' ? "e.g., 'en' (blank=auto)" : `Default: ${spec.default}`} class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition-colors duration-150">
              {/if}
  
              {#if spec.description} <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{spec.description}</p> {/if}
            </div>
          {/if}
        {/each}
      </form>
    {/if}
  </div>
  <style>
      /* Base style for select arrow */
      select {
          background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
          background-position: right 0.5rem center; background-repeat: no-repeat; background-size: 1.5em 1.5em; padding-right: 2.5rem;
          -webkit-print-color-adjust: exact; print-color-adjust: exact; appearance: none; -webkit-appearance: none; -moz-appearance: none;
      }
      /* Dark mode select arrow removed from here */
  </style>