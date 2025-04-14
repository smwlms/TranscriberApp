// src/lib/stores.js
import { writable, readable, derived } from 'svelte/store';

// --- Check if running in a browser environment ---
// This works in plain Vite+Svelte without needing SvelteKit
const browser = typeof window !== 'undefined';

// --- Existing Stores ---
export const configInfo = writable({
    schema: {},
    available_models: [],
    detected_device: null // Added field for detected device
});

export const currentJob = writable({
    job_id: null, status: null, progress: 0, logs: [], result: null,
    error_message: null, stop_requested: false, relative_audio_path: null
});

export const jobConfigOverrides = writable({});
export const configLoaded = writable(false);
export const apiBaseUrl = readable('/api/v1');

export function resetCurrentJob() {
    currentJob.set({
        job_id: null, status: null, progress: 0, logs: [], result: null,
        error_message: null, stop_requested: false, relative_audio_path: null
    });
    // Don't reset overrides by default
    console.log('[Store] Current job state reset.');
}

// --- THEME STORE (Using browser check) ---

function applyTheme(theme) {
  if (!browser) return; // Guard: Only run in browser
  const root = document.documentElement;
  root.classList.remove('light', 'dark');
  log_theme('Attempting to apply theme:', theme); // Use helper log

  if (theme === 'system') {
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.classList.add(systemPrefersDark ? 'dark' : 'light');
    log_theme('Applying system theme preference:', systemPrefersDark ? 'dark' : 'light');
  } else if (theme === 'dark') {
    root.classList.add('dark');
    log_theme('Applying dark theme');
  } else {
    root.classList.add('light'); // Default to light if theme is 'light' or invalid
    log_theme('Applying light theme');
  }
}

let initialTheme = 'light'; // Default theme
if (browser) { // Guard all browser-specific logic
  try {
      const storedTheme = localStorage.getItem('theme');
      if (storedTheme && ['light', 'dark', 'system'].includes(storedTheme)) {
        initialTheme = storedTheme;
      } else {
        // If no valid theme stored, default to 'system'
        initialTheme = 'system';
        // Store 'system' as the preference if nothing was set before
        localStorage.setItem('theme', 'system');
      }
  } catch (e) {
      console.error("Error accessing localStorage for theme:", e);
      initialTheme = 'system'; // Fallback safely to system if localStorage fails
  }
}

// Writable store for theme preference ('light', 'dark', 'system')
export const theme = writable(initialTheme);

// Subscribe to theme changes ONLY in the browser
if (browser) {
    // Apply theme immediately on first load based on initial value
    applyTheme(initialTheme); // Apply initial theme class correctly

    theme.subscribe(value => {
        if (['light', 'dark', 'system'].includes(value)) {
            try {
                 localStorage.setItem('theme', value); // Persist choice
            } catch (e) {
                 console.error("Error saving theme to localStorage:", e);
            }
            applyTheme(value); // Apply class to <html> tag
        } else {
            log_theme(`Invalid theme value received: ${value}. Resetting to system.`);
            theme.set('system'); // Reset store to 'system' on invalid value
        }
    });

    // Also listen for changes in OS preference *if* the current setting is 'system'
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const systemThemeListener = (event) => {
        let currentThemeValue;
        const unsubscribe = theme.subscribe(value => { currentThemeValue = value; }); // Get current value
        unsubscribe(); // Immediately unsubscribe after getting value
        if (currentThemeValue === 'system') {
            log_theme('System color scheme changed, reapplying theme based on system.');
            applyTheme('system'); // Re-apply based on new system preference
        }
    };
    mediaQuery.addEventListener('change', systemThemeListener);

    // How to clean up this listener? Need to track it globally or use derived store approach.
    // Let's simplify for now and rely on the derived store logic below which is cleaner.
    // We might remove this specific listener if the derived store works well.
    // For now, leave it but acknowledge potential cleanup need if not using derived store for class application.
}

// Derived store to get the *actually* applied theme ('light' or 'dark')
export const appliedTheme = derived(theme, ($theme, set) => {
    if (!browser) { // Default for SSR if ever used
        set('light');
        return;
    }
    // Function to calculate and set the applied theme
    const updateApplied = () => {
        const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const actualTheme = $theme === 'system' ? (systemPrefersDark ? 'dark' : 'light') : $theme;
        set(actualTheme);
        // Apply class here instead? Could simplify the subscription logic above.
        // document.documentElement.classList.remove('light', 'dark');
        // document.documentElement.classList.add(actualTheme);
    };
    updateApplied(); // Set initial value

    // Listen to changes in the OS preference to update derived store if theme is 'system'
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', updateApplied);

    // Return cleanup function for the listener
    return () => {
        mediaQuery.removeEventListener('change', updateApplied);
    };
}, 'light'); // Initial default before hydration/calculation

// Helper log specific to theme store
function log_theme(...args) {
    console.log('[ThemeStore]', ...args);
}

// --- END THEME STORE ---