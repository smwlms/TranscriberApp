<script>
  import { onMount } from 'svelte';
  import { getOllamaCatalog, pullOllamaModel, assignLlmModels } from '../api.js';
  import { configInfo } from '../stores.js';

  let catalog = [];
  let local = [];
  let loading = false;
  let error = null;
  let assigned = {
    summary: [], intent: [], actions: [], emotion: [], questions: [], legal: [], name_detection: [], final: []
  }; // {task: [models]}

  const tasks = ['summary','intent','actions','emotion','questions','legal','name_detection','final'];

  // Build option list for selects: installed models first, then others from catalog
  function allOptions() {
    const set = new Set([...(local || [])]);
    for (const item of catalog || []) set.add(item.name);
    const list = Array.from(set.values());
    const installed = new Set(local || []);
    // Sort installed first, then alphabetically
    list.sort((a,b) => {
      const ia = installed.has(a) ? 0 : 1;
      const ib = installed.has(b) ? 0 : 1;
      if (ia !== ib) return ia - ib;
      return a.localeCompare(b);
    });
    return list.map(name => ({
      value: name,
      label: installed.has(name) ? `${name} (installed)` : name
    }));
  }

  async function refresh() {
    loading = true; error = null;
    try {
      const data = await getOllamaCatalog();
      catalog = data.catalog || [];
      local = data.local || [];
    } catch (e) {
      error = e.message || String(e);
    } finally { loading = false; }
  }

  async function pull(model) {
    if (!confirm(`Model '${model}' downloaden?`)) return;
    loading = true; error = null;
    try {
      await pullOllamaModel(model);
      await refresh();
    } catch (e) { error = e.message || String(e); }
    finally { loading = false; }
  }

  async function saveAssignments() {
    const filtered = {};
    for (const t of tasks) {
      if (Array.isArray(assigned[t]) && assigned[t].length) filtered[t] = assigned[t];
    }
    if (!Object.keys(filtered).length) { alert('Geen toewijzingen om op te slaan.'); return; }
    loading = true; error = null;
    try {
      await assignLlmModels(filtered);
      alert('Opgeslagen in config.yaml');
    } catch (e) { error = e.message || String(e); }
    finally { loading = false; }
  }

  // Preset for Apple Silicon M1/M2/M3 with 32GB RAM (your machine)
  function applyM1Max32Preset() {
    assigned = {
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

  onMount(refresh);
</script>

<section class="mt-4 p-4 border rounded-lg bg-white/70 dark:bg-slate-800/50 dark:border-slate-700">
  <div class="flex items-center justify-between mb-3">
    <h2 class="text-lg font-semibold text-slate-800 dark:text-slate-100">Model Manager</h2>
    <button class="px-3 py-1 text-sm rounded bg-slate-200 dark:bg-slate-700" on:click={refresh} disabled={loading}>
      {loading ? 'Refreshing…' : 'Refresh'}
    </button>
  </div>

  {#if error}
    <div class="text-sm text-red-600 dark:text-red-400 mb-3">{error}</div>
  {/if}

  <div class="grid md:grid-cols-2 gap-4">
    <div>
      <h3 class="font-medium mb-2">Beschikbare modellen (curated)</h3>
      <ul class="space-y-2">
        {#each catalog as item}
          <li class="p-2 rounded border dark:border-slate-700">
            <div class="flex items-center justify-between">
              <div>
                <div class="font-mono text-sm">{item.name}</div>
                <div class="text-xs text-slate-600 dark:text-slate-400">{item.summary}</div>
                <div class="text-xs text-slate-500 mt-1">Best for: {item.best_for?.join(', ')}</div>
              </div>
              <div class="text-right">
                {#if item.available}
                  <span class="text-xs px-2 py-1 rounded bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">Installed</span>
                {:else}
                  <button class="text-xs px-2 py-1 rounded bg-blue-600 text-white" on:click={() => pull(item.name)} disabled={loading}>Pull</button>
                {/if}
              </div>
            </div>
          </li>
        {/each}
      </ul>
    </div>

    <div>
      <div class="flex items-center justify-between mb-2">
        <h3 class="font-medium">Toewijzen aan taken</h3>
        <button class="text-xs px-2 py-1 rounded bg-emerald-600 text-white" on:click={applyM1Max32Preset} disabled={loading}>M1 Max 32GB preset</button>
      </div>
      <div class="space-y-2">
        {#each tasks as t}
          <div class="flex items-center gap-2">
            <label class="min-w-36 text-sm font-medium capitalize">{t.replace('_',' ')}</label>
            <select class="flex-1 text-sm px-2 py-1 border rounded dark:bg-slate-900 dark:border-slate-700"
                    multiple size="4"
                    bind:value={assigned[t]}
            >
              {#each allOptions() as opt}
                <option value={opt.value}>{opt.label}</option>
              {/each}
            </select>
          </div>
        {/each}
        <div class="pt-2">
          <button class="px-3 py-1 rounded bg-indigo-600 text-white" on:click={saveAssignments} disabled={loading}>Opslaan in config.yaml</button>
        </div>
      </div>
    </div>
  </div>
</section>

<style>
  .min-w-36 { min-width: 9rem; }
</style>
