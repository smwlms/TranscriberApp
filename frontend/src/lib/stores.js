// src/stores.js

import { writable, readable, derived } from 'svelte/store';

// --- Check if running in a browser environment ---
const browser = typeof window !== 'undefined';

// --- Logging Helpers (Browser Only) ---
function log_store(...args) { if (browser) console.log('[Store]', ...args); }
function log_theme(...args) { if (browser) console.log('[ThemeStore]', ...args); }

// --- Application Stores ---

export const configInfo = writable({
  schema: {},
  available_models: [],
  detected_device: null
});

export const currentJob = writable({
  job_id: null,
  status: null,
  progress: 0,
  logs: [],
  result: null,
  error_message: null,
  stop_requested: false,
  relative_audio_path: null
});

export const jobConfigOverrides = writable({});
export const configLoaded = writable(false);
export const apiBaseUrl = writable('http://127.0.0.1:5000/api/v1');

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
  log_store('Current job state reset.');
}

// --- THEME MANAGEMENT STORE ---

function applyThemeClass(themePreferenceValue) {
  if (!browser) return;
  const root = document.documentElement;
  let themeToApply = 'light';

  if (themePreferenceValue === 'dark') {
    themeToApply = 'dark';
  } else if (themePreferenceValue === 'system') {
    themeToApply = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  if (!root.classList.contains(themeToApply)) {
    root.classList.remove('light', 'dark');
    root.classList.add(themeToApply);
    log_theme('Applied theme class to <html>:', themeToApply);
  } else {
    log_theme('Theme class already set to:', themeToApply);
  }
}

let initialUserThemePreference = 'system';
if (browser) {
  try {
    const storedTheme = localStorage.getItem('theme');
    if (storedTheme && ['light', 'dark', 'system'].includes(storedTheme)) {
      initialUserThemePreference = storedTheme;
    } else {
      localStorage.setItem('theme', 'system');
    }
  } catch (e) {
    console.error("Error accessing localStorage for theme, defaulting to 'system'.", e);
    initialUserThemePreference = 'system';
  }
}

export const themePreference = writable(initialUserThemePreference);

if (browser) {
  applyThemeClass(initialUserThemePreference);

  themePreference.subscribe(value => {
    if (['light', 'dark', 'system'].includes(value)) {
      try {
        localStorage.setItem('theme', value);
      } catch (e) {
        console.error("Error saving theme preference to localStorage:", e);
      }
      applyThemeClass(value);
    } else {
      log_theme(`Invalid theme preference value: ${value}. Resetting to 'system'.`);
      themePreference.set('system');
    }
  });

  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  const systemThemeListener = (event) => {
    let currentPreference;
    const unsubscribe = themePreference.subscribe(v => { currentPreference = v; });
    unsubscribe();
    if (currentPreference === 'system') {
      log_theme('System color scheme changed by OS, reapplying theme class.');
      applyThemeClass('system');
    }
  };
  mediaQuery.addEventListener('change', systemThemeListener);
}

// Derived store for the actually applied theme
export const appliedTheme = derived(
  themePreference,
  ($preference, set) => {
    if (!browser) { set('light'); return; }
    const updateApplied = () => {
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const actualTheme = $preference === 'system'
        ? (systemPrefersDark ? 'dark' : 'light')
        : $preference;
      set(actualTheme);
      log_theme('Applied theme derived store updated:', actualTheme);
    };
    updateApplied();
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', updateApplied);
    return () => mediaQuery.removeEventListener('change', updateApplied);
  },
  'light'
);

// --- PRESET STORE ---
export const selectedPreset = writable('standard');
