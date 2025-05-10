// frontend/src/lib/stores.js

import { writable, derived, get } from 'svelte/store';

// --- 1. Browser-check & Logging Helpers -------------------------
const browser = typeof window !== 'undefined';
const logStore = (...args)   => browser && console.debug('[Store]', ...args);
const logTheme = (...args)   => browser && console.debug('[Theme]', ...args);

// --- 2. Config Info (ongewijzigd) ------------------------------
export const configInfo = writable({
  schema: {},
  available_models: [],
  detected_device: null
});

// --- 3. Job-Store met patch/reset -------------------------------
function createJobStore() {
  const initial = {
    job_id: null,
    status: null,
    progress: 0,
    logs: [],
    result: null,
    error_message: null,
    stop_requested: false,
    relative_audio_path: null
  };
  const { subscribe, set, update } = writable(initial);

  return {
    subscribe,
    // Voegt alleen de gewijzigde velden toe, behoudt de rest
    patch: partial => update(j => {
      const patched = { ...j, ...partial };
      logStore('currentJob.patch →', patched);
      return patched;
    }),
    // Zet alles terug naar de initiële staat
    reset: () => {
      logStore('currentJob.reset');
      set(initial);
    }
  };
}
export const currentJob = createJobStore();

// --- 4. Overige eenvoudige stores -------------------------------
export const jobConfigOverrides = writable({});
export const configLoaded        = writable(false);
export const apiBaseUrl          = writable('http://127.0.0.1:5000/api/v1');

// --- 5. Theme-management (light / dark / system) ---------------
function applyThemeClass(pref) {
  if (!browser) return;
  const root = document.documentElement;
  let toApply = 'light';

  if (pref === 'dark') {
    toApply = 'dark';
  } else if (pref === 'system') {
    toApply = window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
  }

  if (!root.classList.contains(toApply)) {
    root.classList.remove('light', 'dark');
    root.classList.add(toApply);
    logTheme('Applied theme →', toApply);
  } else {
    logTheme('Theme already →', toApply);
  }
}

// Bepaal initiële voorkeur (localStorage of system)
const stored = browser ? localStorage.getItem('theme') : null;
const initialTheme = (stored && ['light','dark','system'].includes(stored))
  ? stored
  : 'system';

export const themePreference = writable(initialTheme);

// Bij load & bij elke wijziging: sla op + pas class toe
if (browser) {
  applyThemeClass(initialTheme);
  themePreference.subscribe(value => {
    if (!['light','dark','system'].includes(value)) {
      logTheme('Ongeldige theme:', value, 'Reset naar system');
      value = 'system';
      themePreference.set(value);
    }
    try { localStorage.setItem('theme', value); }
    catch (e) { console.error('Kon theme niet opslaan:', e); }
    applyThemeClass(value);
  });

  // Als system-pref verandert, opnieuw toepassen (indien mode=system)
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const onSysChange = () => {
    if (get(themePreference) === 'system') {
      logTheme('System preference gewijzigd, opnieuw toepassen');
      applyThemeClass('system');
    }
  };
  mq.addEventListener('change', onSysChange);
}

// Derived store die écht toegepaste theme bijhoudt
export const appliedTheme = derived(
  themePreference,
  ($pref, set) => {
    if (!browser) { set('light'); return; }

    const update = () => {
      const sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const actual = $pref === 'system'
        ? (sysDark ? 'dark' : 'light')
        : $pref;
      set(actual);
      logTheme('Derived theme →', actual);
    };

    update();
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  },
  'light'
);

// --- 6. Preset Store (ongewijzigd) ------------------------------
export const selectedPreset = writable('standard');
