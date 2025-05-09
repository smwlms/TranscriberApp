<script>
    import { onMount, onDestroy, createEventDispatcher } from 'svelte';
    import { getReviewData as apiGetReviewData, updateReviewData as apiUpdateReviewData } from '../api.js';
    
    export let jobId;
    export let audioRelativePath;
    
    const dispatch = createEventDispatcher();
    
    let isLoading = true;
    let error = '';
    let transcript = [];
    let proposedMap = {};
    let contextSnippets = {};
    let uniqueSpeakers = [];
    let editedMap = {};
    let contextVisible = {};
    
    let audioPlayer;
    let currentWordId = null;
    let previousWordElement = null;
    
    onMount(async () => {
      fetchReviewData();
    });
    
    onDestroy(() => {
      if (audioPlayer && !audioPlayer.paused) {
        audioPlayer.pause();
      }
      if (previousWordElement) {
        previousWordElement.classList.remove('highlight');
        previousWordElement = null;
        currentWordId = null;
      }
    });
    
    async function fetchReviewData() {
      isLoading = true;
      error = '';
      try {
        const data = await apiGetReviewData(jobId);
        transcript = data.intermediate_transcript || [];
        proposedMap = data.proposed_map || {};
        contextSnippets = data.context_snippets || {};
        const nonCriticalErrors = data.non_critical_errors || [];
    
        const ids = Array.from(
          new Set(transcript.map(s => s.speaker).filter(s => s && typeof s === 'string' && s.startsWith('SPEAKER_')))
        );
        uniqueSpeakers = ids;
    
        const initialEditedMap = {};
        const initialContextVisible = {};
        ids.forEach(id => {
          initialEditedMap[id] = proposedMap[id]?.name || '';
          initialContextVisible[id] = false;
        });
        editedMap = initialEditedMap;
        contextVisible = initialContextVisible;
      } catch (e) {
        error = `Fout bij laden review data: ${e.message}`;
        transcript = [];
        uniqueSpeakers = [];
        proposedMap = {};
        contextSnippets = {};
        editedMap = {};
        contextVisible = {};
      } finally {
        isLoading = false;
      }
    }
    
    function toggleContext(id) {
      contextVisible[id] = !contextVisible[id];
      contextVisible = contextVisible;
    }
    
    function getRelevantContext(id) {
      const indices = proposedMap[id]?.reasoning_indices || [];
      if (!indices.length) return 'Geen context beschikbaar.';
      const snippets = indices
        .map(i => {
          const snippet = contextSnippets[String(i)];
          if (snippet === undefined) {
            return `(Snippet ${i} content not found)`;
          }
          return snippet;
        })
        .join('\n–––\n');
      return snippets;
    }
    
    async function submit() {
      isLoading = true;
      error = '';
      try {
        const data = await apiUpdateReviewData(jobId, editedMap);
        dispatch('submit');
      } catch (e) {
        error = `Fout bij opslaan review data: ${e.message}`;
      } finally {
        isLoading = false;
      }
    }
    
    function cancel() {
      dispatch('cancel');
    }
    
    function handleTimeUpdate() {
      if (!audioPlayer || !transcript || transcript.length === 0) {
        return;
      }
    
      const currentTime = audioPlayer.currentTime;
      let foundWord = false;
    
      for (let i = 0; i < transcript.length; i++) {
        const segment = transcript[i];
        if (typeof segment !== 'object' || segment === null || !Array.isArray(segment.words)) {
          continue;
        }
        for (let j = 0; j < segment.words.length; j++) {
          const word = segment.words[j];
          if (
            typeof word !== 'object' ||
            word === null ||
            typeof word.start !== 'number' ||
            typeof word.end !== 'number'
          ) {
            continue;
          }
          if (currentTime >= word.start && currentTime < word.end) {
            const wordDomId = `word-${i}-${j}`;
            if (wordDomId !== currentWordId) {
              if (previousWordElement) {
                previousWordElement.classList.remove('highlight');
              }
              const currentWordElement = document.getElementById(wordDomId);
              if (currentWordElement) {
                currentWordElement.classList.add('highlight');
                currentWordElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
              }
              currentWordId = wordDomId;
              previousWordElement = currentWordElement;
            }
            foundWord = true;
            break;
          }
        }
        if (foundWord) {
          break;
        }
      }
    
      if (!foundWord && currentWordId !== null) {
        if (previousWordElement) {
          previousWordElement.classList.remove('highlight');
        }
        currentWordId = null;
        previousWordElement = null;
      }
    }
    </script>
    
    <div class="fixed inset-0 bg-gray-800 bg-opacity-60 flex items-center justify-center p-4 z-50">
      <div class="bg-gray-900 text-gray-100 rounded-lg w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <header class="flex justify-between items-center p-4 border-b border-gray-700">
          <h2 class="text-lg font-semibold">Speaker Review</h2>
          <button on:click={cancel} class="text-xl leading-none hover:text-gray-300 transition-colors">&times;</button>
        </header>
    
        <main class="p-4 overflow-auto flex-1 space-y-6">
          {#if isLoading}
            <p class="text-center text-gray-400">Laden review data…</p>
          {:else if error}
            <div class="bg-red-700 p-3 rounded text-red-100">
              <strong>Fout:</strong> {error}
            </div>
          {:else}
            {#if audioRelativePath}
              <audio
                bind:this={audioPlayer}
                on:timeupdate={handleTimeUpdate}
                controls
                class="w-full mb-4"
                preload="metadata"
                onerror={(e) => console.error('Audio error:', e.target.error)}
                src={`/${audioRelativePath}`}
              />
            {:else}
              <p class="text-red-400">Audio file path niet beschikbaar in job data.</p>
            {/if}
    
            <section>
              <h3 class="mb-3 text-gray-300">Spreker Namen Toewijzen</h3>
              {#if uniqueSpeakers.length === 0}
                <p class="text-gray-400 italic">Geen sprekers gevonden in de transcriptie om toe te wijzen.</p>
              {/if}
              {#each uniqueSpeakers as id}
                <div class="flex flex-col sm:flex-row items-start sm:items-center space-y-2 sm:space-y-0 sm:space-x-2 mb-3">
                  <label for={"speaker-" + id} class="w-32 font-mono text-sm font-medium text-gray-200 flex-shrink-0">
                    {id}:
                  </label>
                  <input
                    id={"speaker-" + id}
                    type="text"
                    bind:value={editedMap[id]}
                    placeholder={proposedMap[id]?.name || 'Naam invoeren...'}
                    class="flex-1 p-1.5 rounded bg-gray-800 text-gray-100 focus:outline-none focus:ring focus:ring-blue-500 border border-gray-700"
                    aria-label={"Naam toewijzen aan " + id}
                  />
                  {#if proposedMap[id]?.reasoning_indices?.length}
                    <button
                      on:click={() => toggleContext(id)}
                      class="px-3 py-1 bg-gray-700 rounded text-gray-200 text-sm hover:bg-gray-600 transition-colors focus:outline-none focus:ring"
                    >
                      Waarom?
                    </button>
                  {/if}
                </div>
                {#if contextVisible[id]}
                  <pre class="p-3 bg-gray-800 rounded text-sm text-gray-300 overflow-auto max-h-40 border border-gray-700 mt-1 mb-3">
    {getRelevantContext(id)}
                  </pre>
                {/if}
              {/each}
            </section>
    
            <section>
              <h3 class="mb-3 text-gray-300">Transcript</h3>
              <div class="bg-gray-800 p-4 rounded-lg h-72 overflow-y-auto text-gray-100 text-base border border-gray-700">
                {#if transcript.length === 0}
                  <p class="text-gray-400 italic text-center">Transcript data is leeg of ontbreekt.</p>
                {/if}
                {#each transcript as seg, i}
                  <p class="mb-2 leading-relaxed">
                    <strong class="text-blue-400">{editedMap[seg.speaker] || seg.speaker}:</strong>
                    {#each seg.words || [] as w, j}
                      {#if w && typeof w === 'object' && typeof w.word === 'string' && typeof w.start === 'number' && typeof w.end === 'number'}
                        <span id={`word-${i}-${j}`}>{w.word} </span>
                      {:else}
                        <span class="text-red-400">(Ongeldig woord data) </span>
                      {/if}
                    {/each}
                    {#if !Array.isArray(seg.words)}
                      <span class="text-yellow-400 italic">(Woorden data ontbreekt voor dit segment)</span>
                    {/if}
                  </p>
                {/each}
              </div>
            </section>
          {/if}
        </main>
    
        <footer class="p-4 border-t border-gray-700 bg-gray-900 text-right space-x-3 flex-shrink-0">
          <button
            on:click={cancel}
            disabled={isLoading}
            class="px-4 py-2 bg-gray-700 text-gray-200 rounded hover:bg-gray-600 transition-colors focus:outline-none focus:ring disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Annuleren
          </button>
          <button
            on:click={submit}
            disabled={isLoading || uniqueSpeakers.length === 0 || transcript.length === 0}
            class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors focus:outline-none focus:ring disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Bevestigen & Doorgaan
          </button>
        </footer>
      </div>
    </div>
    
    <style>
        
    /* css-unused-selector */ /*
    .highlight {
      background-color: #3b82f6;
      color: white;
      padding: 1px 2px;
      border-radius: 3px;
      transition: background-color 0.2s ease;
    }
    
    div.overflow-y-auto::-webkit-scrollbar {
      width: 8px;
    }
    div.overflow-y-auto::-webkit-scrollbar-track {
      background: #4b5563;
      border-radius: 10px;
    }
    div.overflow-y-auto::-webkit-scrollbar-thumb {
      background: #6b7280;
      border-radius: 10px;
    }
    div.overflow-y-auto::-webkit-scrollbar-thumb:hover {
      background: #9ca3af;
    }
    div.overflow-y-auto {
      scrollbar-width: thin;
      scrollbar-color: #6b7280 #4b5563;
    }
    </style>
    