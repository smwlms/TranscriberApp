// src/lib/stores.js
import { writable, readable, derived } from 'svelte/store';

// --- Check if running in a browser environment ---
const browser = typeof window !== 'undefined';

// --- Logging Helpers (Browser Only) ---
function log_store(...args) { if (browser) { console.log('[Store]', ...args); } }
function log_theme(...args) { if (browser) { console.log('[ThemeStore]', ...args); } }

// --- Application Stores ---

// Holds configuration schema, available LLM models, and detected backend device
export const configInfo = writable({
    schema: {},
    available_models: [],
    detected_device: null // 'mps', 'cuda', 'cpu', 'error', or 'unknown'
});

// Holds the state of the currently active or last run job
export const currentJob = writable({
    job_id: null,
    status: null,
    progress: 0,
    logs: [],           // Array of [timestamp, level, message]
    result: null,       // Object containing results on completion
    error_message: null,
    stop_requested: false,
    relative_audio_path: null // Filename after successful upload
});

// Holds the user's current selections from the ConfigForm
export const jobConfigOverrides = writable({});

// Boolean flag indicating if the initial config has been fetched from the backend
export const configLoaded = writable(false);

// Base URL for backend API calls (proxied by Vite during development)
export const apiBaseUrl = readable('/api/v1');

// Function to reset the job state, e.g., before starting a new job
export function resetCurrentJob() {
    currentJob.set({
        job_id: null, status: null, progress: 0, logs: [], result: null,
        error_message: null, stop_requested: false, relative_audio_path: null
    });
    // Keep jobConfigOverrides as is, user might want to reuse settings
    log_store('Current job state reset.');
}

// --- THEME MANAGEMENT STORE ---

// Helper function to apply the correct class ('light' or 'dark') to the <html> element
function applyThemeClass(themePreferenceValue) {
  if (!browser) return; // Only run in the browser
  const root = document.documentElement;
  let themeToApply = 'light'; // Default theme

  if (themePreferenceValue === 'dark') {
    themeToApply = 'dark';
  } else if (themePreferenceValue === 'system') {
    // Check the OS/browser preference if 'system' is selected
    themeToApply = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  // Else: themePreferenceValue is 'light' or invalid, applies 'light'

  root.classList.remove('light', 'dark'); // Remove any existing theme class
  root.classList.add(themeToApply);      // Add the determined theme class
  log_theme('Applied theme class to <html>:', themeToApply);
}

// Determine the initial theme preference on load
let initialUserThemePreference = 'system'; // Default to 'system'
if (browser) {
  try {
    const storedTheme = localStorage.getItem('theme');
    // Use stored theme only if it's one of the valid options
    if (storedTheme && ['light', 'dark', 'system'].includes(storedTheme)) {
      initialUserThemePreference = storedTheme;
    } else {
      // If no valid theme stored, set preference to 'system' and store it
      localStorage.setItem('theme', 'system');
    }
  } catch (e) {
    console.error("Error accessing localStorage for theme, defaulting to 'system'.", e);
    initialUserThemePreference = 'system'; // Fallback safely
  }
}

// Writable store holding the user's *selected* preference ('light', 'dark', 'system')
export const themePreference = writable(initialUserThemePreference);

// Subscribe to changes in the user's preference store (runs only in browser)
if (browser) {
  // Apply the theme class immediately when the app loads based on initial preference
  applyThemeClass(initialUserThemePreference);

  // Whenever the themePreference store changes...
  themePreference.subscribe(value => {
    if (['light', 'dark', 'system'].includes(value)) {
        try {
            localStorage.setItem('theme', value); // ...save the new preference to localStorage...
        } catch (e) {
             console.error("Error saving theme preference to localStorage:", e);
        }
        applyThemeClass(value); // ...and apply the corresponding CSS class.
    } else {
      // Handle potential invalid value by resetting
      log_theme(`Invalid theme preference value: ${value}. Resetting to 'system'.`);
      themePreference.set('system');
    }
  });

  // Listen for changes in the OS's color scheme preference
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  const systemThemeListener = (event) => {
    let currentPreference;
    const unsubscribe = themePreference.subscribe(v => { currentPreference = v; }); // Get current stored preference
    unsubscribe();
    // If the user preference is 'system', re-apply the theme class based on the new OS state
    if (currentPreference === 'system') {
        log_theme('System color scheme changed by OS, reapplying theme class.');
        applyThemeClass('system');
    }
  };
  mediaQuery.addEventListener('change', systemThemeListener);
  // Note: Removing this listener on module unload isn't straightforward in plain JS modules.
  // The derived store approach below is generally cleaner for reacting to OS changes.
}

// Derived store: automatically calculates the *actually applied* theme ('light' or 'dark')
export const appliedTheme = derived(themePreference, ($preference, set) => {
    if (!browser) { set('light'); return; } // SSR fallback

    const updateApplied = () => {
        const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        // If preference is 'system', use OS setting, otherwise use the explicit preference
        set($preference === 'system' ? (systemPrefersDark ? 'dark' : 'light') : $preference);
    };

    updateApplied(); // Set the initial value

    // Listen to OS changes and update the derived store's value
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', updateApplied);

    // Return cleanup function for the event listener
    return () => {
        mediaQuery.removeEventListener('change', updateApplied);
    };
}, 'light'); // Initial value before browser check/calculation

// --- !! NEW PRESET STORE !! ---
// Store to hold the key of the currently selected preset ('warp', 'balanced', 'deepdive')
export const selectedPreset = writable('balanced'); // Default to 'balanced' preset on load
// --- END PRESET STORE ---