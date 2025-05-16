<script>
  import { onDestroy } from 'svelte';
  import { currentJob, jobConfigOverrides } from '../stores.js';
  import ReviewDialog from './ReviewDialog.svelte';
  import ResultViewer from './ResultViewer.svelte';
  import {
    startPipeline,
    getJobStatus,
    stopPipeline,
    updateReviewData
  } from '../api.js';

  let pollInterval = null;
  const POLL_MS = 2000;

  const log = (...args) => console.debug('[JobRunner]', ...args);
  const err = (...args) => console.error('[JobRunner]', ...args);

  const logLevelMap = {
    10: 'DEBUG',
    20: 'INFO',
    25: 'SUCCESS',
    30: 'WARNING',
    40: 'ERROR',
    50: 'CRITICAL'
  };

  function formatLogEntry([ts, lvl, msg]) {
    const time = new Date(ts * 1000).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
    const level = logLevelMap[lvl] || `L${lvl}`;
    return `${time} [${level}] ${msg}`;
  }

  function isTerminal(status) {
    return ['COMPLETED', 'FAILED', 'STOPPED', 'UNKNOWN', 'POLLING_FAILED', 'START_FAILED'].includes(status);
  }

  $: canStart = $currentJob.relative_audio_path &&
    (!$currentJob.job_id || isTerminal($currentJob.status));
  $: canStop = $currentJob.job_id && !isTerminal($currentJob.status);
  $: isReviewing = $currentJob.status === 'WAITING_FOR_REVIEW';

  $: {
    if (isReviewing) {
      if (pollInterval) {
        log('Reactive: Status is WAITING_FOR_REVIEW. Stopping polling for job:', $currentJob.job_id);
        stopPolling();
      }
    } else if ($currentJob.job_id && !isTerminal($currentJob.status)) {
      if (!pollInterval) {
        log('Reactive: Job active, not terminal, not in review. Starting polling for job:', $currentJob.job_id);
        startPolling();
      }
    } else {
      if (pollInterval) {
        log('Reactive: Job not pollable (no ID, terminal, or status requires no polling). Stopping polling for job:', $currentJob.job_id);
        stopPolling();
      }
    }
  }

  async function startPipelineAction() {
    if (!canStart) return;
    log('Attempting to start pipeline with:', {
      path: $currentJob.relative_audio_path,
      overrides: $jobConfigOverrides
    });
    try {
      const { job_id } = await startPipeline(
        $currentJob.relative_audio_path,
        $jobConfigOverrides
      );
      currentJob.patch({
        job_id,
        status: 'QUEUED',
        progress: 0,
        stop_requested: false,
        error_message: null,
        logs: []
      });
      log('Pipeline successfully queued as job_id:', job_id);
    } catch (e) {
      err('startPipeline failed:', e);
      currentJob.patch({
        status: 'START_FAILED',
        error_message: e.message
      });
    }
  }

  async function stopPipelineAction() {
    if (!canStop) return;
    log('Attempting to stop pipeline for job:', $currentJob.job_id);
    try {
      await stopPipeline($currentJob.job_id);
      currentJob.patch({ stop_requested: true });
      log('Stop request sent for job:', $currentJob.job_id, '. Polling will continue until STOPPED status is confirmed.');
    } catch (e) {
      err('stopPipeline API call failed:', e);
      currentJob.patch({ error_message: e.message });
    }
  }

  async function pollStatus() {
    if (!pollInterval) {
      return;
    }
    const id = $currentJob.job_id;
    if (!id || isTerminal($currentJob.status) || $currentJob.status === 'WAITING_FOR_REVIEW') {
        log('pollStatus: Conditions to stop polling already met (no id, terminal, or already in review). Forcing stop. Job ID:', id, 'Status:', $currentJob.status);
        stopPolling();
        return;
    }
    log('Polling for status of job:', id);
    try {
      const data = await getJobStatus(id);
      log('Polled status data received for job:', id, data);
      if (!data) {
          err('Polling error: Job data not found on backend for ID', id);
          currentJob.patch({ status: 'POLLING_FAILED', error_message: 'Job data not found during poll.' });
          return;
      }
      currentJob.patch({
        status:       data.status,
        progress:     data.progress     ?? $currentJob.progress,
        logs:         data.logs         ?? $currentJob.logs,
        result:       data.result       ?? $currentJob.result,
        error_message:data.error_message?? $currentJob.error_message
      });
    } catch (e) {
      err('Polling API call failed for job:', id, e);
      currentJob.patch({
        status: 'POLLING_FAILED',
        error_message: `Polling failed: ${e.message}`
      });
    }
  }

  function startPolling() {
    if (pollInterval) {
      return;
    }
    log('Starting poll loop for job:', $currentJob.job_id, ', every', POLL_MS, 'ms');
    setTimeout(pollStatus, 50);
    pollInterval = setInterval(pollStatus, POLL_MS);
  }

  function stopPolling() {
    if (!pollInterval) {
      return;
    }
    clearInterval(pollInterval);
    pollInterval = null;
    log('Stopped polling for job:', $currentJob.job_id);
  }

  async function handleReviewSubmit(event) {
    const finalMap = event.detail;
    log('ReviewDialog submitted. Attempting to update review data for job:', $currentJob.job_id, 'with map:', finalMap);
    try {
      await updateReviewData($currentJob.job_id, finalMap);
      log('Review data successfully submitted to backend for job:', $currentJob.job_id, '. Backend will continue pipeline.');
      log('Explicitly restarting polling to detect status change after review submission for job:', $currentJob.job_id);
      if (pollInterval) {
          log('handleReviewSubmit: Stopping existing poll interval before restarting.');
          stopPolling();
      }
      startPolling();
    } catch (e) {
      err('Review submission API call failed for job:', $currentJob.job_id, e);
      currentJob.patch({
        error_message: `Review submit failed: ${e.message}`
      });
    }
  }

  function handleReviewCancel() {
    log('Review cancelled by user for job:', $currentJob.job_id, '. Status remains WAITING_FOR_REVIEW. Polling remains stopped.');
  }

  onDestroy(() => {
    if (pollInterval) {
      log('JobRunner component destroyed. Stopping any active polling for job:', $currentJob.job_id);
      stopPolling();
    }
  });
