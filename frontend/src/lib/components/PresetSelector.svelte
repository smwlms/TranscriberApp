<script>
    import { selectedPreset } from '../stores.js';
  
    // --- Use user's chosen labels and new keys ---
    const presets = [
      { key: 'quick', label: 'Quick and Dirty' },
      { key: 'standard', label: 'Standard Brew' },
      { key: 'multi', label: 'Multi-Task Analysis' }
    ];
    // --- Default preset key ---
    // Ensure the store's default value matches one of these keys ('standard' is good)
    // We assume stores.js initializes selectedPreset to 'standard'
  
    function selectPreset(key) {
      $selectedPreset = key; // Update the store
    }
  
    // --- Button styling ---
    const baseButtonClasses = "px-4 py-1.5 rounded-md text-sm font-medium transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-indigo-500 dark:focus:ring-offset-gray-900";
    const inactiveButtonClasses = "bg-gray-200 text-gray-600 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600";
    const activeButtonClasses = "bg-indigo-600 text-white shadow-sm";
  
  </script>
  
  <div class="mb-4 bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md transition-colors duration-150">
    <div class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2" id="preset-label">
      Processing Preset:
    </div>
    <div class="flex flex-wrap gap-2" role="group" aria-labelledby="preset-label">
      {#each presets as preset (preset.key)}
        <button
          type="button"
          class="{baseButtonClasses} {$selectedPreset === preset.key ? activeButtonClasses : inactiveButtonClasses}"
          aria-pressed={$selectedPreset === preset.key}
          on:click={() => selectPreset(preset.key)}
        >
          {preset.label}
        </button>
      {/each}
    </div>
    {#if $selectedPreset === 'quick'}
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-2">Fastest processing, minimal analysis (summary only), name detection off.</p>
    {:else if $selectedPreset === 'standard'}
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-2">Good balance of speed and quality, includes summary and tries name detection.</p>
    {:else if $selectedPreset === 'multi'}
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-2">More accurate transcription, full advanced analysis (slower).</p>
    {/if}
  </div>
  
  <style> /* Optional styles */ </style>