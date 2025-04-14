<script>
    import { configInfo, jobConfigOverrides } from '../stores.js';
    import { tick } from 'svelte'; // Import tick for async updates
  
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
        // Avoid infinite loops by checking if values differ significantly
        if (JSON.stringify(overrides) !== JSON.stringify(value)) {
           overrides = { ...value }; // Update local copy from store
        }
    });
  
    // --- Define Compatibility Rules ---
    const COMPATIBILITY_RULES = {
        mps: ['int8', 'float32', 'int16'], // Common MPS compatible types (float32 might be slow)
        cuda: ['float16', 'bfloat16', 'int8', 'float32', 'int16'], // Most types usually work on CUDA
        cpu: ['int8', 'float32', 'int16'], // Common CPU types
        unknown: ['int8', 'float16', 'int16', 'bfloat16', 'float32'], // Show all if detection failed
        error: ['int8', 'float16', 'int16', 'bfloat16', 'float32'], // Show all if detection failed
    };
  
    // --- Reactive Calculation for Available Compute Types ---
    let availableComputeTypes = [];
    $: {
        if (schema?.compute_type?.options && detectedDevice) {
            const compatibleTypes = COMPATIBILITY_RULES[detectedDevice] || COMPATIBILITY_RULES['unknown'];
            availableComputeTypes = schema.compute_type.options.filter(option => compatibleTypes.includes(option));
            log(`Device: ${detectedDevice}. Available compute types:`, availableComputeTypes);
  
            // --- Adjust Initial/Default Override Value ---
            // Run this reactively after schema and device info are loaded
            const currentComputeOverride = $jobConfigOverrides['compute_type'];
            const schemaDefault = schema?.compute_type?.default;
  
            // If the current override is not available OR if no override is set yet
            // and the schema default is not available, pick the first available type.
            if ((currentComputeOverride && !availableComputeTypes.includes(currentComputeOverride)) ||
                (!currentComputeOverride && schemaDefault && !availableComputeTypes.includes(schemaDefault)))
            {
                const newDefault = availableComputeTypes.length > 0 ? availableComputeTypes[0] : schemaDefault; // Fallback to schema default if available list empty
                if (newDefault !== currentComputeOverride) {
                    log(`Adjusting compute_type default/override. Schema default '${schemaDefault}' or current '${currentComputeOverride}' not available for device '${detectedDevice}'. Setting to '${newDefault}'.`);
                    // Use tick to ensure this update happens after initial store hydration
                    tick().then(() => {
                        jobConfigOverrides.update(o => ({ ...o, compute_type: newDefault }));
                    });
                }
            }
            // If no override is set yet, but schema default *is* available, set it
            else if (!currentComputeOverride && schemaDefault && availableComputeTypes.includes(schemaDefault)) {
                 tick().then(() => {
                      jobConfigOverrides.update(o => ({ ...o, compute_type: schemaDefault }));
                 });
            }
        } else {
            // Fallback if schema/device not loaded yet
            availableComputeTypes = schema?.compute_type?.options || [];
        }
    }
  
    // Initialize overrides with defaults when schema loads
    // Use a reactive statement to trigger once schema is populated
    let initialized = false;
    $: {
        if (!initialized && schema && Object.keys(schema).length > 0 && Object.keys(overrides).length === 0) {
            const initialOverrides = {};
            const simpleTypes = ["string", "integer", "float", "bool", "enum"];
            for (const key in schema) {
                if (schema[key]?.default !== undefined && simpleTypes.includes(schema[key].type)) {
                    // Special case: Don't set compute_type here yet, let the reactive block above handle it
                    if (key !== 'compute_type') {
                       initialOverrides[key] = schema[key].default;
                    }
                }
            }
            jobConfigOverrides.set(initialOverrides);
            log('Initialized overrides with defaults (excluding compute_type initially):', initialOverrides);
            initialized = true; // Prevent re-initialization
        }
    }
  
  
    // --- Update Store on Input Change ---
    function handleInputChange(key, value) {
        // Update the central store whenever a local input changes
        // This could be done directly with bind:value={$jobConfigOverrides[key]}
        // but having a handler allows for potential validation later.
        jobConfigOverrides.update(currentOverrides => ({
            ...currentOverrides,
            [key]: value
        }));
    }
    // We'll use bind:value directly for simplicity now. Remove handleInputChange if not needed.
  
    // --- Utility Functions ---
    function formatLabel(key) { /* ... unchanged ... */ }
    function log(...args) { console.log('[ConfigForm]', ...args); }
    import { onDestroy } from 'svelte'; // Need onDestroy for cleanup
    onDestroy(() => { unsubscribeConfig(); unsubscribeOverrides(); }); // Cleanup subscriptions
  
    // Define which types should have input controls generated
    const editableTypes = ["string", "integer", "float", "bool", "enum"];
    const excludedKeys = ["input_audio", "intermediate_transcript_path", "llm_models", "hf_token"];
  
  </script>
  
  <div class="bg-white p-6 rounded-lg shadow-md">
    <h2 class="text-xl font-semibold mb-4 text-gray-700">2. Configure Pipeline</h2>
  
    {#if !schema || Object.keys(schema).length === 0}
      <p class="text-gray-500 italic">Loading configuration options...</p>
    {:else}
      <form class="space-y-4">
        {#each Object.entries(schema) as [key, spec] (key)} <!-- Add key to each block -->
          {#if editableTypes.includes(spec.type) && !excludedKeys.includes(key)}
            <div class="flex flex-col border-b border-gray-200 pb-3 last:border-b-0">
              <label for={key} class="block text-sm font-medium text-gray-700 mb-1">
                {formatLabel(key)} {#if key === 'compute_type' && detectedDevice}(Detected: {detectedDevice || 'N/A'}){/if}
              </label>
  
              <!-- Render different input based on schema type -->
              {#if spec.type === 'enum'}
                <select {key} bind:value={$jobConfigOverrides[key]} class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm">
                   <!-- !! Use FILTERED list for compute_type !! -->
                   {#if key === 'compute_type'}
                      {#each availableComputeTypes as option (option)} <option {option}>{option}</option> {/each}
                   {:else}
                      {#each spec.options || [] as option (option)} <option {option}>{option}</option> {/each}
                   {/if}
                </select>
  
              {:else if spec.type === 'bool'}
                <input {key} type="checkbox" bind:checked={$jobConfigOverrides[key]} class="mt-1 h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500">
  
              {:else if spec.type === 'integer'}
                <input {key} type="number" step="1" bind:value={$jobConfigOverrides[key]} placeholder="Default: {spec.default}" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
  
              {:else if spec.type === 'float'}
                 <input {key} type="number" step="any" bind:value={$jobConfigOverrides[key]} placeholder="Default: {spec.default}" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
  
              {:else if key === 'extra_context_prompt'}
                  <textarea {key} rows="3" bind:value={$jobConfigOverrides[key]} placeholder="Optional: Provide extra context for LLM analysis..." class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"></textarea>
  
              {:else if spec.type === 'string'}
                 {#if key === 'language'}
                   <input {key} type="text" bind:value={$jobConfigOverrides[key]} placeholder="e.g., 'en', 'nl' (leave empty for auto-detect)" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                 {:else}
                   <input {key} type="text" bind:value={$jobConfigOverrides[key]} placeholder="Default: {spec.default}" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                 {/if}
              {/if}
  
              {#if spec.description} <p class="mt-1 text-xs text-gray-500">{spec.description}</p> {/if}
            </div>
          {/if}
        {/each}
      </form>
    {/if}
  </div>