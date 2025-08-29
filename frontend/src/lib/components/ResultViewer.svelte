<!-- frontend/src/lib/components/ResultViewer.svelte -->
<script>
  import { onMount, afterUpdate, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store';
  import { apiBaseUrl } from '../stores.js';
  import { reAnalyze } from '../api.js';

  export let htmlPath;
  export let summaryPath;
  export let advancedPath = 'results/advanced_analysis.json';
  export let jobId;
  export let audioRelativePath; // e.g., 'audio/xyz.mp3'

  const dispatch = createEventDispatcher();

  let transcriptHtml = '';
  let summaryText  = '';
  let advanced = null; // advanced analysis JSON
  let showTranscript = true;
  let showEditor = false;
  let editing = false;
  let isSubmitting = false;
  let editSegments = [];
  let containerEl; // transcript container for event delegation
  let audioEl;

  // Cache of word spans for highlighting during playback
  let wordSpans = [];
  let currentHighlightedEl = null;

  $: audioSrc = audioRelativePath ? `${get(apiBaseUrl).replace('/api/v1','')}/${audioRelativePath}` : null;

  async function loadResources() {
    if (htmlPath) {
      try { transcriptHtml = await (await fetch(htmlPath)).text(); }
      catch (err) { transcriptHtml = `<p class=\"text-red-600\">Kon transcript niet laden: ${err.message}</p>`; }
    }
    if (summaryPath) {
      try { summaryText = await (await fetch(summaryPath)).text(); }
      catch (err) { summaryText = `Kon samenvatting niet laden: ${err.message}`; }
    }
    if (advancedPath) {
      try {
        const res = await fetch(advancedPath);
        if (res.ok) advanced = await res.json();
      } catch (err) { /* optional */ }
    }
  }

  onMount(loadResources);

  // Build/refresh the local cache of word spans when HTML changes
  function buildWordIndex() {
    if (!containerEl) return;
    const nodes = containerEl.querySelectorAll('span.word');
    wordSpans = Array.from(nodes)
      .map((el) => {
        const s = parseFloat(el.dataset.start || 'NaN');
        const e = parseFloat(el.dataset.end || 'NaN');
        return Number.isNaN(s) || Number.isNaN(e) ? null : { el, s, e };
      })
      .filter(Boolean);
  }

  afterUpdate(buildWordIndex);

  // Clicking on per-word spans seeks the audio
  function onTranscriptClick(e) {
    const span = e.target && e.target.closest && e.target.closest('span.word');
    if (!span || !audioEl) return;
    const s = parseFloat(span.dataset.start || 'NaN');
    if (!Number.isNaN(s)) {
      audioEl.currentTime = s;
      audioEl.play().catch(() => {});
    }
  }

  // Highlight the current word while the audio plays
  function onAudioTimeUpdate() {
    if (!audioEl || !wordSpans.length) return;
    const t = audioEl.currentTime;
    // Find first span whose [s,e) window contains current time
    let active = null;
    for (let i = 0; i < wordSpans.length; i++) {
      const w = wordSpans[i];
      if (t >= w.s && t < w.e) { active = w; break; }
    }
    if (active?.el !== currentHighlightedEl) {
      if (currentHighlightedEl) currentHighlightedEl.classList.remove('highlight');
      currentHighlightedEl = active?.el || null;
      if (currentHighlightedEl) {
        currentHighlightedEl.classList.add('highlight');
        // Keep the active word in view without big jumps
        currentHighlightedEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
      }
    }
  }

  async function toggleEditor() {
    showEditor = !showEditor;
    if (showEditor && editSegments.length === 0) {
      try {
        const base = get(apiBaseUrl).replace('/api/v1','');
        const res = await fetch(`${base}/transcripts/final_transcript.json`);
        editSegments = await res.json();
      } catch (e) {
        editSegments = [];
      }
    }
  }

  async function submitReAnalyze() {
    if (!jobId) return;
    isSubmitting = true;
    try {
      await reAnalyze(jobId, editSegments);
      // Inform parent (JobRunner) to resume polling
      dispatch('rerun');
    } catch (e) {
      alert('Re-analyze failed: ' + (e.message || e));
    } finally {
      isSubmitting = false;
    }
  }
</script>
  
  <div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md space-y-6 transition-colors duration-150">
    <div class="flex items-center justify-between">
      <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200">Transcript</h3>
      <div class="flex items-center gap-2">
        {#if audioSrc}
          <audio bind:this={audioEl} controls src={audioSrc} class="h-8" on:timeupdate={onAudioTimeUpdate}></audio>
        {/if}
        <button class="text-sm px-2 py-1 rounded bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-100" on:click={() => showTranscript = !showTranscript}>
        {showTranscript ? 'Verberg' : 'Toon'}
        </button>
        <button class="text-sm px-2 py-1 rounded bg-indigo-600 text-white" on:click={toggleEditor}>{showEditor ? 'Sluit editor' : 'Edit & Re‑analyze'}</button>
      </div>
    </div>
    {#if showTranscript}
      <div class="prose dark:prose-invert max-w-none" bind:this={containerEl} on:click={onTranscriptClick}>
        {@html transcriptHtml}
      </div>
    {/if}
  
    <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200">Samenvatting</h3>
    <pre class="bg-gray-100 dark:bg-gray-700 p-4 rounded overflow-x-auto text-sm">
  {summaryText}
    </pre>

    {#if advanced}
      <div class="mt-4">
        <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200">Advanced Analyse</h3>
        {#each Object.entries(advanced) as [key, val] (key)}
          {#if typeof val === 'string' && val}
            <details class="mt-2 bg-gray-100 dark:bg-gray-700 rounded">
              <summary class="cursor-pointer px-3 py-2 text-sm font-medium text-gray-800 dark:text-gray-100">{key}</summary>
              <pre class="px-3 py-2 text-sm whitespace-pre-wrap">{val}</pre>
            </details>
          {/if}
        {/each}
      </div>
    {/if}

    {#if showEditor}
      <div class="mt-4 border-t border-gray-700 pt-4">
        <h4 class="text-md font-semibold mb-2 text-gray-700 dark:text-gray-200">Transcript Editor</h4>
        {#if !editSegments || !editSegments.length}
          <p class="text-sm text-slate-500">Kon final_transcript.json niet laden of transcript is leeg.</p>
        {:else}
          <div class="space-y-2 max-h-64 overflow-y-auto">
            {#each editSegments as seg, i}
              <div class="flex gap-2 items-start">
                <input class="w-40 text-sm px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 border dark:border-gray-600" bind:value={seg.speaker_name} title="Speaker name" />
                <textarea rows="2" class="flex-1 text-sm px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 border dark:border-gray-600" bind:value={seg.text}></textarea>
              </div>
            {/each}
          </div>
          <div class="mt-2 flex justify-end">
            <button class="px-3 py-1 rounded bg-indigo-600 text-white disabled:opacity-50" on:click={submitReAnalyze} disabled={isSubmitting}>{isSubmitting ? 'Bezig…' : 'Analyse opnieuw'}</button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
  

<style>
  :global(.highlight) {
    background-color: #2563eb;
    color: #fff;
    border-radius: 3px;
    padding: 0 2px;
  }
</style>
