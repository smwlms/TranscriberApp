<script>
    import { configInfo, jobConfigOverrides, selectedPreset } from '../stores.js';
    import { tick, onDestroy } from 'svelte';
  
    // Local state for accordion visibility
    let transcriptionVisible = false;
    let speakerVisible = false;
    let analysisVisible = false;
  
    // Subscribe to stores
    let schema = {};
    let detectedDevice = null;
    const unsubscribeConfig = configInfo.subscribe(value => {
        schema = value.schema || {};
        detectedDevice = value.detected_device;
    });
    // jobConfigOverrides store is bound directly in the template using bind:value
  
    // --- Preset Definitions (using user chosen names) ---
    const presetsConfig = {
      quick: {
        mode: 'fast',
        whisper_model: 'tiny',
        compute_type: 'int8', // Will be adjusted by compatibility check if needed
        speaker_name_detection_enabled: false,
        language: null,
      },
      standard: { // Should align with most schema defaults
        mode: 'fast',
        whisper_model: 'small',
        compute_type: 'int8',
        speaker_name_detection_enabled: true, // Diarization itself always runs
        language: null,
      },
      multi: {
        mode: 'advanced',
        whisper_model: 'medium', // User might want large-v3 depending on hardware
        compute_type: 'int8',
        speaker_name_detection_enabled: true,
        language: null,
      }
    };
  
    // --- Compatibility Rules & Available Types Calculation ---
    const COMPATIBILITY_RULES = {
        mps: ['int8', 'float32', 'int16'],
        cuda: ['float16', 'bfloat16', 'int8', 'float32', 'int16'],
        cpu: ['int8', 'float32', 'int16'],
        unknown: ['int8', 'float16', 'int16', 'bfloat16', 'float32'], // Fallback: show all
        error: ['int8', 'float16', 'int16', 'bfloat16', 'float32'], // Fallback: show all
    };
    let availableComputeTypes = [];
    $: { // Calculate available compute types reactively
        if (schema?.compute_type?.options && detectedDevice && typeof detectedDevice === 'string') { // Added string check
            const compatibleTypes = COMPATIBILITY_RULES[detectedDevice] || COMPATIBILITY_RULES['unknown'];
            availableComputeTypes = schema.compute_type.options.filter(option => compatibleTypes.includes(option));
            log(`Device: ${detectedDevice}. Available compute types:`, availableComputeTypes);
        } else { availableComputeTypes = schema?.compute_type?.options || []; }
    }
  
    // --- Store Schema Defaults ---
    let schemaDefaults = {};
    let defaultsInitialized = false;
    $: {
      // Initialize schemaDefaults once schema is loaded
      if (!defaultsInitialized && schema && Object.keys(schema).length > 0) {
          const simpleTypes = ["string", "integer", "float", "bool", "enum"];
          schemaDefaults = {}; // Reset just in case
          for (const key in schema) {
              // Ensure default is not undefined before adding
              if (schema[key]?.default !== undefined && simpleTypes.includes(schema[key].type)) {
                   schemaDefaults[key] = schema[key].default;
              }
          }
          log('Schema defaults captured:', schemaDefaults);
          defaultsInitialized = true;
          // Trigger initial preset application now that defaults are ready
          // Use the initial value from the selectedPreset store (likely 'standard')
          applyPreset($selectedPreset);
      }
    }
  
    // --- Function to Apply Presets (called reactively) ---
    function applyPreset(presetKey) {
        // Only run if defaults are ready and presetKey is valid
        if (!presetKey || !defaultsInitialized || !presetsConfig[presetKey]) return;
  
        log(`Applying preset: ${presetKey}`);
        const presetValues = presetsConfig[presetKey];
  
        // Start with schema defaults, then merge preset values
        let mergedOverrides = { ...schemaDefaults, ...presetValues };
  
        // Adjust compute_type based on device compatibility AFTER merging preset value
        const targetComputeType = mergedOverrides['compute_type'];
        // Ensure availableComputeTypes is calculated before this check runs
        if (detectedDevice && availableComputeTypes.length > 0) {
            if (!availableComputeTypes.includes(targetComputeType)) {
                 const newComputeType = availableComputeTypes[0]; // Fallback to first compatible type
                 log(`Preset compute_type '${targetComputeType}' adjusted to '${newComputeType}' for device '${detectedDevice}'.`);
                 mergedOverrides['compute_type'] = newComputeType;
            }
        } else if (schema?.compute_type?.options && !schema.compute_type.options.includes(targetComputeType)) {
             // Fallback if device detection failed but default compute type is invalid somehow
             log(`Preset compute_type '${targetComputeType}' invalid. Using schema default '${schema.compute_type.default}'.`, "WARN");
             mergedOverrides['compute_type'] = schema.compute_type.default;
        }
  
        // Update the central store -> this updates the bound form elements
        let currentOverridesValue;
        const unsubscribe = jobConfigOverrides.subscribe(v => currentOverridesValue = v);
        unsubscribe(); // Get current value then unsubscribe immediately
        if(JSON.stringify(currentOverridesValue) !== JSON.stringify(mergedOverrides)){
            jobConfigOverrides.set(mergedOverrides);
            log('Applied preset overrides:', mergedOverrides);
        } else {
            log('Preset selection resulted in no changes to current overrides.');
        }
    }
  
    // --- Reactive statement to apply presets when selection changes ---
    // This ensures that clicking a preset button updates the form
    $: if(defaultsInitialized) applyPreset($selectedPreset);
  
  
    // --- Utility Functions & Cleanup ---
    function formatLabel(key) { return key.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').replace(/^./, (str) => str.toUpperCase()); }
    function log(...args) { console.log('[ConfigForm]', ...args); }
    onDestroy(() => { unsubscribeConfig(); }); // Cleanup configInfo subscription
  
    // --- Component Configuration ---
    const editableTypes = ["string", "integer", "float", "bool", "enum"];
    // Exclude keys handled elsewhere or too complex/read-only for this form
    const excludedKeys = [
        "input_audio", "intermediate_transcript_path", "llm_models", "hf_token",
        "llm_default_timeout", "llm_final_analysis_timeout", "logging_enabled",
        "log_level", "log_backup_count", "database_filename" // Also exclude logging/DB settings
    ];
  
    // Helper function to toggle accordion sections
    function toggleSection(section) {
        if (section === 'transcription') transcriptionVisible = !transcriptionVisible;
        if (section === 'speaker') speakerVisible = !speakerVisible;
        if (section === 'analysis') analysisVisible = !analysisVisible;
    }
  
  </script>
  
  <div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md transition-colors duration-150">
    <h2 class="text-xl font-semibold mb-1 text-gray-700 dark:text-gray-200">2. Configure Pipeline (Advanced)</h2>
    <p class="text-xs text-gray-500 dark:text-gray-400 mb-4">Select a preset (above) or expand sections below to customize.</p>
  
    {#if !schema || Object.keys(schema).length === 0}
      <p class="text-gray-500 dark:text-gray-400 italic">Loading configuration options...</p>
    {:else}
      <div class="space-y-2">
  
        <div class="border border-gray-200 dark:border-gray-700 rounded">
          <button on:click={() => toggleSection('transcription')} aria-expanded={transcriptionVisible} aria-controls="transcription-panel" class="w-full flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700/80 rounded-t {transcriptionVisible ? '' : 'rounded-b'} transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500">
            <span class="font-medium text-gray-700 dark:text-gray-200">Transcription Settings</span>
            <span class="text-gray-500 dark:text-gray-400 transform transition-transform {transcriptionVisible ? 'rotate-180' : ''}">▼</span>
          </button>
          {#if transcriptionVisible}
            <div id="transcription-panel" class="p-4 space-y-4 border-t border-gray-200 dark:border-gray-700">
              {#each Object.entries(schema) as [key, spec] (key)}
                {#if (key === 'whisper_model' || key === 'compute_type' || key === 'language') && editableTypes.includes(spec.type) && !excludedKeys.includes(key)}
                  <div class="flex flex-col">
                    <label for={key} class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {formatLabel(key)} {#if key === 'compute_type' && detectedDevice}(Detected: {detectedDevice || 'N/A'}){/if}
                    </label>
                    {#if spec.type === 'enum'}
                      <select id={key} bind:value={$jobConfigOverrides[key]} class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm transition-colors duration-150 appearance-none">
                         {#if key === 'compute_type'} {#each availableComputeTypes as option (option)} <option value={option}>{option}</option> {/each}
                         {:else} {#each spec.options || [] as option (option)} <option value={option}>{option}</option> {/each} {/if}
                      </select>
                    {:else if spec.type === 'string'}
                         <input id={key} type="text" bind:value={$jobConfigOverrides[key]} placeholder={key === 'language' ? "e.g., 'en' (blank=auto)" : `Default: ${spec.default}`} class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm placeholder-gray-400 dark:placeholder-gray-500">
                    {/if}
                    {#if spec.description} <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{spec.description}</p> {/if}
                  </div>
                {/if}
              {/each}
            </div>
          {/if}
        </div>
  
        <div class="border border-gray-200 dark:border-gray-700 rounded">
           <button on:click={() => toggleSection('speaker')} aria-expanded={speakerVisible} aria-controls="speaker-panel" class="w-full flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700/80 rounded-t {speakerVisible ? '' : 'rounded-b'} transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500">
             <span class="font-medium text-gray-700 dark:text-gray-200">Speaker Settings</span>
             <span class="text-gray-500 dark:text-gray-400 transform transition-transform {speakerVisible ? 'rotate-180' : ''}">▼</span>
           </button>
           {#if speakerVisible}
             <div id="speaker-panel" class="p-4 space-y-4 border-t border-gray-200 dark:border-gray-700">
               {#each Object.entries(schema) as [key, spec] (key)}
                 {#if (key === 'pyannote_pipeline' || key === 'speaker_name_detection_enabled' || key === 'speaker_map_path') && editableTypes.includes(spec.type) && !excludedKeys.includes(key)}
                   <div class="flex flex-col">
                     <label for={key} class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{formatLabel(key)}</label>
                     {#if spec.type === 'bool'}
                       <div class="flex items-center"> <input id={key} type="checkbox" bind:checked={$jobConfigOverrides[key]} class="mt-1 h-4 w-4 text-indigo-600 border-gray-300 dark:border-gray-500 rounded focus:ring-indigo-500 bg-white dark:bg-gray-700"></div>
                     {:else if spec.type === 'string'}
                        <input id={key} type="text" bind:value={$jobConfigOverrides[key]} placeholder="Default: {spec.default}" class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm placeholder-gray-400 dark:placeholder-gray-500">
                     {/if}
                     {#if spec.description} <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{spec.description}</p> {/if}
                   </div>
                 {/if}
               {/each}
             </div>
           {/if}
         </div>
  
        <div class="border border-gray-200 dark:border-gray-700 rounded">
           <button on:click={() => toggleSection('analysis')} aria-expanded={analysisVisible} aria-controls="analysis-panel" class="w-full flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700/80 rounded-t {analysisVisible ? '' : 'rounded-b'} transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500">
             <span class="font-medium text-gray-700 dark:text-gray-200">Analysis Settings</span>
             <span class="text-gray-500 dark:text-gray-400 transform transition-transform {analysisVisible ? 'rotate-180' : ''}">▼</span>
           </button>
           {#if analysisVisible}
             <div id="analysis-panel" class="p-4 space-y-4 border-t border-gray-200 dark:border-gray-700">
               {#each Object.entries(schema) as [key, spec] (key)}
                 {#if (key === 'mode' || key === 'extra_context_prompt') && editableTypes.includes(spec.type) && !excludedKeys.includes(key)}
                    <div class="flex flex-col">
                      <label for={key} class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{formatLabel(key)}</label>
                      {#if spec.type === 'enum'}
                        <select id={key} bind:value={$jobConfigOverrides[key]} class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm appearance-none">
                           {#each spec.options || [] as option (option)} <option value={option}>{option}</option> {/each}
                        </select>
                      {:else if spec.type === 'string'}
                         <textarea id={key} rows="3" bind:value={$jobConfigOverrides[key]} placeholder="Optional: Provide extra context..." class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm placeholder-gray-400 dark:placeholder-gray-500"></textarea>
                      {/if}
                      {#if spec.description} <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{spec.description}</p> {/if}
                    </div>
                 {/if}
               {/each}
               {#if schema.llm_models} <div class="pt-2"> <p class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">LLM Models Used (Read-only):</p> {#if $jobConfigOverrides.llm_models} <div class="text-xs text-gray-600 dark:text-gray-400 space-y-1"> {#each Object.entries($jobConfigOverrides.llm_models) as [task, models]} {#if models && models.length > 0} <p><span class="font-semibold">{formatLabel(task)}:</span> {models.join(', ')}</p> {/if} {/each} </div> {:else} <p class="text-xs text-gray-500 italic">(Defaults from config.yaml)</p> {/if} {#if schema.llm_models.description} <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{schema.llm_models.description}</p> {/if} </div> {/if}
             </div>
           {/if}
         </div>
  
      </div> {/if} </div>
  <style>
      /* Base style for select arrow */
      select {
          background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
          background-position: right 0.5rem center; background-repeat: no-repeat; background-size: 1.5em 1.5em; padding-right: 2.5rem;
          -webkit-print-color-adjust: exact; print-color-adjust: exact; appearance: none; -webkit-appearance: none; -moz-appearance: none;
      }
      /* The .dark select rule was removed as it's unused */
  </style>