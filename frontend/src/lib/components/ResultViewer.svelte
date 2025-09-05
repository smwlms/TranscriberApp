<!-- frontend/src/lib/components/ResultViewer.svelte -->
<script>
  import { onMount, afterUpdate, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store';
  import { apiBaseUrl } from '../stores.js';
  import { reAnalyze } from '../api.js';
  import CopyIcon from '../icons/Copy.svelte';

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
  $: finalJsonUrl = `${get(apiBaseUrl).replace('/api/v1','')}/transcripts/final_transcript.json`;
  $: finalHtmlUrl = htmlPath || '';

  async function loadResources() {
    if (htmlPath) {
      try { transcriptHtml = await (await fetch(htmlPath, { cache: 'no-store' })).text(); }
      catch (err) { transcriptHtml = `<p class=\"text-red-600\">Kon transcript niet laden: ${err.message}</p>`; }
    }
    if (summaryPath) {
      try { summaryText = await (await fetch(summaryPath, { cache: 'no-store' })).text(); }
      catch (err) { summaryText = `Kon samenvatting niet laden: ${err.message}`; }
    }
    if (advancedPath) {
      try {
        const res = await fetch(advancedPath, { cache: 'no-store' });
        if (res.ok) advanced = await res.json();
      } catch (err) { /* optional */ }
    }
  }

  onMount(loadResources);

  let prevPaths = { htmlPath, summaryPath, advancedPath };
  $: if (htmlPath !== prevPaths.htmlPath || summaryPath !== prevPaths.summaryPath || advancedPath !== prevPaths.advancedPath) {
    prevPaths = { htmlPath, summaryPath, advancedPath };
    loadResources();
  }

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

  // Provide keyboard accessibility equivalent to click on container
  function onTranscriptKeydown(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onTranscriptClick(e);
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

  async function copyToClipboard(text) {
    try { await navigator.clipboard.writeText(text || ''); }
    catch (e) { console.error('Copy failed', e); }
  }

  // Lightweight rich-text renderer: paragraphs + bullet/numbered lists
  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
  }
  function toRichHtml(text) {
    const lines = (text || '').split(/\r?\n/);
    let html = '';
    let mode = null; // 'ul' | 'ol'
    const flush = () => { if (mode) { html += `</${mode}>`; mode = null; } };
    for (const raw of lines) {
      const line = raw.trimEnd();
      const ul = /^[-*]\s+(.+)$/.exec(line);
      const ol = /^(\d+)\.\s+(.+)$/.exec(line);
      if (ul) {
        if (mode !== 'ul') { flush(); mode = 'ul'; html += '<ul class="list-disc pl-5">'; }
        html += `<li>${escapeHtml(ul[1])}</li>`; continue;
      }
      if (ol) {
        if (mode !== 'ol') { flush(); mode = 'ol'; html += '<ol class="list-decimal pl-5">'; }
        html += `<li>${escapeHtml(ol[2])}</li>`; continue;
      }
      if (line === '') { flush(); html += '<p></p>'; continue; }
      flush(); html += `<p>${escapeHtml(line)}</p>`;
    }
    flush();
    return html || '<p></p>';
  }
</script>
  
  <div class="surface-card space-y-6">
    <div class="title-stack">
      <h3 class="text-lg font-semibold">Transcript</h3>
      {#if audioSrc}
        <audio bind:this={audioEl} controls src={audioSrc} class="w-full max-w-full" on:timeupdate={onAudioTimeUpdate}></audio>
      {/if}
      <div class="flex items-center gap-2">
        <button class="btn btn-ghost text-xs" on:click={() => showTranscript = !showTranscript}>{showTranscript ? 'Verberg transcript' : 'Toon transcript'}</button>
        <a class="btn btn-ghost text-xs" href={finalJsonUrl} download>Download JSON</a>
        {#if finalHtmlUrl}
          <a class="btn btn-ghost text-xs" href={finalHtmlUrl} download>Download HTML</a>
        {/if}
        <button class="btn btn-soft text-xs" on:click={toggleEditor}>{showEditor ? 'Editor sluiten' : 'Edit & Re‑analyze'}</button>
      </div>
    </div>
    {#if showTranscript}
      <div
        class="prose dark:prose-invert max-w-none"
        bind:this={containerEl}
        on:click={onTranscriptClick}
        on:keydown={onTranscriptKeydown}
        role="button"
        tabindex="0"
        aria-label="Transcript: klik of druk Enter/Spatie om naar woordtijd te springen"
      >
        {@html transcriptHtml}
      </div>
    {/if}
  
    <div class="flex items-center justify-between">
      <h3 class="text-[1.05rem] font-semibold">Samenvatting</h3>
      <button class="chip" aria-label="Copy summary" title="Copy" on:click={() => copyToClipboard(summaryText)}>
        <CopyIcon size={16} />
      </button>
    </div>
    <div class="surface-card rt">{@html toRichHtml(summaryText)}</div>

    {#if advanced}
      <div class="mt-4">
        <h3 class="text-lg font-semibold">Advanced Analyse</h3>
        {#each Object.entries(advanced) as [key, val] (key)}
          {#if typeof val === 'string' && val}
            <details class="mt-2 surface-card">
              <summary class="cursor-pointer px-3 py-2 text-sm font-medium text-gray-800 dark:text-gray-100 flex items-center justify-between">
                <span>{key}</span>
                <button type="button" class="p-1.5 rounded-md bg-slate-700/60 hover:bg-slate-600 text-white" aria-label="Copy analysis" on:click={(e)=>{e.preventDefault();copyToClipboard(val);}}>
                  <CopyIcon size={16} />
                </button>
              </summary>
              <div class="px-3 py-2 text-sm rt">{@html toRichHtml(val)}</div>
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