</script>

<div class="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-md transition-colors duration-150 space-y-4">
  <h2 class="text-xl font-semibold text-gray-700 dark:text-gray-200">
    3. Run Pipeline & View Status
  </h2>

  <div class="flex gap-3">
    <button
      on:click={startPipelineAction}
      disabled={!canStart}
      class="px-5 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 transition-colors dark:bg-green-500 dark:hover:bg-green-600"
    >
      Start Pipeline
    </button>
    <button
      on:click={stopPipelineAction}
      disabled={!canStop}
      class="px-5 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 transition-colors dark:bg-red-500 dark:hover:bg-red-600"
    >
      Stop Pipeline
    </button>
  </div>

  {#if $currentJob.job_id}
    <div class="mt-4 p-4 bg-gray-100 dark:bg-gray-700 rounded-lg space-y-3">
      <div class="flex justify-between items-center">
        <span class="text-gray-700 dark:text-gray-200">
          Status: <strong>{$currentJob.status}</strong>
        </span>
        {#if !isTerminal($currentJob.status) && !isReviewing && pollInterval}
          <span class="text-sm text-blue-600 dark:text-blue-400 animate-pulse">
            Polling…
          </span>
        {/if}
      </div>

      {#if $currentJob.progress !== undefined && $currentJob.status !== 'WAITING_FOR_REVIEW' && !isTerminal($currentJob.status)}
        <div class="w-full bg-gray-300 dark:bg-gray-600 h-2 rounded-full overflow-hidden">
          <div
            class="h-full bg-blue-600 dark:bg-blue-500 transition-all"
            style="width: {$currentJob.progress}%"
          ></div>
        </div>
        <div class="text-right text-sm text-gray-600 dark:text-gray-300">
          {$currentJob.progress}%
        </div>
      {/if}

      {#if $currentJob.error_message}
        <div class="p-2 bg-red-100 border border-red-400 text-red-700 rounded dark:bg-red-900/30 dark:text-red-300">
          <strong>Error:</strong> {$currentJob.error_message}
        </div>
      {/if}

      {#if $currentJob.logs && $currentJob.logs.length}
        <div>
          <h4 class="font-semibold text-gray-700 dark:text-gray-200 mb-1">
            Job Logs
          </h4>
          <div
            class="bg-gray-200 dark:bg-gray-600 p-3 rounded h-32 overflow-y-auto text-xs font-mono text-gray-800 dark:text-gray-100"
          >
            {#each $currentJob.logs as entry (entry[0] + entry[2])}  <p>{formatLogEntry(entry)}</p>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}

  {#if isReviewing} <ReviewDialog
      jobId={$currentJob.job_id}
      audioRelativePath={$currentJob.relative_audio_path}
      on:submit={handleReviewSubmit}
      on:cancel={handleReviewCancel}
    />
  {/if}

  {#if $currentJob.status === 'COMPLETED'}
    <ResultViewer
      htmlPath="results/transcript.html" summaryPath="results/summary.txt"
    />
  {/if}
</div>