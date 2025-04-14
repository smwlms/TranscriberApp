<script>
    // Use the CORRECT store name 'theme'
    import { theme } from '../stores.js';
  
    // Function to update the theme store
    function setTheme(newTheme) {
      $theme = newTheme; // Use correct store variable ($theme)
    }
  
    // --- Tailwind Classes ---
    const baseButtonClasses = "p-1.5 rounded-md transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-indigo-500 dark:focus:ring-offset-gray-800 inline-flex items-center gap-1";
    const inactiveButtonClasses = "text-gray-500 hover:bg-gray-200 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200";
    const activeButtonClasses = "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-400";
  
  </script>
  
  <div class="flex items-center space-x-1 border border-gray-300 dark:border-gray-600 p-0.5 rounded-lg bg-white dark:bg-gray-700/50 shadow-sm">
  
    <button
      type="button"
      title="Set Light Theme"
      aria-label="Set Light Theme"
      aria-pressed={$theme === 'light'}
      class="{baseButtonClasses}"
      class:activeButtonClass={$theme === 'light'}
      class:inactiveButtonClass={$theme !== 'light'}
      on:click={() => setTheme('light')}
    >
      <span class="sr-only">Light Theme</span>
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" /></svg>
    </button>
  
    <button
      type="button"
      title="Set Dark Theme"
      aria-label="Set Dark Theme"
      aria-pressed={$theme === 'dark'}
      class="{baseButtonClasses}"
      class:activeButtonClass={$theme === 'dark'}
      class:inactiveButtonClass={$theme !== 'dark'}
      on:click={() => setTheme('dark')}
    >
      <span class="sr-only">Dark Theme</span>
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" /></svg>
    </button>
  
    <button
      type="button"
      title="Use System Theme Preference"
      aria-label="Use System Theme Preference"
      aria-pressed={$theme === 'system'}
      class="{baseButtonClasses}"
      class:activeButtonClass={$theme === 'system'}
      class:inactiveButtonClass={$theme !== 'system'}
      on:click={() => setTheme('system')}
    >
      <span class="sr-only">System Theme</span>
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5"><path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 0 1-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0 1 15 18.257V17.25m6-12V15a2.25 2.25 0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 15V5.25m18 0A2.25 2.25 0 0 0 18.75 3H5.25A2.25 2.25 0 0 0 3 5.25m18 0V12a2.25 2.25 0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 12V5.25" /></svg>
    </button>
  </div>
  
  <style> /* No styles needed */ </style>