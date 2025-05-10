/* frontend/src/api.js */
import { get } from 'svelte/store';
import { apiBaseUrl } from './stores.js';

/* ─── 1. Basis URL & Fetch Helper ────────────────────────────────────────── */
function getBaseUrl() {
  return get(apiBaseUrl).replace(/\/+$/, '');
}

async function apiFetch(path, options = {}) {
  const url = `${getBaseUrl()}/${path.replace(/^\/+/, '')}`;
  console.debug(`[API] → ${options.method || 'GET'} ${url}`, options.body ?? '');
  const response = await fetch(url, options);
  return handleResponse(response, url);
}

async function handleResponse(response, url) {
  let data;
  try {
    data = await response.json();
  } catch {
    data = { message: `HTTP ${response.status} – no JSON payload` };
  }

  if (!response.ok) {
    const msg = data.error || data.message || `HTTP ${response.status}`;
    console.error(`[API] ❌ ${response.status} ${url}`, data);
    const err = new Error(msg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  console.debug(`[API] ✅ ${response.status} ${url}`, data);
  return data;
}

/* ─── 2. Endpoints ───────────────────────────────────────────────────────── */

/** Upload audio file */
export async function uploadAudio(file) {
  if (!file) throw new Error('No file provided for upload.');
  const form = new FormData();
  form.append('audio_file', file);
  return apiFetch('upload_audio', { method: 'POST', body: form });
}

/** Start transcription/diarization */
export async function startPipeline(relativeAudioPath, configOverrides = {}) {
  if (!relativeAudioPath) throw new Error('relativeAudioPath is required.');
  const form = new FormData();
  form.append('relative_audio_path', relativeAudioPath);
  [
    'mode',
    'whisper_model',
    'compute_type',
    'language',
    'speaker_name_detection_enabled',
    'word_timestamps_enabled',
    'pyannote_pipeline',
    'extra_context_prompt'
  ].forEach((key) => {
    const v = configOverrides[key];
    if (v !== undefined && v !== null)
      form.append(key, typeof v === 'boolean' ? String(v) : v);
  });
  return apiFetch('start_pipeline', { method: 'POST', body: form });
}

/** Poll job status */
export async function getJobStatus(jobId) {
  if (!jobId) throw new Error('jobId is required.');
  return apiFetch(`status/${jobId}`, { method: 'GET' });
}

/** Stop een job */
export async function stopPipeline(jobId) {
  if (!jobId) throw new Error('jobId is required.');
  return apiFetch(`stop_pipeline/${jobId}`, { method: 'POST' });
}

/** Haal de review‐payload op */
export async function getReviewData(jobId) {
  if (!jobId) throw new Error('jobId is required.');
  return apiFetch(`get_review_data/${jobId}`, { method: 'GET' });
}

/** Submit speaker‐mapping en trigger part 2 */
export async function updateReviewData(jobId, finalSpeakerMap) {
  if (!jobId) throw new Error('jobId is required.');
  if (typeof finalSpeakerMap !== 'object')
    throw new Error('finalSpeakerMap moet een object zijn.');
  return apiFetch(`update_review_data/${jobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ final_speaker_map: finalSpeakerMap })
  });
}

/**
 * Update alléén de (eventueel bewerkte) transcriptie voor een review‐job.
 * Verstuurt body: { "transcript": [...] } – conform nieuw backend‑schema.
 */
export async function updateTranscriptData(jobId, transcript) {
  if (!jobId) throw new Error('jobId is required.');
  if (!Array.isArray(transcript))
    throw new Error('transcript moet een array zijn.');
  console.debug('[API] ▶ updateTranscriptData payload', { transcript });
  return apiFetch(`update_transcript_data/${jobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript })
  });
}

/** Ophalen config */
export async function getConfigInfo() {
  return apiFetch('config_info', { method: 'GET' });
}
