<script>
  import { onMount } from 'svelte';
  import { getHealth } from '../api.js';
  let status = 'unknown';
  let checks = {};
  let error = '';
  let expanded = false;
  let timer;

  async function ping() {
    try {
      const data = await getHealth();
      status = data.status || 'unknown';
      checks = data.checks || {};
      error = '';
    } catch (e) {
      status = 'error';
      checks = {};
      error = e.message || String(e);
    }
  }

  onMount(() => {
    ping();
    timer = setInterval(ping, 30000);
    return () => clearInterval(timer);
  });

  $: color = status === 'ok' ? 'bg-emerald-500' : status === 'degraded' ? 'bg-amber-500' : status === 'error' ? 'bg-red-500' : 'bg-gray-400';
</script>

<div class="flex items-center gap-2">
  <span class={`inline-block w-3 h-3 rounded-full ${color}`} title={`server: ${status}`}></span>
  {#if status !== 'ok'}
    <button class="text-xs text-red-600 dark:text-red-300 underline" on:click={() => expanded=!expanded}>
      {status === 'error' ? 'Server issue' : 'Degraded'}
    </button>
  {/if}
</div>

{#if expanded}
  <div class="mt-2 text-xs p-2 rounded bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-200 border border-red-200 dark:border-red-700">
    <p class="mb-1"><strong>Status:</strong> {status}</p>
    {#if error}
      <p class="mb-1"><strong>HTTP:</strong> {error}</p>
    {/if}
    {#if Object.keys(checks || {}).length}
      <ul class="list-disc ml-4">
        {#each Object.entries(checks) as [k,v] (k)}
          <li>{k}: {String(v)}</li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

<style>
</style>

