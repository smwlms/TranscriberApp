// src/lib/stores.js
import { writable, readable } from 'svelte/store';

// Store for configuration schema, available models, and detected device
export const configInfo = writable({
    schema: {},
    available_models: [],
    detected_device: null // <-- Add field for detected device (e.g., 'mps', 'cuda', 'cpu')
});

// Store for the current job state being monitored
export const currentJob = writable({
    job_id: null,
    status: null,
    progress: 0,
    logs: [],
    result: null,
    error_message: null,
    stop_requested: false,
    relative_audio_path: null // Stores filename only after upload success
});

// Store for user selections in the config form (used as overrides)
export const jobConfigOverrides = writable({});

// Simple store to track if the initial backend config has been loaded
export const configLoaded = writable(false);

// Store for API base URL
export const apiBaseUrl = readable('/api/v1'); // Proxied by Vite dev server

// Function to reset the current job state
export function resetCurrentJob() {
    currentJob.set({
        job_id: null, status: null, progress: 0, logs: [], result: null,
        error_message: null, stop_requested: false, relative_audio_path: null
    });
    // Reset overrides? Maybe not, user might want to keep settings for next run
    // jobConfigOverrides.set({});
    console.log('[Store] Current job state reset.');
}