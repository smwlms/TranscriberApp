<script>
  import { onMount, createEventDispatcher, onDestroy } from 'svelte';
  // Import stores needed for API call and potentially job data (though jobId passed as prop)
  import { apiBaseUrl } from '../stores.js';

  // Prop: The ID of the job being reviewed, passed from JobRunner
  export let jobId;

  let baseUrl = '';
  // Subscribe to get the API base URL
  const unsubscribeApiBase = apiBaseUrl.subscribe(value => baseUrl = value);

  // --- Component State ---
  let transcript = null;      // Holds the intermediate transcript segments array
  let proposedMap = {};       // Holds the map suggested by the name detector (if any)
  let contextSnippets = {};   // Holds context snippets (optional display for user)
  let uniqueSpeakers = [];    // Array of unique speaker IDs found (e.g., ['SPEAKER_00', 'SPEAKER_01'])
  let editedMap = {};         // Dictionary bound to input fields, holds final user names (SPEAKER_ID -> name)
  let isLoading = true;       // True while fetching data
  let isSubmitting = false;   // True while submitting the review to backend
  let error = null;           // Holds error messages for display

  // Used to dispatch events ('submit', 'cancel') back to the parent (JobRunner)
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
        // Only add IDs that follow the expected pattern
        if (segment && segment.speaker && typeof segment.speaker === 'string' && segment.speaker.startsWith('SPEAKER_')) {
          speakerSet.add(segment.speaker);
        }
      });
      // Create a sorted array for a consistent UI order
      uniqueSpeakers = Array.from(speakerSet).sort();

      // --- Initialize the Editable Map ---
      // Pre-fill the map with proposed names from the backend, or empty strings
      editedMap = {};
      uniqueSpeakers.forEach(speakerId => {
        // Use proposed name if available, trim it, otherwise default to empty string
        editedMap[speakerId] = (proposedMap[speakerId] || '').trim();
      });

      log('Review data loaded successfully. Unique speakers:', uniqueSpeakers);
      log('Proposed map from backend:', proposedMap);
      log('Initialized map for editing:', editedMap);

    } catch (err) {
      console.error("Failed to fetch or process review data:", err);
      error = `Failed to load review data: ${err.message}`;
      // Clear data on error
      uniqueSpeakers = [];
      editedMap = {};
      transcript = null;
    } finally {
      isLoading = false; // Hide loading indicator
    }
  }

  // --- Action Handlers ---

  // Called when the "Confirm Names" button is clicked
  async function submitReview() {
    if (!jobId) {
        error = "Cannot submit review: Job ID is missing.";
        return;
    }
    // Optional: Basic validation (e.g., prevent duplicate names?) - Skipped for simplicity here

    log("Attempting to submit reviewed speaker map:", editedMap);
    isSubmitting = true; // Show submitting state (e.g., disable buttons)
    error = null;        // Clear previous errors

    try {
        // Send POST request to the backend endpoint
        const response = await fetch(`${baseUrl}/update_review_data/${jobId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json', // We are sending JSON data
            },
            // Send the user-edited map in the required format: { "final_speaker_map": {...} }
            body: JSON.stringify({ final_speaker_map: editedMap }),
        });

        // Try parsing response body (even for errors, backend might provide details)
        const data = await response.json().catch(() => ({ message: "No response body or non-JSON response" }));

        // Check if the HTTP status code indicates success (e.g., 202 Accepted)
        if (!response.ok) {
            throw new Error(data.error || data.message || `Submission failed (HTTP ${response.status})`);
        }

        // --- Success ---
        log("Review submitted successfully, backend acknowledged (likely 202 Accepted).");
        // Dispatch a 'submit' event to notify the parent (JobRunner)
        dispatch('submit'); // Parent component will handle closing the dialog

    } catch (err) {
        // Handle errors during the fetch call or if backend returned an error status
        console.error("Failed to submit review:", err);
        error = `Failed to submit review: ${err.message}`;
        // Keep the dialog open on error so the user sees the message
    } finally {
        // Ensure submitting state is reset regardless of success/failure
        isSubmitting = false;
    }
  }

  // Called when the "Cancel" button is clicked
  function cancelReview() {
     log("Review cancelled by user.");
     // Dispatch a 'cancel' event to notify the parent (JobRunner)
     dispatch('cancel'); // Parent component handles closing the dialog
     // Job state on backend remains WAITING_FOR_REVIEW
  }

  // --- Utility ---
  function log(...args) {
    // Simple console logging wrapper specific to this component
    console.log('[ReviewDialog]', ...args);
  }

  // Cleanup store subscription when component is destroyed
  onDestroy(() => {
      unsubscribeApiBase();
  });

</script>

<div
  class="fixed inset-0 bg-gray-800 bg-opacity-60 backdrop-blur-sm flex items-center justify-center p-4 z-50"
  role="dialog"
  aria-modal="true"
  aria-labelledby="review-dialog-title"
  on:click|self={cancelReview}  > <div class="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">

    <div class="px-6 py-4 border-b border-gray-200 shrink-0">
      <h2 class="text-xl font-semibold text-gray-800" id="review-dialog-title">Review Speaker Names</h2>
    </div>

    <div class="px-6 py-4 flex-grow overflow-y-auto">
      {#if isLoading}
        <p class="text-center text-gray-600 py-10">Loading review data...</p>
      {:else if error}
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded" role="alert">
          <strong class="font-bold">Error Loading Data!</strong>
          <span class="block sm:inline"> {error}</span>
          <p class="text-xs mt-1">You might need to close this dialog and restart the process.</p>
        </div>
      {:else if uniqueSpeakers.length === 0}
         <p class="text-gray-600 italic py-10 text-center">No distinct speaker IDs (like SPEAKER_00) were identified in the audio. You can confirm to proceed with analysis using a single 'Unknown' speaker label.</p>
      {:else}
        <p class="text-sm text-gray-600 mb-4">
          Please review the transcript context below and assign appropriate names to the detected speaker IDs. Leave a name blank if you prefer to keep the original ID (e.g., SPEAKER_00) or if unsure.
        </p>

        <div class="space-y-3 mb-6 border rounded p-4 border-gray-200">
          <h3 class="text-md font-semibold mb-2 text-gray-700">Assign Names:</h3>
          {#each uniqueSpeakers as speakerId (speakerId)} <div class="flex flex-col sm:flex-row sm:items-center sm:gap-3">
              <label for="speaker-{speakerId}" class="w-full sm:w-28 font-mono text-sm font-medium text-gray-700 mb-1 sm:mb-0 shrink-0">{speakerId}:</label>
              <input
                type="text"
                id="speaker-{speakerId}"
                bind:value={editedMap[speakerId]}
                placeholder="Enter Name (optional)"
                class="flex-grow block w-full border border-gray-300 rounded-md shadow-sm py-1.5 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm disabled:bg-gray-100"
                disabled={isSubmitting}
              />
            </div>
          {/each}
        </div>

        <div class="mt-4">
          <h3 class="text-md font-semibold mb-2 text-gray-600">Transcript Context:</h3>
          <div class="max-h-64 overflow-y-auto bg-gray-50 p-3 rounded border border-gray-200 text-xs font-mono">
            {#if transcript && transcript.length > 0}
               {#each transcript as segment, i (i)}
                 <div class="mb-1 border-b border-gray-100 pb-1 last:border-b-0">
                   <span class="text-gray-500 mr-2">[{i}]</span>
                   <span class="font-bold {segment.speaker && segment.speaker.startsWith('SPEAKER_') ? 'text-blue-700' : 'text-gray-500'}">
                     {segment.speaker || 'NO_SPEAKER'}:
                   </span>
                   <span class="text-gray-800"> {segment.text || ''}</span>
                 </div>
               {/each}
            {:else}
               <p class="text-gray-500 italic">No transcript data available to display.</p>
            {/if}
          </div>
        </div>
      {/if} </div> <div class="px-6 py-3 bg-gray-100 border-t border-gray-200 text-right rounded-b-lg shrink-0">
       {#if !isLoading} {#if error}
                <button on:click={cancelReview} class="px-4 py-2 bg-gray-300 rounded hover:bg-gray-400">Close</button>
            {:else}
                <button
                    on:click={cancelReview}
                    disabled={isSubmitting}
                    class="mr-2 px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400 disabled:opacity-50">
                    Cancel
                </button>
                <button
                    on:click={submitReview}
                    disabled={isSubmitting}
                    class="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-wait">
                    {#if isSubmitting}
                        Submitting...
                    {:else if uniqueSpeakers.length === 0}
                         Confirm (No Specific Speakers)
                    {:else}
                         Confirm Names
                    {/if}
                </button>
            {/if}
       {/if} </div>

  </div> </div>