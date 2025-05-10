<!-- frontend/src/JobRunner.svelte -->
<script>
  import { onDestroy } from 'svelte';
  import { currentJob, jobConfigOverrides } from '../stores.js';
  import ReviewDialog from './ReviewDialog.svelte';
  import {
    uploadAudio,
    startPipeline,
    getJobStatus,
    stopPipeline
  } from '../api.js';

  /* ─── Helpers ──────────────────────────────────────────────────────────── */
  const log = (...a) => console.debug('[JobRunner]', ...a);
  const err = (...a) => console.error('[JobRunner]', ...a);

  /* Log‑levels naar leesbare labels */
  const logLevelMap = {
    10: 'DEBUG', 20: 'INFO', 25: 'SUCCESS',
    30: 'WARNING', 40: 'ERROR', 50: 'CRITICAL'
  };
  function formatLogEntry([ts, lvl, msg]) {
    const time = new Date(ts * 1000)
      .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const level = logLevelMap[lvl] || `L${lvl}`;
    return `${time} [${level}] ${msg}`;
  }

  /* ─── Polling ──────────────────────────────────────────────────────────── */
  let pollInterval;
  const POLL_MS = 2000;

  function startPolling() {
    if (pollInterval) return;
    log('Start polling every', POLL_MS, 'ms');
    setTimeout(pollStatus, 100);          // eerste poll snel
    pollInterval = setInterval(pollStatus, POLL_MS);
  }

  function stopPolling() {
    clearInterval(pollInterval);
    pollInterval = null;
    log('Stopped polling');
  }

  function isTerminal(status) {
    return ['COMPLETED','FAILED','STOPPED','UNKNOWN','POLLING_FAILED'].includes(status);
  }

  async function pollStatus() {
    const id = $currentJob.job_id;
    if (!id) return stopPolling();
    if (isTerminal($currentJob.status)) return stopPolling();

    try {
      const data = await getJobStatus(id);
      log('Status', data);
      currentJob.patch({
        status: data.status,
        progress: data.progress ?? $currentJob.progress,
        logs: data.logs ?? $currentJob.logs,
        result: data.result ?? $currentJob.result,
        error_message: data.error_message ?? $currentJob.error_message
      });
      if (isTerminal(data.status)) stopPolling();
    } catch (e) {
      err('Polling failed:', e);
      currentJob.patch({
        status: 'POLLING_FAILED',
        error_message: `Polling failed: ${e.message}`
      });
      stopPolling();
    }
  }

  /* ─── UI‑reactieve button‑states ───────────────────────────────────────── */
  $: canStart = $currentJob.relative_audio_path &&
                (!$currentJob.job_id || isTerminal($currentJob.status));
  $: canStop  = $currentJob.job_id && !isTerminal($currentJob.status);

  /* ─── Pipeline Actions ────────────────────────────────────────────────── */
  async function startPipelineAction() {
    if (!canStart) return;
    log('Start pipeline', $currentJob.relative_audio_path, $jobConfigOverrides);
    try {
      const { job_id } = await startPipeline($currentJob.relative_audio_path, $jobConfigOverrides);
      currentJob.patch({
        job_id,
        status: 'QUEUED',
        progress: 0,
        stop_requested: false,
        error_message: null,
        logs: []
      });
      startPolling();
    } catch (e) {
      err('startPipeline failed:', e);
      currentJob.patch({ status: 'START_FAILED', error_message: e.message });
    }
  }

  async function stopPipelineAction() {
    if (!canStop) return;
    try {
      await stopPipeline($currentJob.job_id);
      currentJob.patch({ stop_requested: true });
      log('Stop requested');
    } catch (e) {
      err('stopPipeline failed:', e);
      currentJob.patch({ error_message: e.message });
    }
  }

  /* ─── Review handlers ─────────────────────────────────────────────────── */
  function handleReviewSubmit() {
    /* ReviewDialog heeft de speaker‑map al verzonden.
       Enkel polling herstarten om Part 2 te volgen. */
    log('Review finished – resume polling');
    startPolling();
  }
  function handleReviewCancel() {
    log('Review cancelled');
  }

  /* ─── Cleanup ─────────────────────────────────────────────────────────── */
  onDestroy(stopPolling);
</script>

<div class="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-md space-y-4">
  <h2 class="text-xl font-semibold text-gray-700 dark:text-gray-200">
    3. Run Pipeline&nbsp;&amp;&nbsp;View Status
  </h2>

  <div class="flex gap-3">
    <button
      on:click={startPipelineAction}
      disabled={!canStart}
      class="px-5 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 dark:bg-green-500 dark:hover:bg-green-600">
      Start Pipeline
    </button>
    <button
      on:click={stopPipelineAction}
      disabled={!canStop}
      class="px-5 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 dark:bg-red-500 dark:hover:bg-red-600">
      Stop Pipeline
    </button>
  </div>

  {#if $currentJob.job_id}
    <!-- Status panel -->
    <div class="mt-4 p-4 bg-gray-100 dark:bg-gray-700 rounded-lg space-y-3">
      <div class="flex justify-between items-center">
        <span class="text-gray-700 dark:text-gray-200">
          Status: <strong>{$currentJob.status}</strong>
        </span>
        {#if !isTerminal($currentJob.status)}
          <span class="text-sm text-blue-600 dark:text-blue-400 animate-pulse">Polling…</span>
        {/if}
      </div>

      {#if $currentJob.progress !== undefined}
        <div class="w-full bg-gray-300 dark:bg-gray-600 h-2 rounded-full overflow-hidden">
          <div class="h-full bg-blue-600 dark:bg-blue-500 transition-all" style="width: {$currentJob.progress}%"></div>
        </div>
        <div class="text-right text-sm text-gray-600 dark:text-gray-300">{$currentJob.progress}%</div>
      {/if}

      {#if $currentJob.error_message}
        <div class="p-2 bg-red-100 border border-red-400 text-red-700 rounded dark:bg-red-900/30 dark:text-red-300">
          <strong>Error:</strong>&nbsp;{$currentJob.error_message}
        </div>
      {/if}

      {#if $currentJob.logs.length}
        <div>
          <h4 class="font-semibold text-gray-700 dark:text-gray-200 mb-1">Job Logs</h4>
          <div class="bg-gray-200 dark:bg-gray-600 p-3 rounded h-32 overflow-y-auto text-xs font-mono text-gray-800 dark:text-gray-100">
            {#each $currentJob.logs as entry}
              <p>{formatLogEntry(entry)}</p>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}

  {#if $currentJob.status === 'WAITING_FOR_REVIEW'}
    <ReviewDialog
      jobId={$currentJob.job_id}
      audioRelativePath={$currentJob.relative_audio_path}
      on:submit={handleReviewSubmit}
      on:cancel={handleReviewCancel} />
  {/if}
</div>
