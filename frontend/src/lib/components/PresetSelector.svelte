<script>
    import { selectedPreset } from '../stores.js';
  
    // --- Use user's chosen labels and new keys ---
    const presets = [
      { key: 'quick', label: 'Quick and Dirty' },
      { key: 'standard', label: 'Standard Brew' },
      { key: 'multi', label: 'Multi-Task Analysis' }
    ];
    // --- Default preset key ('standard' is assumed default in stores.js) ---
  
    function selectPreset(key) {
      $selectedPreset = key; // Update the store
    }
  
    // --- Button styling ---
    const baseButtonClasses = "px-4 py-1.5 rounded-md text-sm font-medium transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-indigo-500 dark:focus:ring-offset-gray-900";
    const inactiveButtonClasses = "bg-gray-200 text-gray-600 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600";
    const activeButtonClasses = "bg-indigo-600 text-white shadow-sm dark:bg-indigo-500";
  
  </script>
  
  <div class="surface-card">
    <div class="section-title mb-2">2. Preset</div>
    <div class="section-subtle mb-3">Kies de balans tussen snelheid en diepte.</div>
    <div class="segmented" role="group" aria-labelledby="preset-label">
      {#each presets as preset (preset.key)}
        <button
          type="button"
          class=""
          aria-pressed={$selectedPreset === preset.key}
          on:click={() => selectPreset(preset.key)}
        >
          {preset.label}
        </button>
      {/each}
    </div>
    {#if $selectedPreset === 'quick'}
        <p class="section-subtle mt-2">Snelste verwerking, minimale analyse (alleen samenvatting).</p>
    {:else if $selectedPreset === 'standard'}
        <p class="section-subtle mt-2">Goede balans tussen snelheid en kwaliteit.</p>
    {:else if $selectedPreset === 'multi'}
        <p class="section-subtle mt-2">Meest nauwkeurig, met uitgebreide analyses (langzamer).</p>
    {/if}
  </div>
  
  <style> /* Optional styles */ </style>
