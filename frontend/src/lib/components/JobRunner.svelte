<script>
    import { onDestroy, onMount } from 'svelte';
    // Import stores and the API base URL
    // resetCurrentJob is needed if you want the reset button to clear the state
    import { currentJob, jobConfigOverrides, apiBaseUrl, resetCurrentJob } from '../stores.js';
    // Import the ReviewDialog component
    import ReviewDialog from './ReviewDialog.svelte';

    // --- Component State & Store Subscriptions ---
    let job = null; // Holds the current job state from the store
    let overrides = {}; // Holds configuration overrides from the store
    let baseUrl = ''; // Holds the API base URL from the store
    let pollInterval = null; // Interval ID for status polling
    let isPolling = false; // Flag to indicate if polling is active
    let startError = ''; // Stores errors related to starting the pipeline
    let stopError = ''; // Stores errors related to stopping the pipeline
    let showReviewDialog = false; // Controls visibility of the speaker review modal

    // Subscribe to stores and update local variables
    const unsubscribeJob = currentJob.subscribe(value => {
        job = value;
        // Stop polling automatically if the job reaches a terminal state
        if (isPolling && isTerminalStatus(job?.status)) {
            stopPolling();
        }
    });
    const unsubscribeOverrides = jobConfigOverrides.subscribe(value => { overrides = value; });
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => { baseUrl = value; });

    // --- Lifecycle Hooks ---
    onMount(() => {
        // If there's an active job when the component mounts (e.g., after page refresh), start polling
        if (job?.job_id && !isTerminalStatus(job?.status)) {
            startPolling();
        }
    });

    onDestroy(() => {
        // Cleanup: Unsubscribe from stores and clear polling interval
        unsubscribeJob();
        unsubscribeOverrides();
        unsubscribeApiBase();
        stopPolling();
    });

    // --- Polling Logic ---
    function startPolling() {
        if (isPolling || !job?.job_id) return; // Don't start if already polling or no job ID
        log(`Starting status polling for job ${job.job_id}...`);
        isPolling = true;
        startError = ''; // Clear previous errors
        stopError = '';
        pollStatus(); // Poll immediately
        pollInterval = setInterval(pollStatus, 2000); // Poll every 2 seconds
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
            isPolling = false;
            log(`Stopped status polling.`);
        }
    }

    async function pollStatus() {
        if (!job?.job_id || !baseUrl) {
            log('Polling skipped (no job_id or baseUrl).', 'debug');
            stopPolling(); // Stop polling if essential info is missing
            return;
        }
        log(`Polling status for job ${job.job_id}...`, 'debug');
        try {
            const response = await fetch(`${baseUrl}/status/${job.job_id}`);
            let data;
            // Handle 404 specifically, might mean job was deleted or ID incorrect
            if (response.status === 404) {
                throw new Error("Job not found on server (404)");
            }
            // Try parsing JSON, handle non-JSON responses
            try {
                data = await response.json();
            } catch (e) {
                throw new Error(`Server returned non-JSON response (Status: ${response.status})`);
            }
            // Handle other non-OK HTTP statuses
            if (!response.ok) {
                throw new Error(data.error || `Server returned HTTP ${response.status}`);
            }
            // Update the global job store with the latest status
            log(`Poll received data: ${JSON.stringify(data)}`, 'debug');
            currentJob.set(data);
        } catch (error) {
            console.error('Polling failed:', error);
            // Optionally display a persistent error or attempt retries
            statusUpdateError(`Polling failed: ${error.message}`);
            // Consider stopping polling on certain errors (like 404)
            if (error.message.includes("404")) {
                 stopPolling();
                 // Maybe reset job state or notify user more prominently
                 currentJob.update(j => ({ ...j, status: 'UNKNOWN (Not Found)', error_message: 'Job not found on server.' }));
            }
        }
    }

    // --- Pipeline Actions ---
    async function startPipeline() {
        console.log('Start Pipeline button clicked.');
        // Check if an audio file has been uploaded (path stored in job store)
        if (!job?.relative_audio_path) {
            startError = 'No audio file has been uploaded or selected.';
            return;
        }
        log('Attempting to start pipeline...');
        startError = ''; // Clear previous start errors
        stopError = '';

        // Prepare form data for the request
        const formData = new FormData();
        formData.append('relative_audio_path', job.relative_audio_path);
        // Add configuration overrides from the store to the form data
        for (const [key, value] of Object.entries(overrides)) {
             // Handle boolean conversion correctly for form data
             if (typeof value === 'boolean') {
                 formData.append(key, value ? 'true' : 'false');
             } else if (value !== null && value !== undefined && value !== '') {
                 // Append other non-null/undefined/empty values
                 formData.append(key, value);
             }
        }
        log(`Start pipeline request form data: ${JSON.stringify(Object.fromEntries(formData.entries()))}`, 'debug');

        try {
            // Make the POST request to start the pipeline
            const response = await fetch(`${baseUrl}/start_pipeline`, {
                method: 'POST',
                body: formData, // Send form data
            });
            const data = await response.json(); // Assume server always returns JSON
            if (!response.ok) {
                // Throw error if response status is not OK (e.g., 4xx, 5xx)
                throw new Error(data.error || `Server returned HTTP ${response.status}`);
            }
            // Pipeline started successfully
            log(`Pipeline start initiated successfully. Job ID: ${data.job_id}`);
            // Update the job store with the new job ID and initial status
            currentJob.update(j => ({
                ...j, // Keep existing info like relative_audio_path
                job_id: data.job_id,
                status: 'QUEUED', // Initial status after successful start request
                progress: 0,
                logs: [],
                result: null,
                error_message: null,
                stop_requested: false,
                // Optionally clear specific fields if needed on restart
            }));
            startPolling(); // Start polling for status updates
        } catch (error) {
            console.error('Pipeline start failed:', error);
            startError = `Failed to start pipeline: ${error.message}`;
        }
    }

    async function stopPipeline() {
        // Check if there's a job ID and if the job is in a state that can be stopped
        if (!job?.job_id || !isStoppableStatus(job?.status)) return;
        log(`Requesting stop for job ${job.job_id}...`);
        stopError = ''; // Clear previous stop errors
        try {
            // Make the POST request to stop the pipeline
            const response = await fetch(`${baseUrl}/stop_pipeline/${job.job_id}`, {
                method: 'POST',
            });
            const data = await response.json(); // Assume JSON response
            if (!response.ok) {
                // Throw error if stop request failed server-side
                throw new Error(data.message || data.error || `Server returned HTTP ${response.status}`);
            }
            // Stop request was accepted by the server
            log(`Stop request sent successfully for job ${job.job_id}.`);
            // Update local state immediately to reflect the request
            currentJob.update(j => ({ ...j, stop_requested: true, status: j.status + ' (Stopping Requested)' }));
            // Polling will eventually reflect the final STOPPED status
        } catch (error) {
            console.error('Pipeline stop failed:', error);
            stopError = `Failed to stop pipeline: ${error.message}`;
        }
    }

    // --- Helper Functions ---
    function isTerminalStatus(status) {
        // Returns true if the job status indicates it has finished (successfully or not)
        return ['COMPLETED', 'FAILED', 'STOPPED', 'UNKNOWN (Not Found)'].includes(status);
    }

    function isStoppableStatus(status) {
        // Returns true if the job is in a state where requesting a stop makes sense
        // Cannot stop if already finished, not started, or already waiting for user input
        const nonStoppableStates = [
            null, '', undefined,
            'COMPLETED', 'FAILED', 'STOPPED', 'UNKNOWN (Not Found)',
            'QUEUED', // Usually too fast to stop, or implies it hasn't started processing
            'WAITING_FOR_REVIEW' // Requires user action (confirm/cancel review)
        ];
        return !nonStoppableStates.includes(status);
    }

    function formatTimestamp(unixTs) {
        // Formats a Unix timestamp (seconds) into a readable time string
        if (!unixTs) return "--:--:--";
        try {
            return new Date(unixTs * 1000).toLocaleTimeString(); // Convert seconds to milliseconds
        } catch {
            return "??:??:??"; // Fallback for invalid timestamp
        }
    }

    function statusUpdateError(message) {
        // Placeholder for potentially displaying polling errors more prominently in the UI
        console.warn("Status Update Warning:", message);
        // Example: You could update a dedicated error variable here
        // pollingError = message;
    }

    function log(message, level = 'info') {
        // Simple console logging wrapper for this component
        console.log(`[JobRunner] [${level.toUpperCase()}] ${message}`);
    }

    // --- Reactive Declarations ---
    // These recalculate automatically when their dependencies (job store) change

    // Determine if a job is currently running (not in a terminal state)
    $: isInProgress = job?.status && !isTerminalStatus(job.status);

    // Determine if the "Start Pipeline" button should be enabled
    $: canStart = !!job?.relative_audio_path && (!job?.job_id || isTerminalStatus(job?.status));

    // Determine if the "Stop Pipeline" button should be enabled
    $: canStop = !!job?.job_id && isPolling && isStoppableStatus(job.status);

    // Log changes in start capability for debugging
    $: console.log('[JobRunner] CanStart Check:', { canStart, relative_path: job?.relative_audio_path, job_id: job?.job_id, isInProgress, status: job?.status });

    // --- Reactive Logic for Review Dialog ---
    // This block runs whenever job.status changes
    $: {
        if (job?.status === 'WAITING_FOR_REVIEW' && !showReviewDialog) {
            log('Status changed to WAITING_FOR_REVIEW, showing review dialog.');
            showReviewDialog = true; // Show the dialog
        } else if (job?.status !== 'WAITING_FOR_REVIEW' && showReviewDialog) {
            // If status changes away from review while dialog is shown, hide it
            log(`Status is no longer WAITING_FOR_REVIEW (now ${job?.status}), hiding review dialog.`);
            showReviewDialog = false; // Hide the dialog
        }
    }

    // --- Event Handlers for Review Dialog ---
    function handleReviewSubmit() {
        log('ReviewDialog submitted event received.');
        showReviewDialog = false; // Close the dialog
        // Status should update automatically via polling after submission triggers Part 2
    }

    function handleReviewCancel() {
        log('ReviewDialog cancel event received.');
        showReviewDialog = false; // Close the dialog
        // Optionally, you might want to trigger a stop or handle cancellation backend-side
        // For now, just closing the dialog. The job remains WAITING_FOR_REVIEW.
    }
 </script>

 <div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md relative transition-colors duration-150">
   <h2 class="text-xl font-semibold mb-4 text-gray-700 dark:text-gray-200">3. Run Pipeline & View Status</h2>

   {#if startError}
     <p class="mb-4 text-sm text-red-600 bg-red-100 p-2 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300">Start Error: {startError}</p>
   {/if}
   {#if stopError}
     <p class="mb-4 text-sm text-red-600 bg-red-100 p-2 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300">Stop Error: {stopError}</p>
   {/if}

   <div class="flex items-center flex-wrap gap-4 mb-4">
       <button on:click={startPipeline} disabled={!canStart} class="px-5 py-2 bg-green-600 text-white rounded-md shadow-sm hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed">
         Start Pipeline
       </button>
       <button on:click={stopPipeline} disabled={!canStop} class="px-5 py-2 bg-red-600 text-white rounded-md shadow-sm hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed">
         Stop Pipeline
       </button>
       <button on:click={resetCurrentJob} disabled={isInProgress && !isTerminalStatus(job?.status)} title="Clear current job state" class="px-5 py-2 bg-gray-500 text-white rounded-md shadow-sm hover:bg-gray-600 dark:bg-gray-600 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed">
         Reset UI State
       </button>
   </div>

   {#if job?.job_id}
     <div class="mt-4 p-4 border border-gray-200 dark:border-gray-700 rounded-md bg-gray-50 dark:bg-gray-800/50 space-y-3 transition-colors duration-150">
       <h3 class="text-lg font-medium text-gray-800 dark:text-gray-100 mb-2">Job Status (ID: <span class="font-mono text-xs break-all">{job.job_id}</span>)</h3>
     </div>
   {/if}

       <div class="flex items-center gap-4 mb-2 flex-wrap">
         <span class="font-semibold text-gray-700 dark:text-gray-300">Status:</span>
         <span class="font-mono px-2 py-0.5 rounded text-sm whitespace-nowrap
           {job.status === 'COMPLETED' ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' : ''}
           {job.status === 'FAILED' || job.status === 'STOPPED' || job.status === 'UNKNOWN (Not Found)' ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' : ''}
           {isInProgress && job.status !== 'WAITING_FOR_REVIEW' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300' : ''}
           {job.status === 'WAITING_FOR_REVIEW' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-800/40 dark:text-yellow-200' : ''}
           {job.status === 'QUEUED' ? 'bg-gray-200 text-gray-800 dark:bg-gray-600 dark:text-gray-100' : ''}
         ">
           {job.status || 'N/A'} {#if job.stop_requested && !isTerminalStatus(job.status)}(Stopping Requested){/if}
         </span>
          {#if isPolling && !isTerminalStatus(job.status)}
            <span class="text-xs text-gray-500 dark:text-gray-400 animate-pulse">Polling Status...</span>
          {/if}
       </div>

       {#if isInProgress || job.status === 'COMPLETED'}
         <div>
           <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
             <div class="bg-blue-600 dark:bg-blue-500 h-2.5 rounded-full transition-all duration-300 ease-out" style="width: {job.progress || 0}%"></div>
           </div>
           <p class="text-right text-sm text-gray-600 dark:text-gray-400 mt-1">{job.progress || 0}%</p>
         </div>
       {/if}

       {#if job.error_message}
         <div class="p-2 bg-red-100 text-red-700 border border-red-300 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300">
           <strong>Error:</strong> {job.error_message}
         </div>
       {/if}

       {#if job.logs && job.logs.length > 0}
         <div class="mt-2">
           <h4 class="text-md font-medium text-gray-700 dark:text-gray-300 mb-1">Logs:</h4>
           <div class="max-h-48 overflow-y-auto bg-gray-900 text-white font-mono text-xs p-3 rounded border border-gray-700 dark:border-gray-600 dark:bg-black/50">
             {#each job.logs as [timestamp, level, message] (timestamp + message)} <div class="whitespace-pre-wrap border-b border-gray-700 dark:border-gray-600 py-1 last:border-b-0">
                    <span class="text-gray-400 dark:text-gray-500">{formatTimestamp(timestamp)}</span>
                    <span class="{level === 'ERROR' || level === 'CRITICAL' ? 'text-red-400 dark:text-red-400' : (level === 'WARNING' ? 'text-yellow-400 dark:text-yellow-300' : (level === 'SUCCESS' ? 'text-green-400 dark:text-green-400' : 'text-blue-300 dark:text-blue-400'))}">
                      [{level}]
                    </span>
                    <span class="text-gray-100 dark:text-gray-300"> {message}</span>
                </div>
             {/each}
           </div>
         </div>
       {/if}

       {#if job.status === 'COMPLETED' && job.result}
          <div class="mt-2">
            <h4 class="text-md font-medium text-gray-700 dark:text-gray-300 mb-1">Results:</h4>
            <div class="text-sm space-y-1">
              {#if job.result.html_transcript_path}
                 <p>📄 <a href={`/results/${job.result.html_transcript_path.split('/').pop()}`} target="_blank" download class="text-indigo-600 dark:text-indigo-400 hover:underline">Download HTML Transcript</a></p>
              {/if}
              {#if job.result.final_transcript_json_path}
                 <p>📄 <a href={`/results/${job.result.final_transcript_json_path.split('/').pop()}`} target="_blank" download class="text-indigo-600 dark:text-indigo-400 hover:underline">Download Final JSON Transcript</a></p>
              {/if}
              {#if job.result.summary_path}
                 <p>📄 <a href={`/results/${job.result.summary_path.split('/').pop()}`} target="_blank" download class="text-indigo-600 dark:text-indigo-400 hover:underline">Download Summary Text</a></p>
              {/if}
              {#if job.result.advanced_analysis_path}
                 <p>📄 <a href={`/results/${job.result.advanced_analysis_path.split('/').pop()}`} target="_blank" download class="text-indigo-600 dark:text-indigo-400 hover:underline">Download Advanced Analysis JSON</a></p>
              {/if}

              {#if job.result.summary_content}
                <div class="mt-2 p-3 bg-gray-100 dark:bg-gray-700/50 rounded border border-gray-200 dark:border-gray-600">
                    <h5 class="font-semibold mb-1 dark:text-gray-200">Summary:</h5>
                    <pre class="whitespace-pre-wrap text-xs dark:text-gray-300">{job.result.summary_content}</pre>
                </div>
              {/if}

              {#if job.result.final_analysis_result}
                <div class="mt-2 p-3 bg-gray-100 dark:bg-gray-700/50 rounded border border-gray-200 dark:border-gray-600">
                    <h5 class="font-semibold mb-1 dark:text-gray-200">Final Analysis:</h5>
                    <pre class="whitespace-pre-wrap text-xs dark:text-gray-300">{job.result.final_analysis_result}</pre>
                </div>
              {/if}
            </div>
          </div>
        {/if}
     </div>
   <div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md relative transition-colors duration-150">
   {#if showReviewDialog && job?.job_id}
     <ReviewDialog
         jobId={job.job_id}
         audioPath={job.config?.input_audio}
         on:submit={handleReviewSubmit}
         on:cancel={handleReviewCancel}
     />
   {/if}

 </div>
 <style>/* Optional styles can go here */</style>