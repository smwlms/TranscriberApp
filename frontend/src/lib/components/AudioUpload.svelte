<script>
    import { currentJob, apiBaseUrl, resetCurrentJob } from '../stores.js'; // Import store and base URL
    import { onDestroy } from 'svelte';
  
    let selectedFile = null; // Holds the File object
    let uploadStatus = 'idle'; // idle | uploading | success | error
    let statusMessage = '';
    let uploadedFilePath = null; // Store the path returned from backend
  
    let baseUrl;
    const unsubscribeApiBase = apiBaseUrl.subscribe(value => {
      baseUrl = value;
    });
  
    function handleFileSelect(event) {
      selectedFile = event.target.files[0];
      uploadStatus = 'idle'; // Reset status if a new file is chosen
      statusMessage = selectedFile ? `Selected: ${selectedFile.name}` : '';
      uploadedFilePath = null; // Reset previous upload path
      // Also reset the job store if a new file is selected after a successful upload/run
      if ($currentJob.status && $currentJob.status !== 'QUEUED') {
          resetCurrentJob();
          log('Job state reset due to new file selection.');
      }
    }
  
    async function handleUpload() {
      if (!selectedFile) {
        statusMessage = 'Please select an audio file first.';
        uploadStatus = 'error';
        return;
      }
  
      uploadStatus = 'uploading';
      statusMessage = 'Uploading...';
      uploadedFilePath = null; // Clear previous path
  
      const formData = new FormData();
      formData.append('audio_file', selectedFile); // Key must match backend ('audio_file')
  
      try {
        const response = await fetch(`${baseUrl}/upload_audio`, {
          method: 'POST',
          body: formData,
        });
  
        const data = await response.json(); // Always try to parse JSON
  
        if (!response.ok) {
          throw new Error(data.error || `HTTP error ${response.status}`);
        }
  
        // Success! Store the relative path in our job store
        uploadedFilePath = data.relative_path;
        currentJob.update(job => ({
            ...job,
            relative_audio_path: uploadedFilePath,
            status: null, // Reset status as we just uploaded, not started pipeline yet
            progress: 0,
            logs: [],
            result: null,
            error_message: null
         }));
  
        uploadStatus = 'success';
        statusMessage = `✅ Upload successful: ${selectedFile.name}`;
        log('File uploaded, relative path stored:', uploadedFilePath);
  
      } catch (error) {
        console.error('Upload failed:', error);
        uploadStatus = 'error';
        statusMessage = `❌ Upload failed: ${error.message}`;
        currentJob.update(job => ({ ...job, relative_audio_path: null })); // Clear path on error
      }
    }
  
    // Cleanup subscription
    onDestroy(() => {
      unsubscribeApiBase();
    });
  
    // Helper log
    function log(...args) {
        console.log('[AudioUpload]', ...args);
    }
  
  </script>
  
  <div class="bg-white p-6 rounded-lg shadow-md">
    <h2 class="text-xl font-semibold mb-4 text-gray-700">1. Upload Audio File</h2>
    <div class="flex flex-col sm:flex-row items-center gap-4">
      <input
        type="file"
        accept="audio/*"
        on:change={handleFileSelect}
        class="block w-full text-sm text-gray-500
               file:mr-4 file:py-2 file:px-4
               file:rounded-full file:border-0
               file:text-sm file:font-semibold
               file:bg-indigo-50 file:text-indigo-700
               hover:file:bg-indigo-100
               disabled:opacity-50 disabled:pointer-events-none"
        disabled={uploadStatus === 'uploading'}
      />
      <button
        on:click={handleUpload}
        disabled={!selectedFile || uploadStatus === 'uploading'}
        class="px-5 py-2 bg-indigo-600 text-white rounded-md shadow-sm hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
      >
        {#if uploadStatus === 'uploading'}
          Uploading...
        {:else}
          Upload File
        {/if}
      </button>
    </div>
  
    {#if statusMessage}
      <p class="mt-4 text-sm
        {uploadStatus === 'success' ? 'text-green-600' : ''}
        {uploadStatus === 'error' ? 'text-red-600' : ''}
        {uploadStatus === 'uploading' ? 'text-blue-600' : ''}
        {uploadStatus === 'idle' && selectedFile ? 'text-gray-600' : ''}"
      >
        {statusMessage}
      </p>
    {/if}
  </div>