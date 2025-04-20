<script>
    import { onMount, onDestroy, createEventDispatcher } from 'svelte';
    import { apiBaseUrl } from '../stores.js';
  
    export let jobId;
    let baseUrl = '';
    const unsub = apiBaseUrl.subscribe(v => (baseUrl = v));
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
  
    onMount(fetchReviewData);
    onDestroy(() => {
      unsub();
      if (audioPlayer && !audioPlayer.paused) audioPlayer.pause();
    });
  
    async function fetchReviewData() {
      isLoading = true;
      error = '';
      try {
        const res = await fetch(`${baseUrl}/get_review_data/${jobId}`);
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          throw new Error(d.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        transcript = data.intermediate_transcript;
        proposedMap = data.proposed_map || {};
        contextSnippets = data.context_snippets || {};
        const ids = Array.from(
          new Set(transcript.map(s => s.speaker).filter(s => s?.startsWith('SPEAKER_')))
        );
        uniqueSpeakers = ids;
        ids.forEach(id => {
          editedMap[id] = proposedMap[id]?.name || '';
          contextVisible[id] = false;
        });
      } catch (e) {
        error = e.message;
      } finally {
        isLoading = false;
      }
    }
  
    function toggleContext(id) {
      contextVisible[id] = !contextVisible[id];
    }
  
    function getRelevantContext(id) {
      const idx = proposedMap[id]?.reasoning_indices || [];
      if (!idx.length) return 'Geen context beschikbaar.';
      return idx
        .map(i => contextSnippets[String(i)] || `(snippet ${i} niet gevonden)`)
        .join('\n–––\n');
    }
  
    async function submit() {
      try {
        const res = await fetch(`${baseUrl}/update_review_data/${jobId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ final_speaker_map: editedMap })
        });
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          throw new Error(d.error || d.message || `HTTP ${res.status}`);
        }
        dispatch('submit');
      } catch (e) {
        error = e.message;
      }
    }
  
    function cancel() {
      dispatch('cancel');
    }
  
    function handleTimeUpdate() {
      if (!audioPlayer || !transcript.length) return;
      const t = audioPlayer.currentTime;
      let found = false;
      transcript.forEach((seg, i) => {
        if (found) return;
        (seg.words || []).forEach((w, j) => {
          if (t >= w.start && t < w.end) {
            const id = `word-${i}-${j}`;
            if (id !== currentWordId) {
              document.getElementById(currentWordId)?.classList.remove('highlight');
              document.getElementById(id)?.classList.add('highlight');
              currentWordId = id;
            }
            found = true;
          }
        });
      });
      if (!found && currentWordId) {
        document.getElementById(currentWordId)?.classList.remove('highlight');
        currentWordId = null;
      }
    }
  </script>
  
  <div class="fixed inset-0 bg-gray-800 bg-opacity-60 flex items-center justify-center p-4 z-50">
    <div class="bg-gray-900 text-gray-100 rounded-lg w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
      <header class="flex justify-between items-center p-4 border-b border-gray-700">
        <h2 class="text-lg">Speaker Review</h2>
        <button on:click={cancel} class="text-xl">&times;</button>
      </header>
  
      <main class="p-4 overflow-auto flex-1 space-y-4">
        {#if isLoading}
          <p>Laden…</p>
        {:else if error}
          <div class="bg-red-600 p-2 rounded">{error}</div>
        {:else}
          <audio
            bind:this={audioPlayer}
            on:timeupdate={handleTimeUpdate}
            controls
            class="w-full mb-4"
            src={`/${jobId}.mp3`}
          />
  
          <section>
            <h3 class="font-semibold mb-2">Assign Names</h3>
            {#each uniqueSpeakers as id}
              <div class="flex items-center space-x-2 mb-2">
                <!-- A11y‑fix: label → for/input id koppeling -->
                <label
                  for={"speaker-" + id}
                  class="w-24 font-mono text-sm font-medium text-gray-200"
                >
                  {id}:
                </label>
                <input
                  id={"speaker-" + id}
                  type="text"
                  bind:value={editedMap[id]}
                  placeholder={proposedMap[id]?.name || ''}
                  class="flex-1 p-1 rounded bg-gray-800 text-gray-100 focus:outline-none focus:ring"
                  aria-label="Naam toewijzen aan {id}"
                />
                {#if proposedMap[id]?.reasoning_indices?.length}
                  <button on:click={() => toggleContext(id)}>Why?</button>
                {/if}
              </div>
              {#if contextVisible[id]}
                <pre class="p-2 bg-gray-700 rounded text-sm overflow-auto">
  {getRelevantContext(id)}
                </pre>
              {/if}
            {/each}
          </section>
  
          <section>
            <h3 class="font-semibold mb-2">Transcript</h3>
            <div class="h-48 overflow-auto p-2 bg-gray-800 rounded">
              {#each transcript as seg, i}
                <p>
                  <strong>{editedMap[seg.speaker] || seg.speaker}:</strong>
                  {#each seg.words || [] as w, j}
                    <span id={`word-${i}-${j}`}>{w.word} </span>
                  {/each}
                </p>
              {/each}
            </div>
          </section>
        {/if}
      </main>
  
      <footer class="p-4 border-t border-gray-700 text-right space-x-2">
        <button on:click={cancel} class="px-3 py-1 bg-gray-600 rounded">Cancel</button>
        <button on:click={submit} class="px-3 py-1 bg-blue-600 rounded text-white">Confirm</button>
      </footer>
    </div>
  </div>
  
  <!-- svelte-ignore css-unused-selector -->
  <style>
    .highlight {
      background-color: red;
      color: white;
      padding: 1px 2px;
      border-radius: 3px;
    }
  </style>
  