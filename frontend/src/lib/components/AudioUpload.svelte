<script>
    // Script part remains the same
    import { currentJob, apiBaseUrl, resetCurrentJob } from '../stores.js';
    import { onDestroy } from 'svelte';
    let selectedFile = null; let uploadStatus = 'idle'; let statusMessage = ''; let uploadedFilePath = null;
    let baseUrl;
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => { baseUrl = value; });
    function handleFileSelect(event) { selectedFile = event.target.files[0]; uploadStatus = 'idle'; statusMessage = selectedFile ? `Selected: ${selectedFile.name}` : ''; uploadedFilePath = null; if ($currentJob.status && $currentJob.status !== 'QUEUED') { resetCurrentJob(); log('Job state reset.'); } }
    async function handleUpload() { if (!selectedFile) { statusMessage = 'Please select audio.'; uploadStatus = 'error'; return; } uploadStatus = 'uploading'; statusMessage = 'Uploading...'; uploadedFilePath = null; const formData = new FormData(); formData.append('audio_file', selectedFile); try { const response = await fetch(`${baseUrl}/upload_audio`, { method: 'POST', body: formData }); const data = await response.json(); if (!response.ok) { throw new Error(data.error || `HTTP error ${response.status}`); } const filenameOnly = data.relative_path.includes('/') ? data.relative_path.substring(data.relative_path.lastIndexOf('/') + 1) : data.relative_path; uploadedFilePath = filenameOnly; currentJob.update(job => ({ ...job, relative_audio_path: filenameOnly, status: null, progress: 0, logs: [], result: null, error_message: null })); uploadStatus = 'success'; statusMessage = `✅ Upload successful: ${selectedFile.name}`; log('File uploaded, filename stored:', uploadedFilePath); } catch (error) { console.error('Upload failed:', error); uploadStatus = 'error'; statusMessage = `❌ Upload failed: ${error.message}`; currentJob.update(job => ({ ...job, relative_audio_path: null })); } }
    onDestroy(() => { unsubscribeApiBase(); }); function log(...args) { console.log('[AudioUpload]', ...args); }
</script>

<div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md transition-colors duration-150">
  <h2 class="text-xl font-semibold mb-4 text-gray-700 dark:text-gray-200">1. Upload Audio File</h2>
  <div class="flex flex-col sm:flex-row items-center gap-4">
    <input
      type="file"
      accept="audio/*,.m4a,.ogg,.opus"
      on:change={handleFileSelect}
      class="block w-full text-sm text-gray-500 dark:text-gray-400
             file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0
             file:text-sm file:font-semibold
             file:bg-indigo-50 dark:file:bg-indigo-900/50 dark:file:hover:bg-indigo-800/60 file:text-indigo-700 dark:file:text-indigo-300
             hover:file:bg-indigo-100
             disabled:opacity-50 disabled:pointer-events-none cursor-pointer"
      disabled={uploadStatus === 'uploading'}
    />
    <button
      on:click={handleUpload}
      disabled={!selectedFile || uploadStatus === 'uploading'}
      class="px-5 py-2 bg-indigo-600 text-white rounded-md shadow-sm hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
    >
      {#if uploadStatus === 'uploading'} Uploading... {:else} Upload File {/if}
    </button>
  </div>

  {#if statusMessage}
    <p class="mt-4 text-sm
      {uploadStatus === 'success' ? 'text-green-600 dark:text-green-400' : ''}
      {uploadStatus === 'error' ? 'text-red-600 dark:text-red-400' : ''}
      {uploadStatus === 'uploading' ? 'text-blue-600 dark:text-blue-400' : ''}
      {uploadStatus === 'idle' && selectedFile ? 'text-gray-600 dark:text-gray-400' : ''}"
    >
      {statusMessage}
    </p>
  {/if}
</div>
<style>/* Optional styles */</style>