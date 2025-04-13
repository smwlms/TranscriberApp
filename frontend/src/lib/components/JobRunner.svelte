<script>
    import { onDestroy, onMount } from 'svelte';
    // Import relevant stores and helpers
    import { currentJob, jobConfigOverrides, apiBaseUrl, resetCurrentJob } from '../stores.js';
    // Import the new dialog component
    import ReviewDialog from './ReviewDialog.svelte';
  
    let job = null; // Local reactive copy of the currentJob store
    let overrides = {}; // Local reactive copy of overrides
    let baseUrl = ''; // Local copy of API base URL
  
    let pollInterval = null; // Interval timer handle
    let isPolling = false;   // Flag to track polling state
    let startError = '';     // Error message if starting pipeline fails
    let stopError = '';      // Error message if stopping fails
    let showReviewDialog = false; // NEW: State to control review dialog visibility
  
    // Subscribe to Svelte stores to keep local variables updated
    const unsubscribeJob = currentJob.subscribe(value => {
      job = value;
      // Automatically stop polling if the job reaches a terminal state
      if (isPolling && isTerminalStatus(job?.status)) {
        stopPolling();
      }
    });
    const unsubscribeOverrides = jobConfigOverrides.subscribe(value => { overrides = value; });
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => { baseUrl = value; });
  
    // --- Lifecycle Hooks ---
    onMount(() => {
      // If component mounts and there's already an active, non-terminal job ID in the store
      // (e.g., after a page reload), immediately start polling for its status.
      if (job?.job_id && !isTerminalStatus(job?.status)) {
        startPolling();
      }
    });
  
    onDestroy(() => {
      // Cleanup: Unsubscribe from stores and clear any active polling interval
      // to prevent memory leaks when the component is destroyed.
      unsubscribeJob();
      unsubscribeOverrides();
      unsubscribeApiBase();
      stopPolling();
    });
  
    // --- Status Polling Logic ---
    function startPolling() {
      if (isPolling || !job?.job_id) return; // Prevent multiple intervals or polling without ID
      log(`Starting status polling for job ${job.job_id}...`);
      isPolling = true;
      startError = ''; stopError = ''; // Clear previous errors
      pollStatus(); // Poll immediately once
      pollInterval = setInterval(pollStatus, 2000); // Poll every 2 seconds thereafter
    }
  
    function stopPolling() {
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
        isPolling = false;
        log(`Stopped status polling for job ${job?.job_id}.`);
      }
    }
  
    async function pollStatus() {
      // Core polling function - fetches status from backend
      if (!job?.job_id || !baseUrl) { log('Polling skipped: No job ID or base URL.'); stopPolling(); return; }
      log(`Polling status for ${job.job_id}...`, 'debug');
      try {
        const response = await fetch(`${baseUrl}/status/${job.job_id}`); // Using original blueprint route with string converter
        let data;
        if (response.status === 404) { throw new Error("Job not found on server (404)"); }
        try { data = await response.json(); } catch (e) { throw new Error(`Received non-JSON response (Status: ${response.status})`); }
        if (!response.ok) { throw new Error(data.error || data.message || `HTTP error ${response.status}`); }
  
        log(`Received status poll data: ${JSON.stringify(data)}`, 'debug');
        currentJob.set(data); // Update the central store with the latest job state
  
      } catch (error) {
        console.error('Status polling failed:', error);
        statusUpdateError(`Failed to get status update: ${error.message}`);
        // Optional: stop polling on persistent errors?
        // stopPolling();
      }
    }
  
    // --- Action Handlers ---
    async function startPipeline() {
      console.log('[JobRunner] Start button clicked!'); // Debug log
      if (!job?.relative_audio_path) { startError = 'No audio file has been uploaded.'; return; }
      log('Attempting to start pipeline...');
      startError = ''; stopError = '';
  
      const formData = new FormData();
      formData.append('relative_audio_path', job.relative_audio_path);
      for (const [key, value] of Object.entries(overrides)) {
          if (typeof value === 'boolean') { formData.append(key, value ? 'true' : 'false'); }
          else if (value !== null && value !== undefined) { formData.append(key, value); }
      }
      log(`Sending start_pipeline request with form data: ${JSON.stringify(Object.fromEntries(formData.entries()))}`, 'DEBUG');
      try {
        const response = await fetch(`${baseUrl}/start_pipeline`, { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) { throw new Error(data.error || `HTTP error ${response.status}`); }
        log(`Pipeline started successfully. Job ID: ${data.job_id}`);
        currentJob.update(j => ({ ...j, job_id: data.job_id, status: 'QUEUED', progress: 0, logs: [], result: null, error_message: null, stop_requested: false }));
        startPolling();
      } catch (error) {
        console.error('Failed to start pipeline:', error);
        startError = `Failed to start pipeline: ${error.message}`;
      }
    }
  
    async function stopPipeline() {
       // --- Unchanged ---
       if (!job?.job_id || !isStoppableStatus(job?.status)) return;
       log(`Attempting to stop job ${job.job_id}...`);
       stopError = '';
       try {
           const response = await fetch(`${baseUrl}/stop_pipeline/${job.job_id}`, { method: 'POST' });
           const data = await response.json();
           if (!response.ok) { throw new Error(data.message || data.error || `HTTP error ${response.status}`); }
           log(`Stop request sent for job ${job.job_id}.`);
           currentJob.update(j => ({ ...j, stop_requested: true, status: j.status + ' (Stopping...)'}));
       } catch(error) {
            console.error('Failed to send stop request:', error);
            stopError = `Failed to send stop request: ${error.message}`;
       }
    }
  
    // --- Utility Functions ---
    function isTerminalStatus(status) { return ['COMPLETED', 'FAILED', 'STOPPED'].includes(status); }
    function isStoppableStatus(status) { return ![null, 'COMPLETED', 'FAILED', 'STOPPED', 'QUEUED', 'WAITING_FOR_REVIEW'].includes(status); }
    function formatTimestamp(unixTs) { if (!unixTs) return "--:--:--"; try { return new Date(unixTs * 1000).toLocaleTimeString(); } catch { return "??:??:??"; } }
    function statusUpdateError(message) { console.warn("Status Update Warning:", message); }
    function log(message, level = 'info') { console.log(`[JobRunner] [${level.toUpperCase()}] ${message}`); }
  
    // --- Reactive Statements ---
    $: isInProgress = job?.status && !isTerminalStatus(job.status);
    $: canStart = !!job?.relative_audio_path && !job?.job_id && !isInProgress;
    $: canStop = !!job?.job_id && isPolling && isStoppableStatus(job.status);
  
    // Debug log for canStart changes
    $: console.log('[JobRunner] canStart check:', { canStart, relative_path: job?.relative_audio_path, job_id: job?.job_id, isInProgress });
  
    // --- !! NEW: Reactive statement to show/hide the review dialog !! ---
    $: {
        // Show dialog if status is WAITING_FOR_REVIEW and dialog isn't already shown
        if (job?.status === 'WAITING_FOR_REVIEW' && !showReviewDialog) {
            log('Job status is WAITING_FOR_REVIEW. Showing review dialog.');
            // We keep polling in the background. The dialog relies on the job_id prop.
            showReviewDialog = true;
        }
        // Automatically hide dialog if status changes *away* from WAITING_FOR_REVIEW
        // (e.g., user stops job, or backend error occurs)
        else if (job?.status !== 'WAITING_FOR_REVIEW' && showReviewDialog) {
            log(`Job status changed to ${job?.status}. Hiding review dialog.`);
            showReviewDialog = false;
        }
    }
  
    // --- Functions to handle events dispatched from ReviewDialog ---
    function handleReviewSubmit() {
        log('Review submitted successfully via dialog.');
        showReviewDialog = false; // Close the dialog
        // Polling will automatically pick up the next status (e.g., MAPPING_SPEAKERS)
    }
  
    function handleReviewCancel() {
         log('Review cancelled via dialog.');
         showReviewDialog = false; // Close the dialog
         // The job remains in WAITING_FOR_REVIEW state. The user can choose
         // to stop it using the main "Stop Pipeline" button if desired.
         // Or potentially re-open the review if we add a button for that.
    }
  
  </script>
  
  <div class="bg-white p-6 rounded-lg shadow-md relative"> <h2 class="text-xl font-semibold mb-4 text-gray-700">3. Run Pipeline & View Status</h2>
  
    {#if startError} <p class="mb-4 text-sm text-red-600 bg-red-100 p-2 rounded">Error: {startError}</p> {/if}
    {#if stopError} <p class="mb-4 text-sm text-red-600 bg-red-100 p-2 rounded">Error: {stopError}</p> {/if}
  
    <div class="flex items-center gap-4 mb-4">
      <button on:click={startPipeline} disabled={!canStart} class="px-5 py-2 bg-green-600 text-white rounded-md shadow-sm hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"> Start Pipeline </button>
      <button on:click={stopPipeline} disabled={!canStop} class="px-5 py-2 bg-red-600 text-white rounded-md shadow-sm hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"> Stop Pipeline </button>
      <button on:click={resetCurrentJob} disabled={isInProgress} title="Reset state to allow new upload/run" class="px-5 py-2 bg-gray-400 text-white rounded-md shadow-sm hover:bg-gray-500 disabled:opacity-50 disabled:cursor-not-allowed"> Reset </button>
    </div>
  
    {#if job?.job_id}
      <div class="mt-4 p-4 border border-gray-200 rounded-md bg-gray-50 space-y-3">
        <h3 class="text-lg font-medium text-gray-800">Job Status (ID: <span class="font-mono text-xs">{job.job_id}</span>)</h3>
        <div class="flex items-center gap-4">
          <span class="font-semibold text-gray-700">Status:</span>
          <span class="font-mono px-2 py-0.5 rounded text-sm whitespace-nowrap
            {job.status === 'COMPLETED' ? 'bg-green-100 text-green-800' : ''}
            {job.status === 'FAILED' || job.status === 'STOPPED' ? 'bg-red-100 text-red-800' : ''}
            {isInProgress && job.status !== 'WAITING_FOR_REVIEW' ? 'bg-blue-100 text-blue-800' : ''}
            {job.status === 'WAITING_FOR_REVIEW' ? 'bg-yellow-100 text-yellow-800' : ''}
            {job.status === 'QUEUED' ? 'bg-gray-200 text-gray-800' : ''}
          ">
            {job.status || 'N/A'} {#if job.stop_requested && !isTerminalStatus(job.status)}(Stopping...){/if}
          </span>
           {#if isPolling && !isTerminalStatus(job.status)} <span class="text-xs text-gray-500 animate-pulse">Polling Status...</span> {/if}
        </div>
        <div>
          <div class="w-full bg-gray-200 rounded-full h-2.5">
            <div class="bg-blue-600 h-2.5 rounded-full transition-all duration-300 ease-out" style="width: {job.progress || 0}%"></div>
          </div>
          <p class="text-right text-sm text-gray-600 mt-1">{job.progress || 0}%</p>
        </div>
        {#if job.error_message} <div class="p-2 bg-red-100 text-red-700 border border-red-300 rounded"> <strong>Error:</strong> {job.error_message} </div> {/if}
        {#if job.logs && job.logs.length > 0}
          <div class="mt-2">
            <h4 class="text-md font-medium text-gray-700 mb-1">Logs:</h4>
            <div class="max-h-48 overflow-y-auto bg-gray-900 text-white font-mono text-xs p-3 rounded border border-gray-700">
              {#each job.logs as [timestamp, level, message]} <div class="whitespace-pre-wrap border-b border-gray-700 py-1 last:border-b-0"> <span class="text-gray-500">{formatTimestamp(timestamp)}</span> <span class="{level === 'ERROR' || level === 'CRITICAL' ? 'text-red-400' : (level === 'WARNING' ? 'text-yellow-400' : (level === 'SUCCESS' ? 'text-green-400' : 'text-blue-300'))}"> [{level}] </span> <span class="text-gray-200"> {message}</span> </div> {/each}
            </div>
          </div>
        {/if}
        {#if job.status === 'COMPLETED' && job.result} <div class="mt-2"> <h4 class="text-md font-medium text-gray-700 mb-1">Results:</h4> <div class="text-sm space-y-1"> {#if job.result.html_transcript_path} <p>📄 <a href="{baseUrl.replace('/api/v1','')}/results/{job.result.html_transcript_path.split('/').pop()}" target="_blank" class="text-indigo-600 hover:underline">View/Download HTML Transcript</a> ({job.result.html_transcript_path})</p> {/if} {#if job.result.final_transcript_json_path} <p>📄 <a href="{baseUrl.replace('/api/v1','')}/results/{job.result.final_transcript_json_path.split('/').pop()}" target="_blank" class="text-indigo-600 hover:underline">Download Final JSON</a> ({job.result.final_transcript_json_path})</p> {/if} {#if job.result.summary_path} <p>📄 <a href="{baseUrl.replace('/api/v1','')}/results/{job.result.summary_path.split('/').pop()}" target="_blank" class="text-indigo-600 hover:underline">Download Summary Text</a> ({job.result.summary_path})</p> {/if} {#if job.result.advanced_analysis_path} <p>📄 <a href="{baseUrl.replace('/api/v1','')}/results/{job.result.advanced_analysis_path.split('/').pop()}" target="_blank" class="text-indigo-600 hover:underline">Download Advanced Analysis JSON</a> ({job.result.advanced_analysis_path})</p> {/if} {#if job.result.summary_content} <div class="mt-2 p-3 bg-gray-100 rounded border border-gray-200"> <h5 class="font-semibold mb-1">Summary Content:</h5> <pre class="whitespace-pre-wrap text-xs">{job.result.summary_content}</pre> </div> {/if} {#if job.result.final_analysis_result} <div class="mt-2 p-3 bg-gray-100 rounded border border-gray-200"> <h5 class="font-semibold mb-1">Final Analysis Content:</h5> <pre class="whitespace-pre-wrap text-xs">{job.result.final_analysis_result}</pre> </div> {/if} </div> </div> {/if}
      </div>
    {/if}
  
    {#if showReviewDialog && job?.job_id}
      <ReviewDialog
          jobId={job.job_id}
          on:submit={handleReviewSubmit}  
          on:cancel={handleReviewCancel}  
      />
    {/if}
  
  </div>
  
  <style lang="postcss">
    /* Optional: Component-specific styles if needed */
  </style>