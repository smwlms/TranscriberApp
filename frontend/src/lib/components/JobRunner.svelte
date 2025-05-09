<script>
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { currentJob, jobConfigOverrides } from '../stores.js';
  import ReviewDialog from './ReviewDialog.svelte';
  import {
    uploadAudio as apiUploadAudio,
    startPipeline as apiStartPipeline,
    getJobStatus as apiGetJobStatus,
    stopPipeline as apiStopPipeline,
    getReviewData as apiGetReviewData,
    updateReviewData as apiUpdateReviewData
  } from '../api.js';
  
  let job;
  let overrides;
  const unsubscribeJob = currentJob.subscribe(v => job = v);
  const unsubscribeOverrides = jobConfigOverrides.subscribe(v => overrides = v);
  
  let pollInterval;
  let isPolling = false;
  let startError = '';
  let stopError = '';
  
  const logLevelMap = {
    10: 'DEBUG',
    20: 'INFO',
    25: 'SUCCESS',
    30: 'WARNING',
    40: 'ERROR',
    50: 'CRITICAL'
  };
  
  function formatLogEntry(logTuple) {
    if (!Array.isArray(logTuple) || logTuple.length < 3) {
      return String(logTuple);
    }
    const timestamp = new Date(logTuple[0] * 1000)
      .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const level = logLevelMap[logTuple[1]] || `Level${logTuple[1]}`;
    const message = logTuple[2];
    return `${timestamp} [${level}] ${message}`;
  }
  
  function handleReviewSubmit() {
    console.log('[JobRunner] Review submitted. Proceeding to part 2.');
  }
  
  function handleReviewCancel() {
    console.log('[JobRunner] Review cancelled.');
  }
  
  function isTerminal(status) {
    return ['COMPLETED', 'FAILED', 'STOPPED', 'UNKNOWN', 'POLLING_FAILED'].includes(status);
  }
  
  function isStoppable(status) {
    const currentJobState = get(currentJob);
    if (!currentJobState?.job_id) return false;
    const nonStoppable = [
      'COMPLETED','FAILED','STOPPED','UNKNOWN','POLLING_FAILED',
      'QUEUED','WAITING_FOR_REVIEW'
    ];
    return !nonStoppable.includes(status);
  }
  
  async function pollStatus() {
    const currentJobState = get(currentJob);
    if (!currentJobState?.job_id) {
      return stopPolling();
    }
    if (isTerminal(currentJobState.status)) {
      return stopPolling();
    }
    try {
      const data = await apiGetJobStatus(currentJobState.job_id);
      currentJob.set(data);
      if (isTerminal(data.status)) {
        stopPolling();
      }
    } catch (e) {
      stopPolling();
      currentJob.update(j => ({
        ...j,
        status: 'POLLING_FAILED',
        error_message: j.error_message || `Polling failed: ${e.message}`
      }));
    }
  }
  
  function startPolling() {
    if (isPolling) return;
    isPolling = true;
    setTimeout(pollStatus, 50);
    pollInterval = setInterval(pollStatus, 2000);
  }
  
  function stopPolling() {
    if (!isPolling) return;
    clearInterval(pollInterval);
    isPolling = false;
  }
  
  async function startPipelineAction() {
    const currentJobState = get(currentJob);
    const audioPath = currentJobState?.relative_audio_path;
    if (!audioPath) {
      startError = 'Geen audio-bestand geselecteerd.';
      return;
    }
    startError = '';
    stopError = '';
    try {
      const data = await apiStartPipeline(audioPath, get(jobConfigOverrides));
      currentJob.set(data);
    } catch (e) {
      startError = `Start mislukt: ${e.message}`;
      currentJob.update(j => ({
        ...j,
        status: 'START_FAILED',
        error_message: j.error_message || `Start failed: ${e.message}`
      }));
    }
  }
  
  async function stopPipelineAction() {
    stopError = '';
    const currentJobState = get(currentJob);
    if (!currentJobState?.job_id) {
      stopError = 'Geen actieve job om te stoppen.';
      return;
    }
    if (!isStoppable(currentJobState.status)) {
      stopError = `Job kan niet gestopt worden in status: ${currentJobState.status}`;
      return;
    }
    try {
      const data = await apiStopPipeline(currentJobState.job_id);
      currentJob.update(j => ({ ...j, stop_requested: true }));
    } catch (e) {
      stopError = `Stop mislukt: ${e.message}`;
      currentJob.update(j => ({
        ...j,
        error_message: j.error_message || `Stop failed: ${e.message}`
      }));
    }
  }
  
  $: canStart = !!$currentJob?.relative_audio_path && (!$currentJob.job_id || isTerminal($currentJob.status));
  $: canStop = isStoppable($currentJob?.status);
  
  $: {
    if ($currentJob?.status) {
      if (!isTerminal($currentJob.status) && !isPolling) {
        startPolling();
      } else if (isTerminal($currentJob.status) && isPolling) {
        stopPolling();
      }
    } else if (isPolling) {
      stopPolling();
    }
  }
  
  onDestroy(() => {
    unsubscribeJob();
    unsubscribeOverrides();
    stopPolling();
  });
  </script>
  
  <div class="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-md transition-colors duration-150 space-y-4">
    <h2 class="text-xl font-semibold mb-4 text-gray-700 dark:text-gray-200">
      3. Run Pipeline &amp; View Status
    </h2>
  
    {#if startError}
      <div class="p-2 bg-red-100 border border-red-400 text-red-700 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300">
        {startError}
      </div>
    {/if}
    {#if stopError}
      <div class="p-2 bg-red-100 border border-red-400 text-red-700 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300">
        {stopError}
      </div>
    {/if}
  
    <div class="flex gap-3">
      <button
        on:click={startPipelineAction}
        disabled={!canStart}
        class="px-5 py-2 bg-green-600 text-white rounded-md shadow-sm hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150 whitespace-nowrap dark:bg-green-500 dark:hover:bg-green-600"
      >
        Start Pipeline
      </button>
      <button
        on:click={stopPipelineAction}
        disabled={!canStop}
        class="px-5 py-2 bg-red-600 text-white rounded-md shadow-sm hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150 whitespace-nowrap dark:bg-red-500 dark:hover:bg-red-600"
      >
        Stop Pipeline
      </button>
    </div>
  
    {#if $currentJob?.job_id}
      <div class="mt-4 p-4 bg-gray-100 dark:bg-gray-700 rounded-lg space-y-2 transition-colors duration-150">
        <div class="flex justify-between items-center">
          <span class="text-gray-700 dark:text-gray-200">
            Status: <strong>{$currentJob.status}</strong>
          </span>
          {#if isPolling && !isTerminal($currentJob.status)}
            <span class="text-sm text-blue-600 dark:text-blue-400 animate-pulse">
              Polling…
            </span>
          {/if}
        </div>
  
        {#if $currentJob.progress !== undefined}
          <div class="w-full bg-gray-300 dark:bg-gray-600 h-2 rounded-full overflow-hidden">
            <div
              class="h-full bg-blue-600 dark:bg-blue-500 transition-all duration-300 ease-in-out"
              style="width: {$currentJob.progress}%"
            ></div>
          </div>
          <div class="text-right text-sm text-gray-600 dark:text-gray-300">
            {$currentJob.progress}%
          </div>
        {/if}
  
        {#if $currentJob.error_message}
          <div class="p-2 bg-red-100 border border-red-400 text-red-700 rounded dark:bg-red-900/30 dark:border-red-700 dark:text-red-300 text-sm">
            <strong>Error:</strong> {$currentJob.error_message}
          </div>
        {/if}
  
        {#if $currentJob.logs && $currentJob.logs.length > 0}
          <div class="mt-4">
            <h4 class="text-md font-semibold mb-2 text-gray-700 dark:text-gray-200">
              Job Logs
            </h4>
            <div class="bg-gray-200 dark:bg-gray-600 p-3 rounded-lg h-32 overflow-y-auto text-xs text-gray-800 dark:text-gray-100 font-mono">
              {#each $currentJob.logs as logEntry}
                <p>{formatLogEntry(logEntry)}</p>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {/if}
  
    {#if $currentJob?.status === 'WAITING_FOR_REVIEW'}
      <ReviewDialog
        jobId={$currentJob.job_id}
        audioRelativePath={$currentJob.config?.input_audio}
        on:submit={handleReviewSubmit}
        on:cancel={handleReviewCancel}
      />
    {/if}
  </div>
  
  <style>
  </style>
  