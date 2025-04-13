// src/lib/stores.js
import { writable, readable } from 'svelte/store';

// Store for configuration schema and available models fetched from backend
export const configInfo = writable({
    schema: {}, // Will hold the UI-friendly schema structure
    available_models: [] // Will hold the list of local Ollama models
});

// Store for the current job state being monitored
export const currentJob = writable({
    job_id: null,           // ID of the currently running/monitored job
    status: null,           // e.g., "QUEUED", "RUNNING", "COMPLETED", "FAILED"
    progress: 0,            // Progress percentage (0-100)
    logs: [],               // Array of log entries [timestamp, level, message]
    result: null,           // Final result data on completion
    error_message: null,    // Error message on failure
    stop_requested: false,
    // We can add other relevant fields here as needed
    relative_audio_path: null // Store path of uploaded file for starting pipeline
});

// Store for user selections in the config form
export const jobConfigOverrides = writable({}); // Store user selections here

// Simple store to track if the backend config has been loaded
export const configLoaded = writable(false);

// Store for API base URL (useful if prefix changes or for production)
// We use /api/v1 which is proxied by Vite dev server
export const apiBaseUrl = readable('/api/v1');

// Function to reset the current job state (e.g., for starting a new job)
export function resetCurrentJob() {
    currentJob.set({
        job_id: null,
        status: null,
        progress: 0,
        logs: [],
        result: null,
        error_message: null,
        stop_requested: false,
        relative_audio_path: null
    });
    jobConfigOverrides.set({}); // Also reset user selections
}