<script>
    import { onDestroy, onMount } from 'svelte';
    import { currentJob, jobConfigOverrides, apiBaseUrl, resetCurrentJob } from '../stores.js';
    import ReviewDialog from './ReviewDialog.svelte';
    let job = null; let overrides = {}; let baseUrl = ''; let pollInterval = null; let isPolling = false;
    let startError = ''; let stopError = ''; let showReviewDialog = false;
    const unsubscribeJob = currentJob.subscribe(value => { job = value; if (isPolling && isTerminalStatus(job?.status)) { stopPolling(); } });
    const unsubscribeOverrides = jobConfigOverrides.subscribe(value => { overrides = value; });
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => { baseUrl = value; });
    onMount(() => { if (job?.job_id && !isTerminalStatus(job?.status)) { startPolling(); } });
    onDestroy(() => { unsubscribeJob(); unsubscribeOverrides(); unsubscribeApiBase(); stopPolling(); });
    function startPolling() { if (isPolling || !job?.job_id) return; log(`Starting poll...`); isPolling = true; startError = ''; stopError = ''; pollStatus(); pollInterval = setInterval(pollStatus, 2000); }
    function stopPolling() { if (pollInterval) { clearInterval(pollInterval); pollInterval = null; isPolling = false; log(`Stopped poll.`); } }
    async function pollStatus() { if (!job?.job_id || !baseUrl) { log('Polling skip.'); stopPolling(); return; } log(`Polling...`, 'debug'); try { const response = await fetch(`${baseUrl}/status/${job.job_id}`); let data; if (response.status === 404) { throw new Error("Job not found (404)"); } try { data = await response.json(); } catch (e) { throw new Error(`Non-JSON response (${response.status})`); } if (!response.ok) { throw new Error(data.error || `HTTP ${response.status}`); } log(`Poll data: ${JSON.stringify(data)}`, 'debug'); currentJob.set(data); } catch (error) { console.error('Poll fail:', error); statusUpdateError(`${error.message}`); } }
    async function startPipeline() { console.log('Start click!'); if (!job?.relative_audio_path) { startError = 'No audio uploaded.'; return; } log('Starting pipeline...'); startError = ''; stopError = ''; const formData = new FormData(); formData.append('relative_audio_path', job.relative_audio_path); for (const [k, v] of Object.entries(overrides)) { if (typeof v === 'boolean') { formData.append(k, v ? 'true' : 'false'); } else if (v !== null && v !== undefined) { formData.append(k, v); } } log(`Start request data: ${JSON.stringify(Object.fromEntries(formData.entries()))}`, 'DEBUG'); try { const response = await fetch(`${baseUrl}/start_pipeline`, { method: 'POST', body: formData }); const data = await response.json(); if (!response.ok) { throw new Error(data.error || `HTTP ${response.status}`); } log(`Pipeline started. Job ID: ${data.job_id}`); currentJob.update(j => ({ ...j, job_id: data.job_id, status: 'QUEUED', progress: 0, logs: [], result: null, error_message: null, stop_requested: false })); startPolling(); } catch (error) { console.error('Start fail:', error); startError = `${error.message}`; } }
    async function stopPipeline() { if (!job?.job_id || !isStoppableStatus(job?.status)) return; log(`Stopping job ${job.job_id}...`); stopError = ''; try { const response = await fetch(`${baseUrl}/stop_pipeline/${job.job_id}`, { method: 'POST' }); const data = await response.json(); if (!response.ok) { throw new Error(data.message || `HTTP ${response.status}`); } log(`Stop request sent.`); currentJob.update(j => ({ ...j, stop_requested: true, status: j.status + ' (Stopping...)' })); } catch (error) { console.error('Stop fail:', error); stopError = `${error.message}`; } }
    function isTerminalStatus(status) { return ['COMPLETED', 'FAILED', 'STOPPED'].includes(status); } function isStoppableStatus(status) { return ![null, 'COMPLETED', 'FAILED', 'STOPPED', 'QUEUED', 'WAITING_FOR_REVIEW'].includes(status); } function formatTimestamp(unixTs) { if (!unixTs) return "--:--:--"; try { return new Date(unixTs * 1000).toLocaleTimeString(); } catch { return "??:??:??"; } } function statusUpdateError(message) { console.warn("Status Warn:", message); } function log(message, level = 'info') { console.log(`[JobRunner] [${level.toUpperCase()}] ${message}`); }
    $: isInProgress = job?.status && !isTerminalStatus(job.status); $: canStart = !!job?.relative_audio_path && !job?.job_id && !isInProgress; $: canStop = !!job?.job_id && isPolling && isStoppableStatus(job.status);
    $: console.log('[JobRunner] canStart check:', { canStart, relative_path: job?.relative_audio_path, job_id: job?.job_id, isInProgress });
    $: { if (job?.status === 'WAITING_FOR_REVIEW' && !showReviewDialog) { log('Showing review dialog.'); showReviewDialog = true; } else if (job?.status !== 'WAITING_FOR_REVIEW' && showReviewDialog) { log(`Hiding review dialog.`); showReviewDialog = false; } }
    function handleReviewSubmit() { log('Review submit.'); showReviewDialog = false; } function handleReviewCancel() { log('Review cancel.'); showReviewDialog = false; }
 </script>
 
 <div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md relative transition-colors duration-150">
   <h2 class="text-xl font-semibold mb-4 text-gray-700 dark:text-gray-200">3. Run Pipeline & View Status</h2>
 
   {#if startError} <p class="mb-4 text-sm text-red-600 bg-red-100 p-2 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300">Error: {startError}</p> {/if}
   {#if stopError} <p class="mb-4 text-sm text-red-600 bg-red-100 p-2 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300">Error: {stopError}</p> {/if}
 
   <div class="flex items-center flex-wrap gap-4 mb-4">
       <button on:click={startPipeline} disabled={!canStart} class="px-5 py-2 bg-green-600 text-white rounded-md shadow-sm hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed"> Start Pipeline </button>
       <button on:click={stopPipeline} disabled={!canStop} class="px-5 py-2 bg-red-600 text-white rounded-md shadow-sm hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed"> Stop Pipeline </button>
       <button on:click={resetCurrentJob} disabled={isInProgress} title="Reset state" class="px-5 py-2 bg-gray-500 text-white rounded-md shadow-sm hover:bg-gray-600 dark:bg-gray-600 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"> Reset </button>
   </div>
 
   {#if job?.job_id}
     <div class="mt-4 p-4 border border-gray-200 dark:border-gray-700 rounded-md bg-gray-50 dark:bg-gray-800/50 space-y-3 transition-colors duration-150">
       <h3 class="text-lg font-medium text-gray-800 dark:text-gray-100 mb-2">Job Status (ID: <span class="font-mono text-xs break-all">{job.job_id}</span>)</h3>
       <div class="flex items-center gap-4 mb-2 flex-wrap">
         <span class="font-semibold text-gray-700 dark:text-gray-300">Status:</span>
         <span class="font-mono px-2 py-0.5 rounded text-sm whitespace-nowrap
           {job.status === 'COMPLETED' ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' : ''}
           {job.status === 'FAILED' || job.status === 'STOPPED' ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' : ''}
           {isInProgress && job.status !== 'WAITING_FOR_REVIEW' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300' : ''}
           {job.status === 'WAITING_FOR_REVIEW' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-800/40 dark:text-yellow-200' : ''}
           {job.status === 'QUEUED' ? 'bg-gray-200 text-gray-800 dark:bg-gray-600 dark:text-gray-100' : ''}
         ">
           {job.status || 'N/A'} {#if job.stop_requested && !isTerminalStatus(job.status)}(Stopping...){/if}
         </span>
          {#if isPolling && !isTerminalStatus(job.status)} <span class="text-xs text-gray-500 dark:text-gray-400 animate-pulse">Polling Status...</span> {/if}
       </div>
       <div>
         <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5"> <div class="bg-blue-600 dark:bg-blue-500 h-2.5 rounded-full transition-all duration-300 ease-out" style="width: {job.progress || 0}%"></div> </div>
         <p class="text-right text-sm text-gray-600 dark:text-gray-400 mt-1">{job.progress || 0}%</p>
       </div>
       {#if job.error_message} <div class="p-2 bg-red-100 text-red-700 border border-red-300 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300"> <strong>Error:</strong> {job.error_message} </div> {/if}
       {#if job.logs && job.logs.length > 0}
         <div class="mt-2">
           <h4 class="text-md font-medium text-gray-700 dark:text-gray-300 mb-1">Logs:</h4>
           <div class="max-h-48 overflow-y-auto bg-gray-900 text-white font-mono text-xs p-3 rounded border border-gray-700 dark:border-gray-600 dark:bg-black/50">
             {#each job.logs as [timestamp, level, message] (timestamp)} <div class="whitespace-pre-wrap border-b border-gray-700 dark:border-gray-600 py-1 last:border-b-0"> <span class="text-gray-400 dark:text-gray-500">{formatTimestamp(timestamp)}</span> <span class="{level === 'ERROR' || level === 'CRITICAL' ? 'text-red-400 dark:text-red-400' : (level === 'WARNING' ? 'text-yellow-400 dark:text-yellow-300' : (level === 'SUCCESS' ? 'text-green-400 dark:text-green-400' : 'text-blue-300 dark:text-blue-400'))}"> [{level}] </span> <span class="text-gray-100 dark:text-gray-300"> {message}</span> </div> {/each}
           </div>
         </div>
       {/if}
        {#if job.status === 'COMPLETED' && job.result}
          <div class="mt-2">
            <h4 class="text-md font-medium text-gray-700 dark:text-gray-300 mb-1">Results:</h4>
            <div class="text-sm space-y-1">
              {#if job.result.html_transcript_path} <p>📄 <a href="{baseUrl.replace('/api/v1','')}/results/{job.result.html_transcript_path.split('/').pop()}" target="_blank" class="text-indigo-600 dark:text-indigo-400 hover:underline">View/Download HTML</a> ({job.result.html_transcript_path})</p> {/if}
              {#if job.result.final_transcript_json_path} <p>📄 <a href="{baseUrl.replace('/api/v1','')}/results/{job.result.final_transcript_json_path.split('/').pop()}" target="_blank" class="text-indigo-600 dark:text-indigo-400 hover:underline">Download Final JSON</a> ({job.result.final_transcript_json_path})</p> {/if}
              {#if job.result.summary_path} <p>📄 <a href="{baseUrl.replace('/api/v1','')}/results/{job.result.summary_path.split('/').pop()}" target="_blank" class="text-indigo-600 dark:text-indigo-400 hover:underline">Download Summary Text</a> ({job.result.summary_path})</p> {/if}
              {#if job.result.advanced_analysis_path} <p>📄 <a href="{baseUrl.replace('/api/v1','')}/results/{job.result.advanced_analysis_path.split('/').pop()}" target="_blank" class="text-indigo-600 dark:text-indigo-400 hover:underline">Download Advanced Analysis JSON</a> ({job.result.advanced_analysis_path})</p> {/if}
              {#if job.result.summary_content} <div class="mt-2 p-3 bg-gray-100 dark:bg-gray-700/50 rounded border border-gray-200 dark:border-gray-600"> <h5 class="font-semibold mb-1 dark:text-gray-200">Summary:</h5> <pre class="whitespace-pre-wrap text-xs dark:text-gray-300">{job.result.summary_content}</pre> </div> {/if}
              {#if job.result.final_analysis_result} <div class="mt-2 p-3 bg-gray-100 dark:bg-gray-700/50 rounded border border-gray-200 dark:border-gray-600"> <h5 class="font-semibold mb-1 dark:text-gray-200">Final Analysis:</h5> <pre class="whitespace-pre-wrap text-xs dark:text-gray-300">{job.result.final_analysis_result}</pre> </div> {/if}
            </div>
          </div>
        {/if}
     </div>
   {/if}
 
   {#if showReviewDialog && job?.job_id}
     <ReviewDialog
         jobId={job?.job_id} on:submit={handleReviewSubmit}
         on:cancel={handleReviewCancel}
     />
   {/if}
 </div>
 <style>/* Optional styles */</style>