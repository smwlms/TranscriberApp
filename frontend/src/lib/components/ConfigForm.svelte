<script>
    import { configInfo, jobConfigOverrides } from '../stores.js';
  
    // Reactive statement: $configInfo will automatically update when the store changes
    // We extract the schema part for easier access in the template
    $: schema = $configInfo.schema || {};
  
    // Reactive statement: When the schema changes, initialize overrides
    // This ensures that when config loads, overrides get populated with defaults
    // We only set overrides for keys present in the schema.
    $: {
        if (schema && Object.keys(schema).length > 0) {
            const initialOverrides = {};
            for (const key in schema) {
                if (schema[key] && schema[key].default !== undefined) {
                    // Only include keys that are simple types (handled by form)
                    const simpleTypes = ["string", "integer", "float", "bool", "enum"];
                    if (simpleTypes.includes(schema[key].type)) {
                        initialOverrides[key] = schema[key].default;
                    }
                }
            }
            // Initialize the store only if it's currently empty or schema reloaded
            if (Object.keys($jobConfigOverrides).length === 0) {
                jobConfigOverrides.set(initialOverrides);
                console.log('[ConfigForm] Initialized overrides with defaults:', initialOverrides);
            }
        }
    }
  
    // Helper to generate a readable label from a key
    function formatLabel(key) {
        return key
            .replace(/_/g, ' ') // Replace underscores with spaces
            .replace(/([A-Z])/g, ' $1') // Add space before capital letters
            .replace(/^./, (str) => str.toUpperCase()); // Capitalize first letter
    }
  
    // Define which types should have input controls generated
    // Exclude complex types like 'object' (llm_models) or file paths set elsewhere
    const editableTypes = ["string", "integer", "float", "bool", "enum"];
    const excludedKeys = ["input_audio", "intermediate_transcript_path", "llm_models", "hf_token"]; // Keys handled elsewhere or too complex for form
  
  </script>
  
  <div class="bg-white p-6 rounded-lg shadow-md">
    <h2 class="text-xl font-semibold mb-4 text-gray-700">2. Configure Pipeline</h2>
  
    {#if !schema || Object.keys(schema).length === 0}
      <p class="text-gray-500 italic">Loading configuration options...</p>
    {:else}
      <form class="space-y-4">
        {#each Object.entries(schema) as [key, spec]}
          {#if editableTypes.includes(spec.type) && !excludedKeys.includes(key)}
            <div class="flex flex-col border-b border-gray-200 pb-3 last:border-b-0">
              <label for={key} class="block text-sm font-medium text-gray-700 mb-1">
                {formatLabel(key)}
              </label>
  
              {#if spec.type === 'enum'}
                <select id={key} bind:value={$jobConfigOverrides[key]} class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm">
                  {#each spec.options || [] as option}
                    <option value={option}>{option}</option>
                  {/each}
                </select>
  
              {:else if spec.type === 'bool'}
                <input id={key} type="checkbox" bind:checked={$jobConfigOverrides[key]} class="mt-1 h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500">
  
              {:else if spec.type === 'integer'}
                <input id={key} type="number" step="1" bind:value={$jobConfigOverrides[key]} placeholder={spec.default} class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
  
              {:else if spec.type === 'float'}
                 <input id={key} type="number" step="any" bind:value={$jobConfigOverrides[key]} placeholder={spec.default} class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
  
              {:else if key === 'extra_context_prompt'}
                  <textarea id={key} rows="3" bind:value={$jobConfigOverrides[key]} placeholder="Optional: Provide extra context for LLM analysis..." class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"></textarea>
  
              {:else if spec.type === 'string'}
                 {#if key === 'language'}
                   <input id={key} type="text" bind:value={$jobConfigOverrides[key]} placeholder="e.g., 'en', 'nl' (leave empty for auto-detect)" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                 {:else}
                   <input id={key} type="text" bind:value={$jobConfigOverrides[key]} placeholder={spec.default} class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                 {/if}
  
              {/if}
  
              {#if spec.description}
                <p class="mt-1 text-xs text-gray-500">{spec.description}</p>
              {/if}
            </div>
          {/if}
        {/each}
      </form>
    {/if}
  </div>