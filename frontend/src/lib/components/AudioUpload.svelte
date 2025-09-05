<!-- frontend/src/lib/components/AudioUpload.svelte -->
<script>
  import { onDestroy } from 'svelte';
  import { currentJob } from '../stores.js';
  import { uploadAudio } from '../api.js';

  let selectedFile = null;
  let uploadStatus = 'idle';     // idle | uploading | success | error
  let statusMessage = '';        // Bericht voor gebruiker

  // Logging‐helper
  const log = (...args) => console.debug('[AudioUpload]', ...args);
  const err = (...args) => console.error('[AudioUpload]', ...args);

  // Gebruiker kiest een nieuw bestand
  function handleFileSelect(event) {
    selectedFile = event.target.files[0] || null;
    uploadStatus = 'idle';
    statusMessage = selectedFile ? `Selected: ${selectedFile.name}` : '';

    // Als er al een job stond, reset dan de volledige state
    if ($currentJob.job_id || $currentJob.status) {
      currentJob.reset();
      log('Previous job state reset due to new file selection.');
    }
  }

  // Upload de file via de API
  async function handleUpload() {
    if (!selectedFile) {
      statusMessage = 'Please select an audio file first.';
      uploadStatus = 'error';
      return;
    }

    uploadStatus = 'uploading';
    statusMessage = 'Uploading…';

    try {
      const data = await uploadAudio(selectedFile);
      const fullRelativePath = data.relative_path; // b.v. "audio/my_file.mp3"
      log('Upload successful, backend returned:', fullRelativePath);

      // Reset alles en sla alleen het nieuwe pad op
      currentJob.reset();
      currentJob.patch({ relative_audio_path: fullRelativePath });

      uploadStatus = 'success';
      statusMessage = `✅ Upload successful: ${selectedFile.name}`;
    } catch (e) {
      err('Upload failed:', e);
      uploadStatus = 'error';
      statusMessage = `❌ Upload failed: ${e.message}`;

      // Maak het pad in de store leeg
      currentJob.patch({ relative_audio_path: null });
    }
  }

  onDestroy(() => {
    // geen extra subscriptions meer
  });
</script>

<div class="surface-card">
  <h2 class="section-title">1. Upload Audio</h2>
  <p class="section-subtle mb-4">Kies een audio‑bestand en start daarna de pipeline.</p>

  <div class="flex flex-col sm:flex-row items-center gap-4">
    <input
      type="file"
      accept="audio/*,.m4a,.ogg,.opus"
      on:change={handleFileSelect}
      class="block w-full text-sm text-gray-500 dark:text-gray-400
             file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0
             file:text-sm file:font-semibold
             file:bg-indigo-50 dark:file:bg-indigo-900/50 dark:file:hover:bg-indigo-800/60
             file:text-indigo-700 dark:file:text-indigo-300
             hover:file:bg-indigo-100
             disabled:opacity-50 disabled:pointer-events-none cursor-pointer
             transition-colors duration-150"
      disabled={uploadStatus === 'uploading'}
    />

    <button on:click={handleUpload} disabled={!selectedFile || uploadStatus === 'uploading'} class="btn btn-primary whitespace-nowrap">
      {#if uploadStatus === 'uploading'}
        <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline"
             xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10"
                  stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291
                   A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3
                   7.938l3-2.647z"></path>
        </svg>
        Uploading…
      {:else}
        Upload File
      {/if}
    </button>
  </div>

  {#if statusMessage}
    <p class="mt-3 text-sm min-h-[1.25em]
      {uploadStatus === 'success' ? 'text-green-600 dark:text-green-400' : ''}
      {uploadStatus === 'error'   ? 'text-red-600 dark:text-red-400'     : ''}
      {uploadStatus === 'uploading'? 'text-blue-600 dark:text-blue-400'   : ''}
      {uploadStatus === 'idle'     && selectedFile ? 'muted' : ''}"
    >
      {statusMessage}
    </p>
  {/if}
</div>

<style>
/* Optioneel: component‐specifieke stijlen */
</style>
