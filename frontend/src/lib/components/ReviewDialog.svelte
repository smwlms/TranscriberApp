<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store'; // CORRECTED IMPORT
  import { apiBaseUrl } from '../stores.js';
  import {
    getReviewData as apiGetReviewData,
    updateTranscriptData,
    reDetectNames
  } from '../api.js';

  export let jobId;
  export let audioRelativePath;

  const dispatch = createEventDispatcher();

  let isLoading = true;
  let isSaving = false;
  let error = '';

  let transcript = [];
  let proposedMap = {};
  let contextSnippets = {};
  let uniqueSpeakers = [];
  let editedMap = {};
  let contextVisible = {};
  let rolesHint = {};
  let firstSpeakerId = null;

  let isEditingTranscript = false;
  let editedTranscript = {};
  let transcriptContainer; // scroll control when toggling editor

  let audioPlayer;
  let currentWordId = null;

  onMount(async () => {
    await fetchReviewData();
  });

  onDestroy(() => {
    if (audioPlayer && !audioPlayer.paused) {
      audioPlayer.pause();
    }
  });

  async function fetchReviewData() {
    isLoading = true;
    isSaving = false;
    error = '';
    try {
      const data = await apiGetReviewData(jobId);
      transcript = data.intermediate_transcript || [];
      proposedMap = data.proposed_map || {};
      contextSnippets = data.context_snippets || {};
      rolesHint = data.roles_hint || {};
      firstSpeakerId = data.first_speaker_id || null;
      uniqueSpeakers = Array.from(new Set(transcript.map((s) => s.speaker))).sort();

      const initialEditedMap = {};
      const initialContextVisible = {};
      uniqueSpeakers.forEach((id) => {
        initialEditedMap[id] = proposedMap[id]?.name ?? '';
        initialContextVisible[id] = false;
      });
      editedMap = initialEditedMap;
      contextVisible = initialContextVisible;

    } catch (e) {
      console.error('[ReviewDialog] Fetch review data failed:', e);
      error = `Fout bij laden review data: ${e.message}`;
    } finally {
      isLoading = false;
    }
  }

  function toggleContext(speakerId) {
    contextVisible[speakerId] = !contextVisible[speakerId];
  }

  function swapNames() {
    // Simple 2-speaker swap helper. If more, swap the first two.
    const ids = uniqueSpeakers.slice(0, 2);
    if (ids.length < 2) return;
    const a = ids[0], b = ids[1];
    const tmp = editedMap[a];
    editedMap[a] = editedMap[b];
    editedMap[b] = tmp;
  }

  const iconSize = 14;
  const iconColor = '#60a5fa';
  function PhoneOutgoing(){return `<svg width='${iconSize}' height='${iconSize}' viewBox='0 0 24 24' fill='none' xmlns='http://www.w3.org/2000/svg'><path d='M21 16.5v3a2 2 0 0 1-2.18 2 19.86 19.86 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.86 19.86 0 0 1 1.5 3.18 2 2 0 0 1 3.5 1h3a2 2 0 0 1 2 1.72c.12.86.33 1.7.62 2.5a2 2 0 0 1-.45 2.11L7.1 8.9a16 16 0 0 0 6 6l1.57-1.57a2 2 0 0 1 2.11-.45c.8.29 1.64.5 2.5.62A2 2 0 0 1 21 16.5z' stroke='${iconColor}' stroke-width='1.5'/></svg>`}
  function PhoneIncoming(){return `<svg width='${iconSize}' height='${iconSize}' viewBox='0 0 24 24' fill='none' xmlns='http://www.w3.org/2000/svg'><path d='M3 7.5v-3A2 2 0 0 1 5.18 2a19.86 19.86 0 0 1 8.63 3.07 19.5 19.5 0 0 1 6 6A19.86 19.86 0 0 1 22.5 20.82 2 2 0 0 1 20.5 23h-3a2 2 0 0 1-2-1.72 13 13 0 0 1-.62-2.5 2 2 0 0 1 .45-2.11l1.57-1.57a16 16 0 0 1-6-6L8.9 7.1a2 2 0 0 1-2.11-.45 13 13 0 0 1-2.5-.62A2 2 0 0 1 3 7.5z' stroke='${iconColor}' stroke-width='1.5'/></svg>`}
  function normalized(s){return (s||'').toString().trim().toLowerCase();}
  function roleForSpeaker(sid){
    const name = normalized(editedMap[sid] || proposedMap[sid]?.name);
    const caller = normalized(rolesHint.caller);
    const callee = normalized(rolesHint.callee);
    if (name && caller && name === caller) return 'caller';
    if (name && callee && name === callee) return 'callee';
    if (!name && firstSpeakerId && sid === firstSpeakerId && (caller || callee)) return 'caller?';
    return null;
  }

  function getRelevantContext(speakerId) {
    const reasoningIndices = proposedMap[speakerId]?.reasoning_indices || [];
    if (!reasoningIndices.length) return 'Geen context beschikbaar.';
    return reasoningIndices
      .map((i) => contextSnippets[String(i)] ?? `(Snippet ${i} niet gevonden)`)
      .join('\n–––\n');
  }

  const STOP_NAMES = new Set(['van','wel','ja','nee','u','uw','de','het','een','oke','oké','ok','goed','dag','hallo','hoi','hey','bedankt','thanks','als','dat','dit','eh','euh','uh','uhm','hm','meneer','mevrouw','sir','madam','beste','goedemiddag','goedenavond','goedemorgen']);
  function isLikelyName(s){
    if (!s) return false; const t = normalized(s);
    if (!t || STOP_NAMES.has(t)) return false;
    return /^[a-zà-öø-ÿ][a-zà-öø-ÿ\-']{1,}$/i.test(t);
  }
  function greetingMatches() {
    const re = /^(?:ja|hallo|hoi|hey|dag|goedemiddag|goedenavond|goedemorgen)[,\s]+([A-Z][\w\-]+)/i;
    const matches = [];
    const N = Math.min(8, transcript.length);
    for (let i=0;i<N;i++){
      const seg = transcript[i];
      const txt = (seg?.text||'').trim();
      const m = txt && txt.match(re);
      if (m) matches.push({index:i,speaker:seg?.speaker,name:m[1]});
    }
    return matches;
  }
  function whyFor(sid){
    const lines = [];
    const name = editedMap[sid] || proposedMap[sid]?.name || '';
    if (!isLikelyName(name)) lines.push(`Waarschuwing: '${name||'(leeg)'}' lijkt geen geldige naam.`);
    if (rolesHint?.caller) lines.push(`Context: caller = ${rolesHint.caller}`);
    if (rolesHint?.callee) lines.push(`Context: callee = ${rolesHint.callee}`);
    const role = roleForSpeaker(sid);
    if (role) lines.push(`Rol-hint: deze spreker is '${role}'.`);
    const gm = greetingMatches();
    if (gm.length){
      const relevant = gm.map(g=>`[Index ${g.index}] ${g.speaker} begroet '${g.name}' → toegewezen aan andere spreker`).join('\n');
      lines.push('Begroetingspatronen:\n'+relevant);
    }
    const ri = proposedMap[sid]?.reasoning_indices || [];
    if (ri.length){
      const parts = ri.map(i=>contextSnippets[String(i)]||`(snippet ${i} ontbreekt)`).join('\n---\n');
      lines.push('LLM‑context:\n'+parts);
    }
    return lines.join('\n\n');
  }

  function toggleEditTranscript() {
    if (!isEditingTranscript) {
      const tempEditedTranscript = {};
      transcript.forEach((segment, index) => {
        tempEditedTranscript[index] = segment.text;
      });
      editedTranscript = tempEditedTranscript;
    }
    isEditingTranscript = !isEditingTranscript;
    error = '';
    // Scroll editor container to top so user doesn't land at bottom
    try { transcriptContainer && (transcriptContainer.scrollTop = 0); } catch {}
  }

  async function saveTranscriptEdits() {
    isLoading = true;
    error = '';
    try {
      const updatedFullTranscript = transcript.map((segment, index) => ({
        ...segment,
        text: editedTranscript[index] ?? segment.text,
        words: [],
      }));
      // Detect if any of the first N segments changed
      const N = Math.min(8, transcript.length);
      let firstNChanged = false;
      for (let i = 0; i < N; i++) {
        const before = transcript[i]?.text ?? '';
        const after = editedTranscript[i] ?? transcript[i]?.text ?? '';
        if (typeof before === 'string' && typeof after === 'string' && before !== after) {
          firstNChanged = true; break;
        }
      }
      await updateTranscriptData(jobId, updatedFullTranscript);
      transcript = updatedFullTranscript;
      isEditingTranscript = false;
      // If early segments changed, re-run name detection to refresh suggestions
      if (firstNChanged) {
        try {
          const resp = await reDetectNames(jobId);
          if (resp && resp.proposed_map) {
            proposedMap = resp.proposed_map || {};
            contextSnippets = resp.context_snippets || {};
            // Prefill editedMap only where still empty
            Object.keys(proposedMap).forEach((id) => {
              if (!editedMap[id]) editedMap[id] = proposedMap[id]?.name ?? '';
            });
          }
        } catch (e) {
          console.warn('[ReviewDialog] reDetectNames failed:', e);
        }
      }
      console.log('[ReviewDialog] Transcript updated successfully.');
    } catch (e) {
      console.error('[ReviewDialog] Save transcript failed:', e);
      error = `Fout bij opslaan transcriptie: ${e.message}`;
      throw e;
    } finally {
      isLoading = false;
    }
  }

  async function saveAll() {
    if (isSaving) return;
    isSaving = true;
    error = '';
    try {
      if (isEditingTranscript && Object.keys(editedTranscript).length) {
        console.log('[ReviewDialog] Transcript is being edited, saving transcript first...');
        await saveTranscriptEdits();
      }
      console.log('[ReviewDialog] Dispatching final speaker map to parent:', editedMap);
      dispatch('submit', editedMap);
    } catch (e) {
      console.error('[ReviewDialog] saveAll operation failed:', e);
      if (!error) {
        error = `Fout bij opslaan van review: ${e.message}`;
      }
    } finally {
      isSaving = false;
    }
  }

  function seekAudioTo(time) {
    if (audioPlayer && time !== undefined) {
      audioPlayer.currentTime = time;
    }
  }

  function handleWordClick(word) {
    if (word.start !== undefined) {
      seekAudioTo(word.start);
    }
  }

  function handleWordKeydown(event, word) {
    if (word.start !== undefined && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      seekAudioTo(word.start);
    }
  }

  function handleTimeUpdate() {
    if (!audioPlayer || !Array.isArray(transcript)) return;
    const currentTime = audioPlayer.currentTime;
    let foundWordId = null;

    for (let i = 0; i < transcript.length; i++) {
      const segment = transcript[i];
      if (Array.isArray(segment.words) && segment.words.length > 0) {
        for (let j = 0; j < segment.words.length; j++) {
          const word = segment.words[j];
          if (word.start !== undefined && word.end !== undefined && currentTime >= word.start && currentTime < word.end) {
            foundWordId = `word-${i}-${j}`;
            break;
          }
        }
      }
      if (foundWordId) break;
    }

    if (foundWordId !== currentWordId) {
      currentWordId = foundWordId;
      if (foundWordId) {
        const element = document.getElementById(foundWordId);
        element?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  }

  function cancelReview() {
    dispatch('cancel');
  }

  $: audioSrc = audioRelativePath ? `${get(apiBaseUrl).replace('/api/v1', '')}/${audioRelativePath}` : null;

</script>

<div class="fixed inset-0 bg-gray-800 bg-opacity-60 flex items-center justify-center p-4 z-50">
  <div class="bg-gray-900 text-gray-100 rounded-lg w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl">
    <header class="flex justify-between items-center p-4 border-b border-gray-700">
      <h2 class="text-lg font-semibold">Speaker & Transcript Review</h2>
      <button on:click={cancelReview} disabled={isSaving} class="text-2xl hover:text-gray-300 disabled:opacity-50 transition-opacity">&times;</button>
    </header>

    <main class="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
      {#if isLoading && !isSaving}
        <div class="flex justify-center items-center h-full">
          <p class="text-gray-400 text-lg">Review data laden…</p>
        </div>
      {:else if error}
        <div class="bg-red-800 p-4 rounded text-red-100 border border-red-600">
          <strong class="block mb-2">Fout:</strong>
          <p class="mb-3">{error}</p>
          {#if !isSaving}
            <button on:click={fetchReviewData}
              class="px-3 py-1.5 bg-yellow-500 text-black rounded hover:bg-yellow-600 text-sm mr-2">
              Opnieuw proberen
            </button>
          {/if}
        </div>
      {/if}

      {#if !isLoading || error}
        <fieldset disabled={isSaving || (isLoading && !error)} class="space-y-6">
          {#if audioSrc}
            <section>
              <audio
                bind:this={audioPlayer}
                controls
                class="w-full"
                preload="metadata"
                on:timeupdate={handleTimeUpdate}
                src={audioSrc}
              >
                Your browser does not support the audio element.
              </audio>
            </section>
          {/if}

          <section>
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-xl font-semibold text-gray-200">Spreker Namen Toewijzen</h3>
              {#if uniqueSpeakers.length === 2}
                <button type="button" on:click={swapNames}
                  class="px-2 py-1 text-xs rounded bg-gray-700 hover:bg-gray-600 text-white"
                  title="Wissel namen tussen de twee sprekers">
                  ⇄ Wissel
                </button>
              {/if}
            </div>
            {#if uniqueSpeakers.length === 0 && !isLoading}
                <p class="text-gray-400">Geen sprekers geïdentificeerd in dit transcript.</p>
            {/if}
            <div class="space-y-4">
              {#each uniqueSpeakers as speakerId (speakerId)}
                <div class="flex flex-col sm:flex-row items-start sm:items-center space-y-2 sm:space-y-0 sm:space-x-3">
                  <label for={`speaker-name-${speakerId}`} class="w-full sm:w-32 font-mono text-sm text-gray-300 shrink-0 flex items-center gap-2">{speakerId}:
                    {#if roleForSpeaker(speakerId) === 'caller'}
                      {@html PhoneOutgoing()}<span class="text-xs text-blue-400">caller</span>
                    {:else if roleForSpeaker(speakerId) === 'callee'}
                      {@html PhoneIncoming()}<span class="text-xs text-blue-400">callee</span>
                    {:else if roleForSpeaker(speakerId) === 'caller?'}
                      {@html PhoneOutgoing()}<span class="text-xs text-blue-400">caller?</span>
                    {/if}
                  </label>
                  <input
                    id={`speaker-name-${speakerId}`}
                    type="text"
                    bind:value={editedMap[speakerId]}
                    placeholder={proposedMap[speakerId]?.name ? `Voorgesteld: ${proposedMap[speakerId].name}` : 'Naam invoeren...'}
                    class="flex-grow p-2 rounded bg-gray-800 text-gray-100 border focus:ring-2 outline-none w-full {isLikelyName(editedMap[speakerId]) ? 'border-gray-700 focus:ring-blue-500 focus:border-blue-500' : 'border-red-600 focus:ring-red-500 focus:border-red-500'}"
                  />
                  <button type="button" class="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-white" on:click={() => whyVisible[speakerId]=!whyVisible[speakerId]}>Waarom?</button>
                  {#if proposedMap[speakerId]?.reasoning_indices?.length}
                    <button
                      type="button"
                      on:click={() => toggleContext(speakerId)}
                      class="px-3 py-1.5 bg-gray-700 rounded text-sm hover:bg-gray-600 transition-colors text-gray-200 w-full sm:w-auto"
                    >
                      {#if contextVisible[speakerId]}Verberg{:else}Waarom?{/if}
                    </button>
                  {/if}
                </div>
                {#if whyVisible[speakerId]}
                  <pre class="mt-2 p-2 bg-gray-800 border border-gray-700 rounded text-gray-300 text-xs whitespace-pre-wrap">{whyFor(speakerId)}</pre>
                {/if}
                {#if contextVisible[speakerId]}
                  <pre
                    class="p-3 bg-gray-800 border border-gray-700 rounded text-gray-300 text-xs overflow-auto max-h-40 custom-scrollbar whitespace-pre-wrap"
                  >{getRelevantContext(speakerId)}</pre>
                {/if}
              {/each}
            </div>
          </section>

          <section>
            <div class="flex justify-between items-center mb-3">
              <h3 class="text-xl font-semibold text-gray-200">Transcript</h3>
              {#if transcript.length > 0}
              <button
                type="button"
                on:click={isEditingTranscript ? saveTranscriptEdits : toggleEditTranscript}
                disabled={isLoading && isEditingTranscript}
                class="px-4 py-1.5 text-sm rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                {#if isEditingTranscript}
                  {#if isLoading}Opslaan...{:else}Transcriptie Opslaan{/if}
                {:else}
                  Edit Transcriptie
                {/if}
              </button>
              {/if}
            </div>
            {#if transcript.length === 0 && !isLoading}
                <p class="text-gray-400">Geen transcript beschikbaar.</p>
            {/if}
            <div bind:this={transcriptContainer} class="bg-gray-800 p-4 rounded-lg max-h-96 overflow-y-auto text-gray-100 text-base border border-gray-700 custom-scrollbar">
              {#each transcript as segment, i (segment.id || i)}
                <div class="mb-4">
                  <strong class="text-blue-400">{editedMap[segment.speaker] || segment.speaker}:</strong>
                  {#if isEditingTranscript}
                    <textarea
                      rows="3"
                      class="w-full mt-1 bg-gray-700 text-gray-100 p-2 rounded border border-gray-600 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none"
                      bind:value={editedTranscript[i]}
                      aria-label={`Transcript segment ${i+1} by speaker ${editedMap[segment.speaker] || segment.speaker}`}
                    ></textarea>
                  {:else}
                    <p class="mt-1 whitespace-pre-wrap leading-relaxed">
                      {#if Array.isArray(segment.words) && segment.words.length}
                        {#each segment.words as word, j (`word-${i}-${j}`)}
                          <span
                            id={`word-${i}-${j}`}
                            role="button"
                            tabindex={word.start !== undefined ? 0 : -1}
                            class="word-span"
                            class:highlight={currentWordId === `word-${i}-${j}`}
                            class:clickable={word.start !== undefined}
                            on:click={() => handleWordClick(word)}
                            on:keydown={(event) => handleWordKeydown(event, word)}
                            aria-label={`Woord: ${word.word}, ${word.start !== undefined ? `start op ${word.start.toFixed(2)}s` : 'tijdstip onbekend'}`}
                          >{word.word}</span>{#if j < segment.words.length - 1}&nbsp;{/if}
                        {/each}
                      {:else}
                        {segment.text || '(Leeg segment)'}
                      {/if}
                    </p>
                  {/if}
                </div>
              {/each}
            </div>
          </section>
        </fieldset>
      {/if}
    </main>

    <footer class="flex justify-end items-center p-4 border-t border-gray-700 bg-gray-900 space-x-3">
      <button
        on:click={cancelReview}
        disabled={isSaving}
        class="px-5 py-2.5 bg-gray-700 rounded hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white"
      >
        Annuleren
      </button>
      <button
        on:click={saveAll}
        disabled={isLoading || isSaving || (uniqueSpeakers.length === 0 && transcript.length === 0)}
        class="px-5 py-2.5 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white"
      >
        {#if isSaving}Opslaan…{:else}Bevestigen &amp; Doorgaan{/if}
      </button>
    </footer>
  </div>
</div>

<style>
  .highlight {
    background-color: #2563eb; /* Tailwind's blue-600 */
    color: white;
    padding: 1px 3px;
    border-radius: 3px;
  }
  .custom-scrollbar::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #4b5563; /* Tailwind's gray-600 */
    border-radius: 4px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: #6b7280; /* Tailwind's gray-500 */
  }
  .word-span.clickable {
    cursor: pointer;
  }
  .word-span.clickable:hover,
  .word-span.clickable:focus {
    text-decoration: underline;
    outline: 1px dashed #60a5fa; /* Tailwind's blue-400, of een andere focus indicator */
    outline-offset: 1px;
  }
  .word-span:focus {
    outline: none; /* Verwijder default browser outline als we onze eigen focus style hebben */
  }
</style>
