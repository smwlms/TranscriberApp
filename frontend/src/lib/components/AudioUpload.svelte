<script>
  // Import stores and the API base URL (apiBaseUrl is not strictly needed here anymore
  // as the api service uses the store internally, but keeping it for context/future logging)
  import { currentJob, apiBaseUrl, resetCurrentJob } from '../stores.js';
  import { onDestroy } from 'svelte';

  // --- Import the API service function for upload ---
  import { uploadAudio } from '../api.js';

  let selectedFile = null; // Holds the File object selected by the user
  let uploadStatus = 'idle'; // Tracks the upload process: idle | uploading | success | error
  let statusMessage = '';    // User-facing message about the upload status
  // We no longer need a local variable for uploadedFilePath, as the path goes directly into the store
  // let uploadedFilePath = null;

  // apiBaseUrl subscription is not needed in this component anymore,
  // as the uploadAudio function from api.js handles getting the base URL.
  // let baseUrl; // Holds the API base URL from the store
  // const unsubscribeApiBase = apiBaseUrl.subscribe(value => {
  //   baseUrl = value;
  // });

  // Handler for when the user selects a file using the input element
  function handleFileSelect(event) {
    selectedFile = event.target.files[0]; // Get the first selected file
    uploadStatus = 'idle'; // Reset status when a new file is chosen
    statusMessage = selectedFile ? `Selected: ${selectedFile.name}` : ''; // Update message
    // uploadedFilePath = null; // No longer needed

    // If a job was already running or completed, reset the main job store
    // because a new file implies starting a new analysis from scratch.
    // We check the store value directly using the $ prefix for auto-subscription.
    if ($currentJob.job_id || $currentJob.status) {
        resetCurrentJob(); // Call the reset function from the store
        log('Previous job state reset due to new file selection.');
    }
  }

  // Handler for when the user clicks the "Upload File" button
  async function handleUpload() {
    if (!selectedFile) {
      statusMessage = 'Please select an audio file first.';
      uploadStatus = 'error';
      return;
    }

    // Set state to 'uploading'
    uploadStatus = 'uploading';
    statusMessage = 'Uploading...';
    // uploadedFilePath = null; // No longer needed

    try {
      // --- Use the API service function for upload ---
      // Pass the file object directly to the service function
      const data = await uploadAudio(selectedFile);
      // --- Response handling is done inside uploadAudio/handleResponse ---

      // --- Success ---
      // Bug #2 Fix: Store the FULL relative_path returned by the backend
      const fullRelativePath = data.relative_path; // e.g., "audio/my_file.mp3"

      // Update the central job store with the full relative path
      currentJob.update(job => ({
          ...job,
          relative_audio_path: fullRelativePath, // <-- BUG #2 FIX: Store full relative path
          // Reset other job state fields as this is a new file upload
          status: null,
          progress: 0,
          logs: [],
          result: null,
          error_message: null,
          job_id: null // Important: Clear previous job ID
       }));

      uploadStatus = 'success'; // Update status
      statusMessage = `✅ Upload successful: ${selectedFile.name}`; // Show success message
      log('File uploaded successfully. Full relative path stored:', fullRelativePath);

    } catch (error) {
      // Handle errors thrown by uploadAudio/handleResponse
      console.error('Upload failed:', error);
      uploadStatus = 'error';
      statusMessage = `❌ Upload failed: ${error.message}`;
      // Clear the path in the store if upload fails
      currentJob.update(job => ({ ...job, relative_audio_path: null }));
    }
    // Note: We don't reset uploadStatus automatically from success/error
    // so the user sees the final status message. Selecting a new file will reset it.
  }

  // Cleanup the store subscription when the component is destroyed
  // The apiBaseUrl subscription is removed as it's not needed locally
  onDestroy(() => {
    // unsubscribeApiBase(); // Removed
  });

  // Simple logging helper for this component
  function log(...args) {
      if(typeof console !== 'undefined') {
         console.log('[AudioUpload]', ...args);
      }
  }

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
           file:bg-indigo-50 dark:file:bg-indigo-900/50 dark:file:hover:bg-indigo-800/60
           file:text-indigo-700 dark:file:text-indigo-300
           hover:file:bg-indigo-100
           disabled:opacity-50 disabled:pointer-events-none cursor-pointer
           transition-colors duration-150"
    disabled={uploadStatus === 'uploading'}
  />
  <button
    on:click={handleUpload}
    disabled={!selectedFile || uploadStatus === 'uploading'}
    class="px-5 py-2 bg-indigo-600 text-white rounded-md shadow-sm hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap transition-colors duration-150"
  >
    {#if uploadStatus === 'uploading'}
      <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      Uploading...
    {:else}
      Upload File
    {/if}
  </button>
</div>

{#if statusMessage}
  <p class="mt-4 text-sm min-h-[1.25em]
    {uploadStatus === 'success' ? 'text-green-600 dark:text-green-400' : ''}
    {uploadStatus === 'error' ? 'text-red-600 dark:text-red-400' : ''}
    {uploadStatus === 'uploading' ? 'text-blue-600 dark:text-blue-400' : ''}
    {uploadStatus === 'idle' && selectedFile ? 'text-gray-600 dark:text-gray-400' : ''}"
  >
    {statusMessage}
  </p>
{/if}
</div>

<style>/* Optional component-specific styles */</style>