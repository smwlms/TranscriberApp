<!-- frontend/src/lib/components/ResultViewer.svelte -->
<script>
    export let htmlPath;
    export let summaryPath;
    import { onMount } from 'svelte';
  
    let transcriptHtml = '';
    let summaryText  = '';
  
    onMount(async () => {
      if (htmlPath) {
        try {
          const res = await fetch(htmlPath);
          transcriptHtml = await res.text();
        } catch (err) {
          transcriptHtml = `<p class="text-red-600">Kon transcript niet laden: ${err.message}</p>`;
        }
      }
      if (summaryPath) {
        try {
          const res2 = await fetch(summaryPath);
          summaryText = await res2.text();
        } catch (err) {
          summaryText = `Kon samenvatting niet laden: ${err.message}`;
        }
      }
    });
  </script>
  
  <div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md space-y-6 transition-colors duration-150">
    <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200">Transcript</h3>
    <div class="prose dark:prose-invert max-w-none">
      {@html transcriptHtml}
    </div>
  
    <h3 class="text-lg font-semibold text-gray-700 dark:text-gray-200">Samenvatting</h3>
    <pre class="bg-gray-100 dark:bg-gray-700 p-4 rounded overflow-x-auto text-sm">
  {summaryText}
    </pre>
  </div>
  