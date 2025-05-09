// frontend/src/lib/api.js

import { get } from 'svelte/store';
import { apiBaseUrl } from './stores'; // Assuming apiBaseUrl is in stores.js

// Helper to get the current base URL from the store
const getBaseUrl = () => get(apiBaseUrl);

// Helper for consistent API response handling
async function handleResponse(response) {
    // Try to parse JSON even if the response is not OK, as backend errors often include JSON details
    const data = await response.json().catch(() => ({ message: `HTTP error! Status: ${response.status}` }));

    if (!response.ok) {
        // Construct a more informative error message from backend data or HTTP status
        const errorMessage = data.error || data.message || `Request failed with status ${response.status}`;
        const error = new Error(errorMessage);
        // Attach the status and any other relevant data to the error object if needed
        error.status = response.status;
        error.data = data; // Include the parsed backend response data
        throw error;
    }

    // Return the parsed data on success
    return data;
}


// --- API Service Functions ---

/**
 * Uploads an audio file to the backend.
 * @param {File} file The file object to upload.
 * @returns {Promise<{message: string, relative_path: string}>} A promise resolving with the upload success data.
 * @throws {Error} If the upload fails.
 */
export async function uploadAudio(file) {
    if (!file) {
        throw new Error("No file provided for upload.");
    }

    const formData = new FormData();
    formData.append('audio_file', file); // 'audio_file' is the key expected by the backend

    const url = `${getBaseUrl()}/upload_audio`;
    console.log('[API] Uploading file to:', url);

    const response = await fetch(url, {
        method: 'POST',
        body: formData,
        // Note: Content-Type header is automatically set to multipart/form-data by fetch when using FormData
    });

    return handleResponse(response); // Use the helper to check response and parse JSON
}

/**
 * Starts the transcription/diarization pipeline job.
 * @param {string} relativeAudioPath The path to the uploaded audio file (relative to project root, e.g., 'audio/my_file.mp3').
 * @param {Object} configOverrides Configuration overrides for this job (simple key-value pairs).
 * @returns {Promise<{job_id: string}>} A promise resolving with the new job ID.
 * @throws {Error} If starting the pipeline fails.
 */
export async function startPipeline(relativeAudioPath, configOverrides) {
    if (!relativeAudioPath) {
        throw new Error("Audio file path is required to start the pipeline.");
    }
    if (!configOverrides || typeof configOverrides !== 'object') {
         console.warn("[API] startPipeline called without valid configOverrides object.");
         configOverrides = {}; // Default to empty object if none provided or invalid
    }

    const formData = new FormData();
    // Add the audio path - backend expects this key
    formData.append('relative_audio_path', relativeAudioPath);

    // --- FIX FOR BUG #3: Selectively add config overrides ---
    // ONLY add keys that are simple types and expected by the backend form parser.
    // A better approach might be to get the list of form-editable keys from the schema
    // received via /config_info, but for now, hardcode or get from a known list.
    // Assuming backend's parse_config_overrides_from_form expects keys like:
    // mode, whisper_model, compute_type, language, speaker_name_detection_enabled,
    // word_timestamps_enabled, pyannote_pipeline, extra_context_prompt, etc.
    // (Based on ConfigForm.svelte's excluded/included keys)

    // Define the keys that should be sent as form data overrides
    const formOverrideKeys = [
        'mode', 'whisper_model', 'compute_type', 'language',
        'speaker_name_detection_enabled', 'word_timestamps_enabled',
        'pyannote_pipeline', 'extra_context_prompt',
        // Add other simple config keys if they become form-editable
    ];

    for (const key of formOverrideKeys) {
        // Check if the key exists in overrides and the value is not null/undefined
        // Note: Svelte form bindings might result in null/undefined for empty fields
        // We want to send empty strings for text fields, and skip null/undefined for others
        const value = configOverrides[key];

        // Only append if the value is explicitly set (not undefined)
        if (value !== undefined) {
             // Convert boolean true/false to strings 'true'/'false'
             if (typeof value === 'boolean') {
                 formData.append(key, value ? 'true' : 'false');
             }
             // Convert null to empty string or skip? Backend expects empty string for auto-detect language.
             // Let's append value as string, empty string handles null/'' conversion implicitly with `${value}`
             else if (value !== null) { // Don't append null itself
                formData.append(key, `${value}`); // Append value as string
             }
             // If value is null, we simply don't append that key/value pair.
             // The backend's parse_config_overrides_from_form handles missing keys by not overriding.
        }
    }

    // Add any other *simple* overrides that might be set but not in the main formOverrideKeys list
    // This handles cases where overrides come from elsewhere (e.g., presets might set something unexpected)
    // We must be careful not to send complex objects here.
    // Let's iterate over all overrides but add a type check.
    // Alternative/Better: Get this list from the schema data loaded in App.svelte/stores.
    // For now, use the explicit list above for safety. Iterating over all keys could send unwanted data.
    // Reverted: Stick to the defined list `formOverrideKeys` for safety and clarity.
    // The keys in `formOverrideKeys` should match the simple types in schema/backend parser.


    const url = `${getBaseUrl()}/start_pipeline`;
    console.log('[API] Starting pipeline with overrides:', Object.fromEntries(formData)); // Log sent form data (careful with large data)

    const response = await fetch(url, {
        method: 'POST',
        body: formData,
    });

    return handleResponse(response);
}


