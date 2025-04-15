// src/lib/stores.js
import { writable, readable, derived } from 'svelte/store';

// --- Check if running in a browser environment ---
// This works in plain Vite+Svelte without needing SvelteKit
const browser = typeof window !== 'undefined';

// --- Logging Helpers (Browser Only) ---
// Define log functions that only output in the browser console
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
    relative_audio_path: null // Filename only after successful upload
});

// Holds the user's current selections from the ConfigForm (used as overrides)
export const jobConfigOverrides = writable({});

// Boolean flag indicating if the initial config has been fetched from the backend
export const configLoaded = writable(false);

// Base URL for backend API calls (proxied by Vite during development)
export const apiBaseUrl = readable('/api/v1');

// Function to reset job state, e.g., before starting a new job
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

  // Avoid unnecessary DOM manipulation if class is already correct
  if (!root.classList.contains(themeToApply)) {
      root.classList.remove('light', 'dark'); // Remove any existing theme class
      root.classList.add(themeToApply);      // Add the determined theme class
      log_theme('Applied theme class to <html>:', themeToApply);
  } else {
       log_theme('Theme class already set to:', themeToApply);
  }
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
      // Fallback for invalid values
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
  // Note: Cleanup for this module-level listener isn't handled automatically by Svelte.
  // In a larger app, manage this listener lifecycle more carefully if needed.
}

// Derived store: automatically calculates the *actually applied* theme ('light' or 'dark')
// Useful for components that need to know the current effective mode, not just the preference.
export const appliedTheme = derived(themePreference, ($preference, set) => {
    if (!browser) { set('light'); return; } // SSR fallback

    const updateApplied = () => {
        const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        // If preference is 'system', use OS setting, otherwise use the explicit preference ('light' or 'dark')
        const actualTheme = $preference === 'system' ? (systemPrefersDark ? 'dark' : 'light') : $preference;
        set(actualTheme);
        log_theme('Applied theme derived store updated:', actualTheme);
    };

    updateApplied(); // Set the initial value

    // Listen to OS changes and update the derived store's value
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', updateApplied);

    // Return cleanup function for the event listener (Svelte handles this for derived stores)
    return () => {
        mediaQuery.removeEventListener('change', updateApplied);
        log_theme('Cleaned up appliedTheme media query listener.');
    };
}, 'light'); // Initial value before browser check/calculation


// --- PRESET STORE ---
// Store to hold the key of the currently selected preset ('quick', 'standard', 'multi')
export const selectedPreset = writable('standard'); // Default to 'standard' preset on load
// --- END PRESET STORE ---

// --- End of stores.js ---