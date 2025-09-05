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
  $: canStop = $currentJob.job_id && !isTerminal($currentJob.status) && !$currentJob.stop_requested;
  $: isReviewing = $currentJob.status === 'WAITING_FOR_REVIEW';
  let reviewOpen = false;

  $: {
    // Open dialog automatically when entering WAITING_FOR_REVIEW
    if (isReviewing && !reviewOpen) reviewOpen = true;
    // Ensure it closes when leaving review state
    if (!isReviewing && reviewOpen) reviewOpen = false;
  }

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
  // Force refetch of static result files when a job completes or re‑analyzes
  let _lastStatusForRev = null;
  let _lastSummaryPath = null;
  let _resourceRev = 0;
  $: cacheSuffix = $currentJob.job_id ? `?v=${$currentJob.job_id}-${_resourceRev}` : '';

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
      // Track transitions to bump resource revision when final artifacts change
      const nextStatus = data.status;
      const nextSummaryPath = data?.result?.summary_path;
      if (nextStatus === 'COMPLETED' && (_lastStatusForRev !== 'COMPLETED' || nextSummaryPath !== _lastSummaryPath)) {
        _resourceRev += 1; // force cache-busting for ResultViewer paths
      }
      _lastStatusForRev = nextStatus;
      _lastSummaryPath = nextSummaryPath;

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

  function newRun() {
    // Reset job state but keep selected audio and overrides
    const keepPath = $currentJob.relative_audio_path;
    log('Resetting UI for a new run. Keeping audio path:', keepPath);
    currentJob.reset();
    if (keepPath) currentJob.patch({ relative_audio_path: keepPath });
    // polling is already cleared on reset via reactivity, but ensure stopped
    stopPolling();
  }

  async function handleReviewSubmit(event) {
    const finalMap = event.detail;
    log('ReviewDialog submitted. Attempting to update review data for job:', $currentJob.job_id, 'with map:', finalMap);
    try {
      await updateReviewData($currentJob.job_id, finalMap);
      log('Review data successfully submitted to backend for job:', $currentJob.job_id, '. Backend will continue pipeline.');
      // Optimistically close the dialog immediately to avoid double-submit
      currentJob.patch({ status: 'REVIEW_SUBMITTED' });
      log('Explicitly restarting polling to detect status change after review submission for job:', $currentJob.job_id);
      if (pollInterval) {
          log('handleReviewSubmit: Stopping existing poll interval before restarting.');
          stopPolling();
      }
      startPolling();
    } catch (e) {
      err('Review submission API call failed for job:', $currentJob.job_id, e);
      // If backend already advanced (409), close the dialog and resume polling
      if (e && (e.status === 409)) {
        log('Review already processed on backend (409). Closing dialog and resuming polling.');
        currentJob.patch({ status: 'REVIEW_SUBMITTED' });
        if (pollInterval) stopPolling();
        startPolling();
        return;
      }
      currentJob.patch({ error_message: `Review submit failed: ${e.message}` });
    }
  }

  import { logClientEvent } from '../api.js';

  async function handleReviewCancel() {
    log('Review cancelled by user for job:', $currentJob.job_id, '. Status remains WAITING_FOR_REVIEW.');
    reviewOpen = false; // close the dialog locally while staying in review state
    try {
      if ($currentJob.job_id) await logClientEvent($currentJob.job_id, 'Review dialog cancelled by user');
    } catch (e) {
      err('Failed to log client cancel event:', e);
    }
  }

  onDestroy(() => {
    if (pollInterval) {
      log('JobRunner component destroyed. Stopping any active polling for job:', $currentJob.job_id);
      stopPolling();
    }
  });
</script>

<div class="surface-card space-y-4">
  <h2 class="section-title">4. Run & Status</h2>

  <div class="flex flex-wrap items-center gap-2">
    <button on:click={startPipelineAction} disabled={!canStart} class="btn btn-primary">Start Pipeline</button>
    {#if canStop}
      <button on:click={stopPipelineAction} class="btn btn-danger">Stop</button>
    {/if}
    <button on:click={newRun} class="btn btn-ghost" title="Reset UI zonder audio te verliezen">Nieuwe run</button>
  </div>

  {#if $currentJob.job_id}
    <div class="mt-2 p-4 rounded-lg border" style="border-color: rgb(var(--border)); background-color: rgb(var(--page));">
      <div class="flex justify-between items-center">
        <span>
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
          <h4 class="font-semibold mb-1">
            Job Logs
          </h4>
          <div class="p-3 rounded h-32 overflow-y-auto text-xs font-mono" style="background: rgba(148,163,184,0.15);">
            {#each $currentJob.logs as entry (entry[0] + entry[2])}  <p>{formatLogEntry(entry)}</p>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}

  {#if isReviewing && reviewOpen} <ReviewDialog
      jobId={$currentJob.job_id}
      audioRelativePath={$currentJob.relative_audio_path}
      on:submit={handleReviewSubmit}
      on:cancel={handleReviewCancel}
    />
  {/if}

  {#if $currentJob.status === 'COMPLETED'}
    <ResultViewer
      htmlPath={$currentJob.result?.transcript_path ? `${$currentJob.result.transcript_path}${cacheSuffix}` : undefined}
      summaryPath={$currentJob.result?.summary_path ? `${$currentJob.result.summary_path}${cacheSuffix}` : undefined}
      advancedPath={$currentJob.result?.advanced_analysis_path ? `${$currentJob.result.advanced_analysis_path}${cacheSuffix}` : undefined}
      jobId={$currentJob.job_id}
      audioRelativePath={$currentJob.relative_audio_path}
      on:rerun={() => {
        // Reset local UI state and resume polling for re-analysis
        if (pollInterval) stopPolling();
        currentJob.patch({ status: 'ANALYZING', progress: 0 });
        startPolling();
      }}
    />
  {/if}
</div>