/**
 * Gets the current status of a specific job.
 * @param {string} jobId The ID of the job.
 * @returns {Promise<Object>} A promise resolving with the job status data.
 * @throws {Error} If fetching status fails (e.g., job not found, API error).
 */
export async function getJobStatus(jobId) {
    if (!jobId) {
        throw new Error("Job ID is required to get status.");
    }

    const url = `${getBaseUrl()}/status/${jobId}`;
    // console.log('[API] Fetching status for job:', jobId, url); // Log every poll? Maybe too verbose.

    const response = await fetch(url, {
        method: 'GET',
    });

    return handleResponse(response);
}

/**
 * Requests to stop a running job.
 * @param {string} jobId The ID of the job to stop.
 * @returns {Promise<{message: string}>} A promise resolving with the stop request confirmation.
 * @throws {Error} If stopping the job fails.
 */
export async function stopPipeline(jobId) {
    if (!jobId) {
        throw new Error("Job ID is required to stop the pipeline.");
    }

    const url = `${getBaseUrl()}/stop_pipeline/${jobId}`;
    console.log('[API] Requesting stop for job:', jobId, url);

    const response = await fetch(url, {
        method: 'POST', // Stop is a POST request
    });

    return handleResponse(response);
}

/**
 * Gets review data (transcript, maps, context) for a job waiting for review.
 * @param {string} jobId The ID of the job.
 * @returns {Promise<Object>} A promise resolving with the review data payload.
 * @throws {Error} If fetching review data fails (e.g., job not found, not in review state, file loading error).
 */
export async function getReviewData(jobId) {
    if (!jobId) {
        throw new Error("Job ID is required to get review data.");
    }

    const url = `${getBaseUrl()}/get_review_data/${jobId}`;
    console.log('[API] Fetching review data for job:', jobId, url);

    const response = await fetch(url, {
        method: 'GET',
    });

    // Note: handleResponse will throw if response.ok is false (e.g., 404, 409, 500 from backend)
    return handleResponse(response);
}

/**
 * Submits the final speaker mapping and triggers the next pipeline stage (Part 2).
 * @param {string} jobId The ID of the job.
 * @param {Object<string, string|null>} finalSpeakerMap The final speaker map edited by the user.
 * @returns {Promise<{message: string}>} A promise resolving with the confirmation message.
 * @throws {Error} If submitting the map fails.
 */
export async function updateReviewData(jobId, finalSpeakerMap) {
    if (!jobId) {
        throw new Error("Job ID is required to update review data.");
    }
    if (!finalSpeakerMap || typeof finalSpeakerMap !== 'object') {
        throw new Error("Final speaker map object is required to update review data.");
    }

    const url = `${getBaseUrl()}/update_review_data/${jobId}`;
    console.log('[API] Submitting review data for job:', jobId, url);

    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json', // Send JSON body
        },
        body: JSON.stringify({ final_speaker_map: finalSpeakerMap }), // Backend expects this structure
    });

    return handleResponse(response);
}

/**
 * Fetches initial configuration information from the backend.
 * @returns {Promise<{schema: Object, available_models: string[], detected_device: string}>} A promise resolving with the config info.
 * @throws {Error} If fetching config info fails.
 */
export async function getConfigInfo() {
    const url = `${getBaseUrl()}/config_info`;
    console.log('[API] Fetching config info from:', url);

    const response = await fetch(url, {
        method: 'GET',
    });

    // Note: handleResponse handles error status codes and JSON parsing
    return handleResponse(response);
}