<script>
    import { onMount, createEventDispatcher, onDestroy } from 'svelte';
    import { apiBaseUrl } from '../stores.js';

    export let jobId;
    export let audioPath = null;

    let baseUrl = '';
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => baseUrl = value);

    let currentAudioPath = null;
    $: {
        if (audioPath) {
            currentAudioPath = `/${audioPath}`; // Corrected path construction
            log('Audio path for player set:', currentAudioPath);
        } else {
            currentAudioPath = null;
            log('Audio path prop is null or empty, audio player will not load.');
        }
    }

    // --- Component State ---
    let transcript = null;
    let proposedMap = {}; // Now expects {SPEAKER_ID: {name:..., reasoning_indices:[...]}}
    let contextSnippets = {}; // Expects {index: "snippet text..."}
    let uniqueSpeakers = [];
    let editedMap = {}; // Still holds {SPEAKER_ID: "Final Name"} for editing
    let isLoading = true;
    let isSubmitting = false;
    let error = null;
    let contextVisible = {}; // Tracks visibility per speaker

    // --- DOM Element References ---
    let audioPlayer;
    let transcriptContainer;

    // --- Highlighting State ---
    let currentWordId = null;

    // --- Event Dispatcher ---
    const dispatch = createEventDispatcher();

    // --- Lifecycle Hooks ---
    onMount(async () => {
        if (!jobId) { error = "Error: No Job ID."; isLoading = false; return; }
        log(`ReviewDialog mounted for job ${jobId}.`);
        await fetchReviewData();
    });

    onDestroy(() => {
        unsubscribeApiBase();
        if (audioPlayer && !audioPlayer.paused) { try { audioPlayer.pause(); } catch(e) { /* ignore */ } }
        log("ReviewDialog destroyed.");
    });

    // --- Data Fetching ---
    async function fetchReviewData() {
      isLoading = true; error = null;
      transcript = null; uniqueSpeakers = []; editedMap = {}; proposedMap = {}; contextSnippets = {}; contextVisible = {};
      try {
        log("Fetching review data from:", `${baseUrl}/get_review_data/${jobId}`);
        const response = await fetch(`${baseUrl}/get_review_data/${jobId}`);
        if (!response.ok) { const d=await response.json().catch(()=>({})); throw new Error(d.error || `HTTP ${response.status}`); }
        const data = await response.json();
        if (!data.intermediate_transcript) { throw new Error("Transcript data missing."); }

        // Store data
        transcript = data.intermediate_transcript;
        proposedMap = data.proposed_map || {}; // Expects new structure
        contextSnippets = data.context_snippets || {};

        // Log received data for debugging karaoke
        log('Received transcript data sample (first segment):', JSON.stringify(transcript?.[0]));
        const firstSegmentWithWords = transcript?.find(seg => seg.words && seg.words.length > 0);
        if (firstSegmentWithWords) {
            log('First segment WITH WORDS sample:', JSON.stringify(firstSegmentWithWords.words?.slice(0, 5)));
            log('Data type of word.start:', typeof firstSegmentWithWords.words[0]?.start);
            log('Data type of word.end:', typeof firstSegmentWithWords.words[0]?.end);
        } else {
            log('COULD NOT FIND segment with words array in received data.');
        }

        const speakerSet = new Set();
        transcript.forEach(seg => { if (seg?.speaker?.startsWith('SPEAKER_')) { speakerSet.add(seg.speaker); }});
        uniqueSpeakers = Array.from(speakerSet).sort();

        // Initialize editedMap (with name only) and contextVisible
        editedMap = {};
        contextVisible = {};
        uniqueSpeakers.forEach(id => {
             editedMap[id] = (proposedMap[id]?.name || '').trim(); // Extract name
             contextVisible[id] = false;
        });

        log(`Review data loaded. Speakers: ${uniqueSpeakers.length}, Proposed Map Keys: ${Object.keys(proposedMap).length}, Context Snippets: ${Object.keys(contextSnippets).length}`);

      } catch (err) { console.error("Fetch review fail:", err); error = `${err.message}`; uniqueSpeakers = []; editedMap = {}; transcript = null; proposedMap = {}; contextSnippets = {}; contextVisible = {}; }
      finally { isLoading = false; log("Finished fetchReviewData attempt. isLoading:", isLoading); }
    }

    // --- Action Handlers ---
    async function submitReview() {
      if (!jobId) { error = "No Job ID."; return; }
      log("Submitting map:", editedMap);
      isSubmitting = true; error = null;
      try {
          const response = await fetch(`${baseUrl}/update_review_data/${jobId}`, {
              method: 'POST', headers: { 'Content-Type': 'application/json', },
              body: JSON.stringify({ final_speaker_map: editedMap }),
          });
          const data = await response.json().catch(() => ({ message: "No response body" }));
          if (!response.ok) { throw new Error(data.error || data.message || `HTTP ${response.status}`); }
          log("Review submit success."); dispatch('submit');
      } catch (err) { console.error("Submit review fail:", err); error = `Submit failed: ${err.message}`; }
      finally { isSubmitting = false; }
    }

    function cancelReview() { log("Review cancelled."); dispatch('cancel'); }

    // --- Context Visibility Toggle ---
    function toggleContext(speakerId) {
        contextVisible[speakerId] = !contextVisible[speakerId];
        log(`Toggled context visibility for ${speakerId} to ${contextVisible[speakerId]}`);
    }

    // --- Get Relevant Context Snippets ---
    function getRelevantContext(speakerId) {
        const proposal = proposedMap[speakerId];
        const indices = proposal?.reasoning_indices;
        if (!proposal || !indices || !Array.isArray(indices) || indices.length === 0 || !contextSnippets || Object.keys(contextSnippets).length === 0) {
             return "No specific context linked by LLM for this speaker.";
        }
        let relevantText = indices.map(index => {
                 const snippet = contextSnippets[String(index)]; // Ensure index is string for lookup
                 return snippet ? `Context around Line Index ${index}:\n-----------------------------\n${snippet}\n-----------------------------` : `(Context snippet for index ${index} not found)`;
             }).join('\n\n---\n\n');
        return relevantText || "Could not retrieve context snippets based on indices.";
    }

    function log(...args) { console.log('[ReviewDialog]', ...args); }

    // --- Audio Highlighting Logic ---
    function handleTimeUpdate() {
        // ... (Includes the KaraokeDebug logs added previously) ...
        if (!audioPlayer || !transcript || !transcript.length) return;
        const currentTime = audioPlayer.currentTime;
        let activeWordFoundThisTick = false;
        let activeWordElement = null;
        let newHighlightApplied = false;

        // console.log(`[KaraokeDebug] Time: ${currentTime.toFixed(3)}`);

        for (let i = 0; i < transcript.length; i++) {
          const seg = transcript[i];
          if (seg.words && Array.isArray(seg.words) && seg.words.length > 0) {
            for (let j = 0; j < seg.words.length; j++) {
              const word = seg.words[j];
              const wordId = `word-${i}-${j}`;
              const isValidWordTime = typeof word.start === 'number' && typeof word.end === 'number';

              if (isValidWordTime && currentTime >= word.start && currentTime < word.end) {
                activeWordFoundThisTick = true;
                if (wordId !== currentWordId) {
                  console.log(`[KaraokeDebug] MATCH & NEW WORD: Highlighting ${wordId} (${word.word}) at Time ${currentTime.toFixed(3)} [Word Time: ${word.start.toFixed(3)}-${word.end.toFixed(3)}]`);
                  const previousElement = currentWordId ? document.getElementById(currentWordId) : null;
                  if (previousElement) { try { previousElement.classList.remove('highlight'); } catch(e) { /* ignore */ } }
                  const currentElement = document.getElementById(wordId);
                  if (currentElement) { try { currentElement.classList.add('highlight'); newHighlightApplied = true; } catch(e) { /* ignore */ } }
                  else { console.warn(`[KaraokeDebug] Could not find element ${wordId} to highlight.`); }
                  currentWordId = wordId; activeWordElement = currentElement;
                }
                break;
              }
            }
          }
          if (activeWordFoundThisTick) break;
        }

        if (!activeWordFoundThisTick && currentWordId) {
          console.log(`[KaraokeDebug] NO MATCH found this tick. Removing highlight from ${currentWordId}`);
          const previousElement = document.getElementById(currentWordId);
           if (previousElement) { try { previousElement.classList.remove('highlight'); } catch(e) { /* ignore */ } }
          currentWordId = null;
        }

        if(activeWordElement && transcriptContainer && newHighlightApplied) {
          try {
              const containerRect = transcriptContainer.getBoundingClientRect();
              const wordRect = activeWordElement.getBoundingClientRect();
              if (wordRect.bottom > containerRect.bottom - 5 || wordRect.top < containerRect.top + 5) {
                  activeWordElement.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
              }
          } catch (scrollError) { console.error("Error during scrollIntoView:", scrollError); }
        }
    }
