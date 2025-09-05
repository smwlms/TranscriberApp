<script>
    import { configInfo, jobConfigOverrides, selectedPreset } from '../stores.js';
    import { onMount } from 'svelte';
  import { getOllamaCatalog, pullOllamaModel, assignLlmModels } from '../api.js';
  import { tick, onDestroy } from 'svelte';
  
    // Local state for accordion visibility (start collapsed)
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
    // We bind form elements directly to the $jobConfigOverrides store below
  
    // --- Preset Definitions (using user chosen names & new keys) ---
    const presetsConfig = {
      quick: {
        mode: 'fast',
        whisper_model: 'tiny',
        compute_type: 'int8', // Base value, will be adjusted by compatibility check
        speaker_name_detection_enabled: false, // Explicitly disable for speed
        language: null, // Use schema default (auto)
        word_timestamps_enabled: false // Disable for speed
      },
      standard: { // Should align with most schema defaults, but ensure name detection is off by default now
        mode: 'fast',
        whisper_model: 'small',
        compute_type: 'int8',
        speaker_name_detection_enabled: false, // Default to false after schema change
        language: null,
        word_timestamps_enabled: false
      },
      multi: {
        mode: 'advanced',
        whisper_model: 'medium', // More accurate
        compute_type: 'int8',
        speaker_name_detection_enabled: false, // Keep default off unless user enables
        language: null,
        word_timestamps_enabled: true // Enable words for advanced analysis
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

    // Curated list of common language codes for Whisper
    const LANGUAGE_CODES = ['', 'nl','en','fr','de','es','it','pt','pl','ru','tr','sv','da','no','fi'];
    const LANG_LABEL = (c) => c ? c : 'auto-detect';
    $: { // Calculate available compute types reactively based on detected device
        if (schema?.compute_type?.options && detectedDevice && typeof detectedDevice === 'string') {
            const compatibleTypes = COMPATIBILITY_RULES[detectedDevice] || COMPATIBILITY_RULES['unknown'];
            availableComputeTypes = schema.compute_type.options.filter(option => compatibleTypes.includes(option));
            log(`Device: ${detectedDevice}. Available compute types:`, availableComputeTypes);
        } else {
            // Use all schema options if device detection hasn't run or failed
            availableComputeTypes = schema?.compute_type?.options || [];
        }
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

    // ─── Model Catalog (Ollama) for Analysis Settings ─────────────────────
    let modelCatalog = [];
    let localModels = [];
    let systemSpecs = {};
    let recommended = {};
    let modelLoading = false;
    let modelError = null;
    const tasks = ['summary','intent','actions','emotion','questions','legal','name_detection','final'];
    // Selected mapping per task (chips); initialize from overrides if present
    let modelAssigned = {
      summary: [], intent: [], actions: [], emotion: [], questions: [], legal: [], name_detection: [], final: []
    };
    // Temporary selected option per task (add via dropdown)
    let toAdd = {};

    // --- Helpers for nested NER-by-language overrides ------------------------
    function getNerLang(code) {
      const m = $jobConfigOverrides?.hf_ner_models_by_lang || {};
      return m[code] || '';
    }
    function updateNerLang(code, value) {
      jobConfigOverrides.update(v => ({
        ...(v||{}),
        hf_ner_models_by_lang: { ...(v?.hf_ner_models_by_lang||{}), [code]: value }
      }));
    }

    function buildOptions(catalogArr, localArr) {
      const set = new Set([...(localArr || [])]);
      for (const it of (catalogArr || [])) set.add(it.name);
      const all = Array.from(set.values());
      const installed = new Set(localArr || []);
      all.sort((a,b) => (installed.has(a)?0:1) - (installed.has(b)?0:1) || a.localeCompare(b));
      return all.map(n => ({ value: n, label: installed.has(n) ? `${n} (installed)` : n }));
    }
    $: modelOptions = buildOptions(modelCatalog, localModels);

    async function refreshModels() {
      modelLoading = true; modelError = null;
      try {
        const data = await getOllamaCatalog();
        modelCatalog = data.catalog || [];
        localModels = data.local || [];
        recommended = data.recommended || {};
        systemSpecs = data.specs || {};
        // Auto-prefill recommended when empty per task
        for (const t of tasks) {
          if (!Array.isArray(modelAssigned[t]) || modelAssigned[t].length === 0) {
            const rec = recommended[t];
            if (rec) {
              modelAssigned[t] = [rec];
              toAdd[t] = rec; // select in dropdown
            }
          }
        }
      } catch (e) {
        modelError = e.message || String(e);
      } finally { modelLoading = false; }
    }

    async function pullModel(name) {
      if (!confirm(`Model '${name}' downloaden?`)) return;
      modelLoading = true; modelError = null;
      try {
        await pullOllamaModel(name);
        await refreshModels();
      } catch (e) { modelError = e.message || String(e); }
      finally { modelLoading = false; }
    }

    function addModel(task) {
      const m = toAdd[task];
      if (!m) return;
      modelAssigned[task] = Array.from(new Set([...(modelAssigned[task]||[]), m]));
      toAdd[task] = '';
    }
    function removeModel(task, name) {
      modelAssigned[task] = (modelAssigned[task]||[]).filter(x => x !== name);
    }

    async function saveModelAssignments() {
      const mapping = {};
      for (const t of tasks) if (Array.isArray(modelAssigned[t]) && modelAssigned[t].length) mapping[t] = modelAssigned[t];
      if (!Object.keys(mapping).length) { alert('Geen toewijzingen om op te slaan.'); return; }
      modelLoading = true; modelError = null;
      try {
        const res = await assignLlmModels(mapping);
        // update overrides for UI consistency
        $jobConfigOverrides.llm_models = res.llm_models || mapping;
        alert('Opgeslagen in config.yaml');
      } catch (e) { modelError = e.message || String(e); }
      finally { modelLoading = false; }
    }

    function applyM1Max32Preset() {
      modelAssigned = {
        summary: ['llama3:8b','mistral:7b','phi3:medium'],
        intent: ['mistral:7b','qwen2:7b','llama3:8b'],
        actions: ['llama3:8b','phi3:medium'],
        emotion: ['phi3:medium','llama3:8b'],
        questions: ['llama3:8b','qwen2:7b'],
        legal: ['llama3:8b','mistral:7b'],
        name_detection: ['llama3:8b','mistral:7b'],
        final: ['llama3:8b','phi3:medium']
      };
    }

    // Load model catalog once when component mounts
    onMount(async () => {
      await refreshModels();
    });
  
    // --- Function to Apply Presets (called reactively) ---
    function applyPreset(presetKey) {
        // Only run if defaults are ready and presetKey is valid
        if (!presetKey || !defaultsInitialized || !presetsConfig[presetKey]) {
            log(`Skipping preset application (key: ${presetKey}, defaults init: ${defaultsInitialized})`);
            return;
        }
  
        log(`Applying preset: ${presetKey}`);
        const presetValues = presetsConfig[presetKey];
  
        // Start with schema defaults, then merge preset values on top
        let mergedOverrides = { ...schemaDefaults, ...presetValues };
  
        // Adjust compute_type based on device compatibility AFTER merging preset value
        const targetComputeType = mergedOverrides['compute_type'];
        // Ensure availableComputeTypes is calculated and device is known before adjusting
        if (detectedDevice && availableComputeTypes.length > 0) {
            if (!availableComputeTypes.includes(targetComputeType)) {
                 const newComputeType = availableComputeTypes[0]; // Fallback to first compatible type
                 log(`Preset compute_type '${targetComputeType}' adjusted to '${newComputeType}' for device '${detectedDevice}'.`);
                 mergedOverrides['compute_type'] = newComputeType;
            }
        } else if (schema?.compute_type?.options && !schema.compute_type.options.includes(targetComputeType)) {
             // Fallback if device detection failed but preset compute type is invalid
             log(`Preset compute_type '${targetComputeType}' not in schema options. Using schema default '${schema.compute_type.default}' instead.`, "WARN");
             mergedOverrides['compute_type'] = schema.compute_type.default;
        }
  
        // Update the central store -> this updates the bound form elements
        let currentOverridesValue;
        const unsubscribe = jobConfigOverrides.subscribe(v => currentOverridesValue = v);
        unsubscribe(); // Get current value then unsubscribe immediately
        // Only update if the calculated merged values actually differ from current store
        // to prevent potential reactive loops if presets match current state
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
  
  <div class="surface-card">
    <h2 class="section-title">3. Configure Pipeline</h2>
    <p class="section-subtle mb-4">Kies geavanceerde opties wanneer nodig. Alles is optioneel.</p>
  
    {#if !schema || Object.keys(schema).length === 0}
      <p class="text-gray-500 dark:text-gray-400 italic">Loading configuration options...</p>
    {:else}
      <div class="space-y-2">
  
        <div class="border border-gray-200 dark:border-gray-700 rounded-lg">
          <button on:click={() => toggleSection('transcription')} aria-expanded={transcriptionVisible} aria-controls="transcription-panel" class="w-full flex justify-between items-center px-4 py-3 bg-transparent hover:bg-gray-50 dark:hover:bg-gray-700/40 rounded-t-lg {transcriptionVisible ? '' : 'rounded-b-lg'} transition-colors">
            <span class="font-medium">Transcription Settings</span>
            <span class="muted transform transition-transform {transcriptionVisible ? 'rotate-180' : ''}">▼</span>
          </button>
          {#if transcriptionVisible}
            <div id="transcription-panel" class="p-4 space-y-4 border-t border-gray-200 dark:border-gray-700">
              {#each Object.entries(schema) as [key, spec] (key)}
                {#if (key === 'whisper_model' || key === 'compute_type' || key === 'language' || key === 'word_timestamps_enabled') && editableTypes.includes(spec.type) && !excludedKeys.includes(key)}
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
                      {#if key === 'language'}
                        <select id={key} bind:value={$jobConfigOverrides[key]} class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm transition-colors">
                          {#each LANGUAGE_CODES as code (code)}
                            <option value={code}>{LANG_LABEL(code)}</option>
                          {/each}
                        </select>
                        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">Choose a language code or leave on auto-detect.</p>
                      {:else}
                        <input id={key} type="text" bind:value={$jobConfigOverrides[key]} placeholder={`Default: ${spec.default ?? ''}`} class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm placeholder-gray-400 dark:placeholder-gray-500">
                      {/if}
                    {:else if spec.type === 'bool'}
                       <div class="flex items-center mt-1"> <input id={key} type="checkbox" bind:checked={$jobConfigOverrides[key]} class="h-4 w-4 text-indigo-600 border-gray-300 dark:border-gray-500 rounded focus:ring-indigo-500 bg-white dark:bg-gray-700"></div>
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
                 {#if (key === 'pyannote_pipeline' || key === 'expected_speakers' || key === 'speaker_name_detection_enabled' || key === 'speaker_map_path' || key === 'name_detection_candidate_mode') && editableTypes.includes(spec.type) && !excludedKeys.includes(key)}
                  <div class="flex flex-col">
                    <label for={key} class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{formatLabel(key)}</label>
                    {#if spec.type === 'bool'}
                      <div class="flex items-center mt-1"><input id={key} type="checkbox" bind:checked={$jobConfigOverrides[key]} class="h-4 w-4 text-indigo-600 border-gray-300 dark:border-gray-500 rounded focus:ring-indigo-500 bg-white dark:bg-gray-700"></div>
                    {:else if spec.type === 'string'}
                        <input id={key} type="text" bind:value={$jobConfigOverrides[key]} placeholder="Default: {spec.default ?? ''}" class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm placeholder-gray-400 dark:placeholder-gray-500">
                    {:else if spec.type === 'enum'}
                        <select id={key} bind:value={$jobConfigOverrides[key]} class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm appearance-none">
                           {#each spec.options || [] as option (option)} <option value={option}>{option}</option> {/each}
                        </select>
                    {:else if spec.type === 'integer'}
                        <input id={key} type="number" min="1" step="1" bind:value={$jobConfigOverrides[key]} placeholder="Default: {spec.default ?? ''}" class="mt-1 block w-40 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm placeholder-gray-400 dark:placeholder-gray-500">
                    {/if}
                    {#if spec.description} <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{spec.description}</p> {/if}
                  </div>
                {/if}
               {/each}

               <!-- Per-language HF-NER model overrides -->
               <div class="pt-2 border-t border-gray-200 dark:border-gray-700">
                 <div class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">HF‑NER models per language</div>
                 <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                   <div class="flex flex-col">
                     <label class="text-xs text-gray-500 dark:text-gray-400">English (en)</label>
                     <input type="text" value={getNerLang('en')}
                       on:input={(e)=>updateNerLang('en', e.target.value)}
                       placeholder="dslim/bert-base-NER" class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-100 rounded-md px-2 py-1"/>
                   </div>
                   <div class="flex flex-col">
                     <label class="text-xs text-gray-500 dark:text-gray-400">Nederlands (nl)</label>
                     <input type="text" value={getNerLang('nl')}
                       on:input={(e)=>updateNerLang('nl', e.target.value)}
                       placeholder="GroNLP/bert-base-dutch-cased" class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-100 rounded-md px-2 py-1"/>
                   </div>
                   <div class="flex flex-col">
                     <label class="text-xs text-gray-500 dark:text-gray-400">Français (fr)</label>
                     <input type="text" value={getNerLang('fr')}
                       on:input={(e)=>updateNerLang('fr', e.target.value)}
                       placeholder="Jean-Baptiste/camembert-ner" class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-100 rounded-md px-2 py-1"/>
                   </div>
                   <div class="flex flex-col">
                     <label class="text-xs text-gray-500 dark:text-gray-400">Deutsch (de)</label>
                     <input type="text" value={getNerLang('de')}
                       on:input={(e)=>updateNerLang('de', e.target.value)}
                       placeholder="dbmdz/bert-base-german-…" class="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-100 rounded-md px-2 py-1"/>
                   </div>
                 </div>
                 <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">Laat leeg om te fallbacken op het algemene NER‑model.</p>
               </div>
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
               <!-- Model Manager integrated here -->
               <div class="pt-2">
                 <div class="flex items-center justify-between mb-2">
                   <p class="text-sm font-medium text-gray-700 dark:text-gray-300">LLM Model Selection</p>
                   <div class="flex items-center gap-2">
                     <button class="text-xs px-2 py-1 rounded bg-emerald-600 text-white" on:click={applyM1Max32Preset} disabled={modelLoading}>M1 Max 32GB preset</button>
                     <button class="text-xs px-2 py-1 rounded bg-slate-200 dark:bg-slate-700" on:click={refreshModels} disabled={modelLoading}>{modelLoading ? 'Refreshing…' : 'Refresh'}</button>
                   </div>
                 </div>

                 {#if systemSpecs.device}
                   <div class="text-xs text-slate-600 dark:text-slate-400 mb-2">
                     Detected: {systemSpecs.os}/{systemSpecs.machine}, CPU cores: {systemSpecs.cpu_count || '?'}, RAM: {systemSpecs.memory_gb ? `${systemSpecs.memory_gb} GB` : '?'}, Device: {systemSpecs.device}
                   </div>
                 {/if}

                 {#if modelError}
                   <div class="text-sm text-red-600 dark:text-red-400 mb-2">{modelError}</div>
                 {/if}

                 <div class="grid md:grid-cols-2 gap-4">
                   <div>
                     <h4 class="text-sm font-medium mb-2">Beschikbare modellen (curated)</h4>
                     <ul class="space-y-2">
                       {#each modelCatalog as item}
                         <li class="p-2 rounded border dark:border-slate-700">
                           <div class="flex items-center justify-between">
                             <div>
                               <div class="font-mono text-xs sm:text-sm">{item.name}</div>
                               <div class="text-xs text-slate-600 dark:text-slate-400">{item.summary}</div>
                             </div>
                             <div>
                               {#if (localModels || []).includes(item.name)}
                                 <span class="text-xs px-2 py-1 rounded bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">Installed</span>
                               {:else}
                                 <button class="btn btn-primary text-xs px-2 py-1" on:click={() => pullModel(item.name)} disabled={modelLoading}>Pull</button>
                               {/if}
                             </div>
                           </div>
                         </li>
                       {/each}
                     </ul>
                   </div>

                   <div>
                     <h4 class="text-sm font-medium mb-2">Toewijzen aan taken</h4>
                     <div class="space-y-3">
                       {#each tasks as t}
                         <div>
                           <label class="block text-sm font-medium capitalize mb-1" for={`model-select-${t}`}>{t.replace('_',' ')}</label>
                           <div class="flex flex-wrap gap-2 mb-2">
                             {#each (modelAssigned[t] || []) as m}
                               <span class="text-xs px-2 py-1 rounded-full bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                                 {m}
                                 <button class="ml-1 text-indigo-800 dark:text-indigo-200" title="remove" on:click={() => removeModel(t, m)}>×</button>
                               </span>
                             {/each}
                             {#if !(modelAssigned[t] && modelAssigned[t].length)}
                               <span class="text-xs text-slate-500">(geen selectie)</span>
                             {/if}
                           </div>
                           <div class="flex items-center gap-2">
                             <select id={`model-select-${t}`} class="flex-1 text-sm px-2 py-1 border rounded dark:bg-slate-900 dark:border-slate-700" bind:value={toAdd[t]}>
                               <option value="">— Kies model —</option>
                               {#if modelLoading}
                                 <option value="" disabled>Loading…</option>
                               {/if}
                               {#each modelOptions as opt (opt.value)}
                                 <option value={opt.value}>{opt.label}{recommended[t] === opt.value ? ' — recommended' : ''}</option>
                               {/each}
                             </select>
                             <button class="btn btn-primary text-sm px-2 py-1" on:click={() => addModel(t)}>Add</button>
                           </div>
                         </div>
                       {/each}
                       <div class="pt-2">
                         <button class="btn btn-primary px-3 py-1" on:click={saveModelAssignments} disabled={modelLoading}>Opslaan in config.yaml</button>
                       </div>
                     </div>
                   </div>
                 </div>
               </div>
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
      /* Style removed for .dark select as it was unused */
  </style>
