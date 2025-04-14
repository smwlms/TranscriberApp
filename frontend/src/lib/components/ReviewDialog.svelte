<script>
    import { onMount, createEventDispatcher, onDestroy } from 'svelte';
    // Import stores needed for API call
    import { apiBaseUrl } from '../stores.js';
  
    // Prop: The ID of the job being reviewed, passed from JobRunner
    export let jobId;
  
    let baseUrl = '';
    // Subscribe to get the API base URL
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => baseUrl = value);
  
    // --- Component State ---
    let transcript = null;      // To store the intermediate transcript segments array
    let proposedMap = {};       // To store the map suggested by the name detector (if any)
    let contextSnippets = {};   // To store context snippets (optional display)
    let uniqueSpeakers = [];    // Array of unique speaker IDs found (e.g., ['SPEAKER_00', 'SPEAKER_01'])
    let editedMap = {};         // Dictionary bound to input fields, holds final user names (SPEAKER_ID -> name)
    let isLoading = true;       // Flag for loading state
    let isSubmitting = false;   // Flag for submission state
    let error = null;           // To display errors during fetch or submit
  
    // Used to dispatch events ('submit', 'cancel') back to the parent component
    const dispatch = createEventDispatcher();
  
    // --- Lifecycle: Fetch data when component mounts ---
    onMount(async () => {
      if (!jobId) {
        error = "Error: No Job ID was provided to the ReviewDialog component.";
        isLoading = false;
        return;
      }
      log(`ReviewDialog mounted for job ${jobId}. Fetching review data...`);
      await fetchReviewData();
    });
  
    // --- Data Fetching ---
    async function fetchReviewData() {
      isLoading = true;
      error = null;
      try {
        const response = await fetch(`${baseUrl}/get_review_data/${jobId}`);
        if (!response.ok) {
          const errData = await response.json().catch(() => ({})); // Try to get error details
          throw new Error(errData.error || `Could not fetch review data (HTTP ${response.status})`);
        }
        const data = await response.json();
  
        // Validate essential data presence
        if (!data.intermediate_transcript || !Array.isArray(data.intermediate_transcript)) {
            throw new Error("Intermediate transcript data is missing or invalid in server response.");
        }
  
        // Store fetched data locally
        transcript = data.intermediate_transcript;
        proposedMap = data.proposed_map || {};       // Default to empty obj if missing
        contextSnippets = data.context_snippets || {}; // Default to empty obj if missing
  
        // --- Process Transcript to Find Unique Speaker IDs ---
        const speakerSet = new Set();
        transcript.forEach(segment => {
          if (segment && segment.speaker && typeof segment.speaker === 'string' && segment.speaker.startsWith('SPEAKER_')) {
            speakerSet.add(segment.speaker);
          }
        });
        uniqueSpeakers = Array.from(speakerSet).sort(); // Create a sorted array
  
        // --- Initialize the Editable Map ---
        editedMap = {};
        uniqueSpeakers.forEach(speakerId => {
          editedMap[speakerId] = (proposedMap[speakerId] || '').trim(); // Use proposed name or empty
        });
  
        log('Review data loaded. Unique speakers:', uniqueSpeakers);
        log('Initialized map for editing:', editedMap);
  
      } catch (err) {
        console.error("Failed to fetch or process review data:", err);
        error = `Failed to load review data: ${err.message}`;
        uniqueSpeakers = []; editedMap = {}; transcript = null;
      } finally {
        isLoading = false;
      }
    }
  
    // --- Action Handlers ---
  
    // Handles the submission of the reviewed names
    async function submitReview() {
      if (!jobId) { error = "Cannot submit review: Job ID is missing."; return; }
      log("Submitting reviewed speaker map:", editedMap);
      isSubmitting = true; error = null;
  
      try {
          const response = await fetch(`${baseUrl}/update_review_data/${jobId}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ final_speaker_map: editedMap }),
          });
          const data = await response.json().catch(() => ({ message: "Failed to parse response" }));
          if (!response.ok) { throw new Error(data.error || data.message || `Submission failed (HTTP ${response.status})`); }
  
          log("Review submitted successfully.");
          dispatch('submit'); // Signal parent component
  
      } catch (err) {
          console.error("Failed to submit review:", err);
          error = `Failed to submit review: ${err.message}`;
      } finally {
          isSubmitting = false;
      }
    }
  
    // Handles closing the dialog without submitting
    function cancelReview() {
       log("Review cancelled.");
       dispatch('cancel'); // Signal parent component
    }
  
    // --- Utility ---
    function log(...args) { console.log('[ReviewDialog]', ...args); }
  
    // Cleanup store subscription
    onDestroy(() => { unsubscribeApiBase(); });
  
  </script>
  
  <div
    class="fixed inset-0 bg-gray-800 bg-opacity-60 backdrop-blur-sm flex items-center justify-center p-4 z-50"
    role="dialog"
    aria-modal="true"
    aria-labelledby="review-dialog-title">
  
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden border border-gray-300 dark:border-gray-700 transition-colors duration-150">
  
      <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0 flex justify-between items-center">
        <h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100" id="review-dialog-title">Review Speaker Names</h2>
        <button on:click={cancelReview} aria-label="Close" class="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 text-2xl leading-none">&times;</button>
      </div>
  
      <div class="px-6 py-4 flex-grow overflow-y-auto">
        {#if isLoading}
          <p class="text-center text-gray-600 dark:text-gray-400 py-10">Loading review data...</p>
        {:else if error}
          <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300" role="alert">
            <strong class="font-bold">Error!</strong>
            <span class="block sm:inline"> {error}</span>
          </div>
           <div class="mt-4 text-right"> <button on:click={cancelReview} class="px-4 py-2 bg-gray-300 dark:bg-gray-600 dark:text-gray-200 rounded hover:bg-gray-400 dark:hover:bg-gray-500">Close</button> </div>
        {:else if uniqueSpeakers.length === 0}
           <p class="text-gray-600 dark:text-gray-400 italic py-6 text-center">No distinct speaker IDs found. Confirm to proceed.</p>
        {:else}
          <p class="text-sm text-gray-600 dark:text-gray-300 mb-4"> Review context and assign names. Leave blank to keep original ID. </p>
          <div class="space-y-3 mb-6 border dark:border-gray-600 rounded p-4">
            <h3 class="text-md font-semibold mb-3 text-gray-700 dark:text-gray-200">Assign Names:</h3>
            {#each uniqueSpeakers as speakerId (speakerId)}
              <div class="flex flex-col sm:flex-row sm:items-center sm:gap-3">
                <label for="speaker-{speakerId}" class="w-full sm:w-28 font-mono text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 sm:mb-0 shrink-0">{speakerId}:</label>
                <input
                  type="text"
                  id="speaker-{speakerId}"
                  bind:value={editedMap[speakerId]}
                  placeholder="Enter Name (optional)"
                  class="flex-grow block w-full border border-gray-300 dark:border-gray-600 rounded-md shadow-sm py-1.5 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm
                         bg-white dark:bg-gray-700
                         text-gray-900 dark:text-gray-100  
                         placeholder-gray-500 dark:placeholder-gray-400 
                         disabled:bg-gray-100 dark:disabled:bg-gray-600
                         transition-colors duration-150"
                  disabled={isSubmitting}
                />
              </div>
            {/each}
          </div>
          <div class="mt-4">
            <h3 class="text-md font-semibold mb-2 text-gray-600 dark:text-gray-300">Transcript Context:</h3>
            <div class="max-h-64 overflow-y-auto bg-gray-50 dark:bg-gray-900/50 p-3 rounded border border-gray-200 dark:border-gray-700 text-xs font-mono">
              {#if transcript && transcript.length > 0}
                 {#each transcript as segment, i (i)}
                   <div class="mb-1 border-b border-gray-100 dark:border-gray-800/50 pb-1 last:border-b-0">
                     <span class="text-gray-500 dark:text-gray-400 mr-2">[{i}]</span>
                     <span class="font-bold {segment.speaker && segment.speaker.startsWith('SPEAKER_') ? 'text-blue-700 dark:text-blue-400' : 'text-gray-500 dark:text-gray-400'}"> {segment.speaker || 'NO_SPEAKER'}: </span>
                     <span class="text-gray-800 dark:text-gray-200"> {segment.text || ''}</span>
                   </div>
                 {/each}
              {:else} <p class="text-gray-500 dark:text-gray-400 italic">No transcript data.</p> {/if}
            </div>
          </div>
        {/if} </div> <div class="px-6 py-3 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 text-right rounded-b-lg shrink-0">
         {#if !isLoading && !error}
              <button on:click={cancelReview} disabled={isSubmitting} class="mr-2 px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400 dark:bg-gray-600 dark:text-gray-200 dark:hover:bg-gray-500 disabled:opacity-50"> Cancel </button>
              <button on:click={submitReview} disabled={isSubmitting} class="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-wait"> {#if isSubmitting} Submitting... {:else if uniqueSpeakers.length === 0} Confirm (No Speakers Found) {:else} Confirm Names {/if} </button>
         {:else if !isLoading && error}
             <button on:click={cancelReview} class="px-4 py-2 bg-gray-300 dark:bg-gray-600 dark:text-gray-200 rounded hover:bg-gray-400 dark:hover:bg-gray-500"> Close </button>
         {/if}
      </div>
  
    </div> </div>