</script>

<div class="fixed inset-0 bg-gray-800 bg-opacity-60 backdrop-blur-sm flex items-center justify-center p-4 z-50" role="dialog" aria-modal="true" aria-labelledby="review-dialog-title">
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden border border-gray-300 dark:border-gray-700">

      <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0 flex justify-between items-center">
          <h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100" id="review-dialog-title">Review Speaker Names</h2>
          <button on:click={cancelReview} aria-label="Close" class="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 text-2xl leading-none">&times;</button>
      </div>

      <div class="px-6 py-4 flex-grow overflow-y-auto space-y-6">
        {#if isLoading}
            <p class="text-center text-gray-600 dark:text-gray-400 py-10">Loading review data...</p>
        {:else if error}
            <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300" role="alert">
                <strong class="font-bold">Error!</strong> <span class="block sm:inline"> {error}</span>
            </div>
            <div class="mt-4 text-right"><button on:click={cancelReview} class="px-4 py-2 bg-gray-300 dark:bg-gray-600 dark:text-gray-200 rounded hover:bg-gray-400 dark:hover:bg-gray-500">Close</button> </div>
        {:else}
            {#if currentAudioPath}
                <div class="sticky top-0 bg-white dark:bg-gray-800 py-2 z-10 border-b dark:border-gray-700 -mx-6 px-6">
                    <audio controls bind:this={audioPlayer} on:timeupdate={handleTimeUpdate} on:error={(e) => { console.error('Audio Player Error:', e.target.error); error = `Audio player error: ${e.target.error?.message || 'Could not load source.'}`}} class="w-full" src={currentAudioPath}>
                        Your browser does not support the audio element.
                    </audio>
                </div>
            {:else}
                <p class="text-sm text-center text-yellow-700 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/30 p-2 rounded">Audio player cannot be loaded (audio path missing).</p>
            {/if}

            {#if uniqueSpeakers.length === 0}
                <p class="text-gray-600 dark:text-gray-400 italic py-6 text-center">No distinct speaker IDs (SPEAKER_XX) found.</p>
            {:else}
                <p class="text-sm text-gray-600 dark:text-gray-300">Assign names below. Leave blank to keep original ID ({uniqueSpeakers.join(', ')}).</p>
                <div class="space-y-1 border dark:border-gray-600 rounded p-4">
                    <h3 class="text-md font-semibold text-gray-700 dark:text-gray-200 mb-3">Assign Names:</h3>
                    {#each uniqueSpeakers as speakerId (speakerId)}
                        <div class="flex flex-col sm:flex-row sm:items-center sm:gap-3 mb-1">
                             <label for="speaker-{speakerId}" class="w-full sm:w-28 font-mono text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 sm:mb-0 shrink-0">{speakerId}:</label>
                             <input type="text" id="speaker-{speakerId}" bind:value={editedMap[speakerId]} placeholder={proposedMap[speakerId]?.name ? '(Suggested: ' + proposedMap[speakerId].name + ')' : 'Enter Name (optional)'} class="flex-grow block w-full border border-gray-300 dark:border-gray-600 rounded-md shadow-sm py-1.5 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 disabled:bg-gray-100 dark:disabled:bg-gray-600" disabled={isSubmitting}/>
                            {#if proposedMap[speakerId]?.reasoning_indices?.length > 0}
                                <button type="button" on:click={() => toggleContext(speakerId)} class="ml-0 sm:ml-2 mt-1 sm:mt-0 px-2 py-1 text-xs bg-gray-200 dark:bg-gray-600 rounded hover:bg-gray-300 dark:hover:bg-gray-500 shrink-0" title="Show LLM context for '{proposedMap[speakerId]?.name || speakerId}' suggestion"> {contextVisible[speakerId] ? 'Hide' : 'Why?'} </button>
                            {/if}
                        </div>
                        {#if contextVisible[speakerId]}
                             <div class="ml-0 sm:ml-32 mb-3 p-2 text-xs bg-gray-100 dark:bg-gray-700 border dark:border-gray-600 rounded transition-all duration-200 ease-in-out">
                                 <p class="font-semibold mb-1 text-gray-800 dark:text-gray-200">LLM Context for "{proposedMap[speakerId]?.name || speakerId}":</p>
                                 <pre class="whitespace-pre-wrap font-mono text-gray-700 dark:text-gray-300">{getRelevantContext(speakerId)}</pre>
                             </div>
                        {/if}
                    {/each}
                </div>
            {/if}

            <div class="mt-4">
                <h3 class="text-md font-semibold mb-2 text-gray-600 dark:text-gray-300">Transcript Context:</h3>
                <div bind:this={transcriptContainer} class="max-h-80 overflow-y-auto bg-gray-50 dark:bg-gray-900/50 p-3 rounded border border-gray-200 dark:border-gray-700 text-base leading-relaxed">
                    {#if transcript && transcript.length > 0}
                        {#each transcript as segment, i (segment.start)}
                            <div class="mb-2">
                                <strong class="font-bold {segment.speaker && segment.speaker.startsWith('SPEAKER_') ? 'text-blue-700 dark:text-blue-400' : 'text-gray-500 dark:text-gray-400'}"> {editedMap[segment.speaker] || segment.speaker || 'NO_SPEAKER'}: </strong>
                                {#if segment.words && Array.isArray(segment.words) && segment.words.length > 0}
                                    {#each segment.words as word, j (word.start + '-' + j)}
                                        <span id="word-{i}-{j}" data-start={word.start} data-end={word.end} class="transition-colors duration-75">{word.word}</span>{' '}
                                    {/each}
                                {:else}
                                    <span class="text-gray-800 dark:text-gray-200">{segment.text || ''}</span>{#if !segment.text}(No text){/if}
                                {/if}
                            </div>
                        {/each}
                    {:else}
                        <p class="text-gray-500 dark:text-gray-400 italic">No transcript data available.</p>
                    {/if}
                </div>
            </div>
        {/if}
      </div> <div class="px-6 py-3 bg-gray-100 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 text-right rounded-b-lg shrink-0">
          {#if !isLoading && !error}
            <button on:click={cancelReview} disabled={isSubmitting} class="mr-2 px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400 dark:bg-gray-600 dark:text-gray-200 dark:hover:bg-gray-500 disabled:opacity-50">Cancel</button>
            <button on:click={submitReview} disabled={isSubmitting} class="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-wait">{#if isSubmitting} Submitting... {:else if uniqueSpeakers.length === 0} Confirm (No Speakers Found) {:else} Confirm Names {/if}</button>
          {:else if !isLoading && error}
             <button on:click={cancelReview} class="px-4 py-2 bg-gray-300 dark:bg-gray-600 dark:text-gray-200 rounded hover:bg-gray-400 dark:hover:bg-gray-500">Close</button>
          {/if}
      </div>

    </div> </div> <style lang="postcss">
    /* *** MODIFICATION: Comment out Tailwind @apply and use simple CSS for debugging *** */
    /* .highlight {
        @apply bg-yellow-200 dark:bg-yellow-600/70 rounded px-0.5;
    } */
    .highlight {
        background-color: red; /* Use a very obvious style - REMOVED !important */
        color: white;          /* Ensure text is visible */
        padding: 1px 2px;      /* Optional: add some padding */
        border-radius: 3px;    /* Optional: round corners */
    }
    /* Style for the context display */
    pre {
        max-height: 150px;
        overflow-y: auto;
        background-color: rgba(255, 255, 255, 0.1);
        padding: 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
    }
</style>