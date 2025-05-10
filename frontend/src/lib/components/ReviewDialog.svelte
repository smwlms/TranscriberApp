<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store';
  import { apiBaseUrl } from '../stores.js';
  import {
    getReviewData as apiGetReviewData,
    updateReviewData as apiUpdateReviewData,
    updateTranscriptData
  } from '../api.js';
  
  export let jobId;
  export let audioRelativePath;
  const dispatch = createEventDispatcher();
  
  let isLoading = true;
  let error = '';
  
  // Review‐data
  let transcript = [];
  let proposedMap = {};
  let contextSnippets = {};
  let uniqueSpeakers = [];
  let editedMap = {};
  let contextVisible = {};
  
  // Transcript‐edit modus
  let isEditingTranscript = false;
  let editedTranscript = {}; // object met keys=segment-index en values=nieuwe tekst
  
  // Karaoke
  let audioPlayer;
  let currentWordId = null;
  
  onMount(fetchReviewData);
  onDestroy(() => {
    if (audioPlayer && !audioPlayer.paused) audioPlayer.pause();
  });
  
  async function fetchReviewData() {
    isLoading = true;
    error = '';
    try {
      const data = await apiGetReviewData(jobId);
      transcript = data.intermediate_transcript || [];
      proposedMap = data.proposed_map || {};
      contextSnippets = data.context_snippets || {};
  
      // unieke speakers
      uniqueSpeakers = Array.from(new Set(transcript.map((s) => s.speaker)));
  
      // init speaker‐map en context visibility
      const im = {},
        iv = {};
      uniqueSpeakers.forEach((id) => {
        im[id] = proposedMap[id]?.name ?? '';
        iv[id] = false;
      });
      editedMap = im;
      contextVisible = iv;
    } catch (e) {
      error = `Fout bij laden review data: ${e.message}`;
    } finally {
      isLoading = false;
    }
  }
  
  function toggleContext(id) {
    contextVisible[id] = !contextVisible[id];
    contextVisible = { ...contextVisible };
  }
  
  function getRelevantContext(id) {
    const idx = proposedMap[id]?.reasoning_indices || [];
    if (!idx.length) return 'Geen context beschikbaar.';
    return idx
      .map((i) => contextSnippets[String(i)] ?? `(Snippet ${i} niet gevonden)`)
      .join('\n–––\n');
  }
  
  /** Start edit‐modus en preload alle segment‐teksten */
  function toggleEditTranscript() {
    if (!isEditingTranscript) {
      // entering edit mode: vul editedTranscript
      const temp = {};
      transcript.forEach((seg, i) => {
        temp[i] = seg.words?.map((w) => w.word).join(' ') || seg.text;
      });
      editedTranscript = temp;
    }
    isEditingTranscript = !isEditingTranscript;
    error = '';
  }
  
  /** Opslaan van alleen de aangepaste transcriptie */
  async function saveTranscript() {
    isLoading = true;
    error = '';
    try {
      // nieuw transcript‐array met geüpdatete tekst
      const newTrans = transcript.map((seg, i) => ({
        ...seg,
        text: editedTranscript[i] ?? '',
        words: [] // backend kan hier opnieuw tokenizen
      }));
  
      await updateTranscriptData(jobId, newTrans);
      transcript = newTrans; // reflecteer direct in UI
      isEditingTranscript = false;
    } catch (e) {
      error = `Fout bij opslaan transcriptie: ${e.message}`;
      throw e; // opnieuw gooien zodat saveAll() kan afbreken
    } finally {
      isLoading = false;
    }
  }
  
  /**
   * Finale save: 1) evt. transcript updaten, 2) speaker‑map posten,
   * en 3) dialog sluiten. Hiermee voorkomen we de race‑condition waarbij
   * /update_review_data de status al wijzigt vóór de transcript is opgeslagen.
   */
  async function saveAll() {
    isLoading = true;
    error = '';
    try {
      // 1. Transcript eerst – alleen als er wijzigingen zijn
      if (isEditingTranscript && Object.keys(editedTranscript).length) {
        await saveTranscript();
      }
  
      // 2. Speaker‑map posten en Part 2 triggeren
      await apiUpdateReviewData(jobId, editedMap);
  
      // 3. Informeer parent (JobRunner) dat review afgerond is
      dispatch('submit');
    } catch (e) {
      // saveTranscript kan hier ook exceptions bubbelen
      if (!error) error = `Fout bij opslaan: ${e.message}`;
    } finally {
      isLoading = false;
    }
  }
  
  function handleTimeUpdate() {
    if (!audioPlayer) return;
    const t = audioPlayer.currentTime;
    let found = null;
    for (let i = 0; i < transcript.length; i++) {
      const seg = transcript[i];
      if (!Array.isArray(seg.words)) continue;
      for (let j = 0; j < seg.words.length; j++) {
        const w = seg.words[j];
        if (t >= w.start && t < w.end) {
          found = `word-${i}-${j}`;
          break;
        }
      }
      if (found) break;
    }
    if (found !== currentWordId) {
      currentWordId = found;
      if (found) {
        const el = document.getElementById(found);
        el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  }
  
  function cancel() {
    dispatch('cancel');
  }
  </script>
  
  <div class="fixed inset-0 bg-gray-800 bg-opacity-60 flex items-center justify-center p-4 z-50">
    <div class="bg-gray-900 text-gray-100 rounded-lg w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
      <!-- Header -->
      <header class="flex justify-between items-center p-4 border-b border-gray-700">
        <h2 class="text-lg font-semibold">Speaker Review</h2>
        <button on:click={cancel} class="text-xl hover:text-gray-300">&times;</button>
      </header>
  
      <!-- Body -->
      <main class="flex-1 overflow-auto p-4 space-y-6">
        {#if isLoading}
          <p class="text-center text-gray-400">Laden…</p>
        {:else if error}
          <div class="bg-red-700 p-3 rounded text-red-100">
            <strong>Fout:</strong> {error}
          </div>
        {:else}
          <!-- Audio player -->
          {#if audioRelativePath}
            <audio
              bind:this={audioPlayer}
              controls
              class="w-full mb-4"
              preload="metadata"
              on:timeupdate={handleTimeUpdate}
              src={`${get(apiBaseUrl).replace('/api/v1', '')}/${audioRelativePath}`}
            />
          {/if}
  
          <!-- Speaker mapping -->
          <section>
            <h3 class="mb-3 text-gray-300">Spreker Namen Toewijzen</h3>
            {#if uniqueSpeakers.length === 0}
              <p class="text-gray-400 italic">Geen sprekers gevonden.</p>
            {/if}
  
            {#each uniqueSpeakers as id}
              <div class="flex flex-col sm:flex-row items-start space-y-2 sm:space-y-0 sm:space-x-2 mb-3">
                <label for={'sp-' + id} class="w-32 font-mono text-sm text-gray-200">{id}:</label>
                <input
                  id={'sp-' + id}
                  type="text"
                  bind:value={editedMap[id]}
                  placeholder={proposedMap[id]?.name ?? 'Naam invoeren...'}
                  class="flex-1 p-1.5 rounded bg-gray-800 text-gray-100 border border-gray-700 focus:ring"
                />
                {#if proposedMap[id]?.reasoning_indices?.length}
                  <button on:click={() => toggleContext(id)} class="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600">
                    Waarom?
                  </button>
                {/if}
              </div>
  
              {#if contextVisible[id]}
                <pre class="p-3 bg-gray-800 rounded text-gray-300 text-sm overflow-auto max-h-40 border border-gray-700 mb-3">
  {getRelevantContext(id)}
                </pre>
              {/if}
            {/each}
          </section>
  
          <!-- Transcript + edit/save knop -->
          <section>
            <div class="flex justify-between items-center mb-2">
              <h3 class="text-gray-300">Transcript</h3>
              <button on:click={isEditingTranscript ? saveTranscript : toggleEditTranscript} class="px-3 py-1 text-sm rounded bg-indigo-600 hover:bg-indigo-500">
                {isEditingTranscript ? 'Save Transcriptie' : 'Edit Transcriptie'}
              </button>
            </div>
  
            <div class="bg-gray-800 p-4 rounded-lg h-72 overflow-y-auto text-gray-100 text-base border border-gray-700">
              {#each transcript as seg, i}
                <div class="mb-3">
                  <strong class="text-blue-400">{editedMap[seg.speaker] || seg.speaker}:</strong>
  
                  {#if isEditingTranscript}
                    <textarea
                      rows="2"
                      class="w-full mt-1 bg-gray-700 text-gray-100 p-2 rounded border border-gray-600 focus:ring"
                      value={editedTranscript[i]}
                      on:input={(e) => (editedTranscript[i] = e.target.value)}
                    />
                  {:else}
                    <p>
                      {#if Array.isArray(seg.words) && seg.words.length}
                        {#each seg.words as w, j}
                          <span id={`word-${i}-${j}`} class:highlight={currentWordId === `word-${i}-${j}`}>{w.word}&nbsp;</span>
                        {/each}
                      {:else}
                        {seg.text}
                      {/if}
                    </p>
                  {/if}
                </div>
              {/each}
            </div>
          </section>
        {/if}
      </main>
  
      <!-- Footer -->
      <footer class="flex justify-end items-center p-4 border-t border-gray-700 bg-gray-900 space-x-3">
        <button on:click={cancel} disabled={isLoading} class="px-4 py-2 bg-gray-700 rounded hover:bg-gray-600 disabled:opacity-50">
          Annuleren
        </button>
        <button on:click={saveAll} disabled={isLoading || uniqueSpeakers.length === 0} class="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 text-white">
          Bevestigen &amp; Doorgaan
        </button>
      </footer>
    </div>
  </div>
  
  <style>
  .highlight {
    background-color: #2563eb;
    color: white;
    padding: 1px 2px;
    border-radius: 2px;
  }
  </style>