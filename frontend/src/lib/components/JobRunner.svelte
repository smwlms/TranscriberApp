<script>
  import { onMount, onDestroy } from 'svelte';
  import { currentJob, jobConfigOverrides, apiBaseUrl } from '../stores.js';
  import ReviewDialog from './ReviewDialog.svelte';

  let job;
  let overrides;
  let baseUrl;
  let pollInterval;
  let isPolling = false;
  let startError = '';
  let stopError = '';

  const unsubscribeJob = currentJob.subscribe(v => (job = v));
  const unsubscribeOverrides = jobConfigOverrides.subscribe(v => (overrides = v));
  const unsubscribeBase = apiBaseUrl.subscribe(v => (baseUrl = v));

  // Lifecycle
  onMount(() => {
    if (job?.job_id && !isTerminal(job.status)) startPolling();
  });
  onDestroy(() => {
    unsubscribeJob();
    unsubscribeOverrides();
    unsubscribeBase();
    stopPolling();
  });

  // Helpers
  function isTerminal(status) {
    return ['COMPLETED', 'FAILED', 'STOPPED', 'UNKNOWN'].includes(status);
  }
  function isStoppable(status) {
    return job?.job_id
      && !isTerminal(status)
      && status !== 'QUEUED'
      && status !== 'WAITING_FOR_REVIEW';
  }

  // Polling
  async function pollStatus() {
    if (!job?.job_id) return stopPolling();
    try {
      const res = await fetch(`${baseUrl}/status/${job.job_id}`);
      if (res.status === 404) throw new Error('Job not found');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message);
      currentJob.set(data);
    } catch (e) {
      console.warn('Polling error:', e);
      stopPolling();
      currentJob.update(j => ({ ...j, status: 'UNKNOWN' }));
    }
  }
  function startPolling() {
    if (isPolling) return;
    isPolling = true;
    pollStatus();
    pollInterval = setInterval(pollStatus, 2000);
  }
  function stopPolling() {
    clearInterval(pollInterval);
    isPolling = false;
  }

  // Actions
  async function startPipeline() {
    if (!job?.relative_audio_path) {
      startError = 'Geen audio-bestand geselecteerd';
      return;
    }
    startError = '';
    stopError = '';
    const fd = new FormData();
    fd.append('relative_audio_path', job.relative_audio_path);
    Object.entries(overrides).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== '') {
        fd.append(k, `${v}`);
      }
    });
    try {
      const res = await fetch(`${baseUrl}/start_pipeline`, {
        method: 'POST',
        body: fd
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message);
      currentJob.update(j => ({
        ...j,
        job_id: data.job_id,
        status: 'QUEUED',
        progress: 0,
        logs: [],
        stop_requested: false
      }));
      startPolling();
    } catch (e) {
      startError = `Start mislukt: ${e.message}`;
    }
  }

  async function stopPipeline() {
    stopError = '';
    try {
      const res = await fetch(`${baseUrl}/stop_pipeline/${job.job_id}`, {
        method: 'POST'
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message);
      currentJob.update(j => ({
        ...j,
        stop_requested: true,
        status: j.status + ' (stopping)'
      }));
    } catch (e) {
      stopError = `Stop mislukt: ${e.message}`;
    }
  }

  // Reactive
  $: canStart = !!job?.relative_audio_path && (!job.job_id || isTerminal(job.status));
  $: canStop = isStoppable(job.status) && isPolling;
</script>

<div class="p-6 bg-gray-800 rounded-lg space-y-4">
  <h2 class="text-xl font-semibold">3. Run Pipeline &amp; View Status</h2>

  {#if startError}
    <div class="p-2 bg-red-600 text-white rounded">{startError}</div>
  {/if}
  {#if stopError}
    <div class="p-2 bg-red-600 text-white rounded">{stopError}</div>
  {/if}

  <div class="flex gap-2">
    <button
      on:click={startPipeline}
      disabled={!canStart}
      class="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 rounded text-white"
    >
      Start Pipeline
    </button>
    <button
      on:click={stopPipeline}
      disabled={!canStop}
      class="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded text-white"
    >
      Stop Pipeline
    </button>
  </div>

  {#if job?.job_id}
    <div class="mt-4 p-4 bg-gray-700 rounded space-y-2">
      <div class="flex justify-between items-center">
        <span>Status: <strong>{job.status}</strong></span>
        {#if isPolling && !isTerminal(job.status)}
          <span class="text-sm animate-pulse">Polling…</span>
        {/if}
      </div>
      {#if job.progress !== undefined}
        <div class="w-full bg-gray-600 h-2 rounded">
          <div
            class="h-full bg-blue-500 rounded transition-all"
            style="width: {job.progress}%"
          ></div>
        </div>
        <div class="text-right text-sm">{job.progress}%</div>
      {/if}
    </div>
  {/if}

  {#if job?.status === 'WAITING_FOR_REVIEW'}
    <ReviewDialog
      jobId={job.job_id}
      audioPath={job.config?.input_audio}
      on:submit={() => {}}
      on:cancel={() => {}}
    />
  {/if}
</div>
