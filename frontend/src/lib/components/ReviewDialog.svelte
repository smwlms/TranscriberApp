<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store'; // CORRECTED IMPORT
  import { apiBaseUrl } from '../stores.js';
  import {
    getReviewData as apiGetReviewData,
    updateTranscriptData,
    reDetectNames
  } from '../api.js';

  export let jobId;
  export let audioRelativePath;

  const dispatch = createEventDispatcher();

  let isLoading = true;
  let isSaving = false;
  let error = '';

  let transcript = [];
  let proposedMap = {};
  let contextSnippets = {};
  let nameEvidence = {};
  let contextNamesDetected = [];
  let extraContext = '';
  let uniqueSpeakers = [];
  let editedMap = {};
  let contextVisible = {};
  let whyVisible = {};
  let greetingCache = [];
  let rolesHint = {};
  let firstSpeakerId = null;

  // --- Speaker assist features ---
  let expectedSpeakers = 2; // adjustable in UI
  let isAssigningSpeakers = false;
  let hasSpeakerAssignmentChanges = false;
  let speakerCounts = {}; // { sid: count of segments }
  let speakerIndexMap = {}; // { sid: [segment indices] }
  let speakerNavPos = {}; // { sid: pointer }
  const SPEAKER_COLORS = ['#93c5fd','#fca5a5','#86efac','#fcd34d','#f9a8d4','#a7f3d0','#fbbf24','#c4b5fd','#fda4af','#99f6e4'];
  function colorForSpeaker(sid){ const idx = uniqueSpeakers.indexOf(sid); return SPEAKER_COLORS[(idx>=0?idx:0)%SPEAKER_COLORS.length]; }

  // Consolidation hints state
  let consolidationHints = [];

  let isEditingTranscript = false;
  let editedTranscript = {};
  let transcriptContainer; // scroll control when toggling editor

  let audioPlayer;
  let currentWordId = null;

  onMount(async () => {
    await fetchReviewData();
  });

  onDestroy(() => {
    if (audioPlayer && !audioPlayer.paused) {
      audioPlayer.pause();
    }
  });

  async function fetchReviewData() {
    isLoading = true;
    isSaving = false;
    error = '';
    try {
      const data = await apiGetReviewData(jobId);
      transcript = data.intermediate_transcript || [];
      proposedMap = data.proposed_map || {};
      contextSnippets = data.context_snippets || {};
      nameEvidence = data.name_evidence || {};
      contextNamesDetected = data.context_names_detected || [];
      extraContext = data.extra_context || '';
      rolesHint = data.roles_hint || {};
      firstSpeakerId = data.first_speaker_id || null;
      uniqueSpeakers = Array.from(new Set(transcript.map((s) => s.speaker))).sort();
      // Initialize counts and navigation helpers
      rebuildSpeakerStats();
      if (!Number.isInteger(expectedSpeakers) || expectedSpeakers < 1) expectedSpeakers = 2;

      const initialEditedMap = {};
      const initialContextVisible = {};
      const initialWhyVisible = {};
      uniqueSpeakers.forEach((id) => {
        initialEditedMap[id] = proposedMap[id]?.name ?? '';
        initialContextVisible[id] = false;
        initialWhyVisible[id] = false;
      });
      
      // Fallback: if no LLM suggestion, try extracting names from greetings
      greetingCache = greetingMatches();
      greetingCache.forEach(({ speaker, name }) => {
        if (!initialEditedMap[speaker] && isLikelyName(name)) {
          initialEditedMap[speaker] = name;
        }
      });
      editedMap = initialEditedMap;
      contextVisible = initialContextVisible;
      whyVisible = initialWhyVisible;

    } catch (e) {
      console.error('[ReviewDialog] Fetch review data failed:', e);
      error = `Fout bij laden review data: ${e.message}`;
    } finally {
      isLoading = false;
    }
  }

  function toggleContext(speakerId) {
    contextVisible[speakerId] = !contextVisible[speakerId];
  }

  function assignNameToSpeaker(name, speakerId){
    if(!name || !speakerId) return;
    editedMap[speakerId] = name;
    whyVisible[speakerId] = true;
  }

  function swapNames() {
    // Simple 2-speaker swap helper. If more, swap the first two.
    const ids = uniqueSpeakers.slice(0, 2);
    if (ids.length < 2) return;
    const a = ids[0], b = ids[1];
    const tmp = editedMap[a];
    editedMap[a] = editedMap[b];
    editedMap[b] = tmp;
  }

  function rebuildSpeakerStats(){
    const counts = {}; const idxMap = {}; const nav = {};
    (transcript||[]).forEach((seg, i)=>{
      const sid = seg?.speaker; if(!sid) return;
      counts[sid] = (counts[sid]||0)+1;
      (idxMap[sid]||(idxMap[sid]=[])).push(i);
    });
    uniqueSpeakers = Object.keys(counts).sort();
    uniqueSpeakers.forEach(s=>{ if(nav[s]===undefined) nav[s]=0; });
    speakerCounts = counts; speakerIndexMap = idxMap; speakerNavPos = { ...speakerNavPos, ...nav };
    computeConsolidationHints();
  }

  function scrollToNextFor(sid){
    const list = speakerIndexMap[sid]||[]; if(!list.length) return;
    speakerNavPos[sid] = (speakerNavPos[sid]||0) % list.length;
    const i = list[speakerNavPos[sid]]; speakerNavPos[sid] = (speakerNavPos[sid]+1)%list.length;
    const el = document.getElementById(`seg-${i}`);
    el?.scrollIntoView({behavior:'smooth', block:'start'});
  }

  function toggleAssignSpeakers(){ isAssigningSpeakers = !isAssigningSpeakers; }

  function setSegmentSpeaker(i, newSid){
    const old = transcript[i]?.speaker; if(old === newSid) return;
    transcript[i].speaker = newSid;
    hasSpeakerAssignmentChanges = true;
    rebuildSpeakerStats();
  }

  function consolidateToExpected(){
    const n = Math.max(1, parseInt(expectedSpeakers||2,10));
    const counts = {};
    transcript.forEach(s=>{ if(s?.speaker) counts[s.speaker]=(counts[s.speaker]||0)+1; });
    const sorted = Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([sid])=>sid);
    const keep = new Set(sorted.slice(0,n));
    const kept = Array.from(keep);
    const windowK = 2;
    for (let i=0;i<transcript.length;i++){
      const sid = transcript[i]?.speaker; if(!sid || keep.has(sid)) continue;
      const votes = new Map();
      for (let d=1; d<=windowK; d++){
        const left = transcript[i-d]; const right = transcript[i+d];
        if(left?.speaker && keep.has(left.speaker)) votes.set(left.speaker, (votes.get(left.speaker)||0) + (windowK-d+1));
        if(right?.speaker && keep.has(right.speaker)) votes.set(right.speaker, (votes.get(right.speaker)||0) + (windowK-d+1));
      }
      let chosen = kept[0]; let best=-1;
      for (const k of kept){ const v = votes.get(k)||0; if(v>best){ best=v; chosen=k; } }
      transcript[i].speaker = chosen;
    }
    hasSpeakerAssignmentChanges = true;
    rebuildSpeakerStats();
  }

  function computeConsolidationHints(){
    const n = Math.max(1, parseInt(expectedSpeakers||2,10));
    const counts = {}; transcript.forEach(s=>{ if(s?.speaker) counts[s.speaker]=(counts[s.speaker]||0)+1; });
    const sorted = Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([sid])=>sid);
    const keep = new Set(sorted.slice(0,n));
    const kept = Array.from(keep);
    const windowK = 2; const hintsMap = new Map();
    for (let i=0;i<transcript.length;i++){
      const sid = transcript[i]?.speaker; if(!sid || keep.has(sid)) continue;
      const votes = new Map();
      for (let d=1; d<=windowK; d++){
        const l = transcript[i-d]; const r = transcript[i+d];
        if(l?.speaker && keep.has(l.speaker)) votes.set(l.speaker, (votes.get(l.speaker)||0)+(windowK-d+1));
        if(r?.speaker && keep.has(r.speaker)) votes.set(r.speaker, (votes.get(r.speaker)||0)+(windowK-d+1));
      }
      let chosen = kept[0]; let best=-1; let total=0;
      for (const k of kept){ const v=votes.get(k)||0; total+=v; if(v>best){best=v; chosen=k;} }
      const conf = total>0 ? best/total : 0.5;
      const key = `${sid}=>${chosen}`;
      if(!hintsMap.has(key)) hintsMap.set(key,{fromSid:sid,toSid:chosen,indices:[],sum:0,count:0});
      const h = hintsMap.get(key); h.indices.push(i); h.sum+=conf; h.count+=1;
    }
    consolidationHints = Array.from(hintsMap.values()).map(h=>({
      fromSid:h.fromSid, toSid:h.toSid, indices:h.indices, count:h.count, avgConfidence: h.count? (h.sum/h.count):0
    })).sort((a,b)=>b.count-a.count);
  }

  function applyHint(h){
    if(!h || !Array.isArray(h.indices)) return;
    h.indices.forEach(i=>{ if(transcript[i]) transcript[i].speaker = h.toSid; });
    hasSpeakerAssignmentChanges = true;
    rebuildSpeakerStats();
    computeConsolidationHints();
  }

  const iconSize = 14;
  const iconColor = '#60a5fa';
  function PhoneOutgoing(){return `<svg width='${iconSize}' height='${iconSize}' viewBox='0 0 24 24' fill='none' xmlns='http://www.w3.org/2000/svg'><path d='M21 16.5v3a2 2 0 0 1-2.18 2 19.86 19.86 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.86 19.86 0 0 1 1.5 3.18 2 2 0 0 1 3.5 1h3a2 2 0 0 1 2 1.72c.12.86.33 1.7.62 2.5a2 2 0 0 1-.45 2.11L7.1 8.9a16 16 0 0 0 6 6l1.57-1.57a2 2 0 0 1 2.11-.45c.8.29 1.64.5 2.5.62A2 2 0 0 1 21 16.5z' stroke='${iconColor}' stroke-width='1.5'/></svg>`}
  function PhoneIncoming(){return `<svg width='${iconSize}' height='${iconSize}' viewBox='0 0 24 24' fill='none' xmlns='http://www.w3.org/2000/svg'><path d='M3 7.5v-3A2 2 0 0 1 5.18 2a19.86 19.86 0 0 1 8.63 3.07 19.5 19.5 0 0 1 6 6A19.86 19.86 0 0 1 22.5 20.82 2 2 0 0 1 20.5 23h-3a2 2 0 0 1-2-1.72 13 13 0 0 1-.62-2.5 2 2 0 0 1 .45-2.11l1.57-1.57a16 16 0 0 1-6-6L8.9 7.1a2 2 0 0 1-2.11-.45 13 13 0 0 1-2.5-.62A2 2 0 0 1 3 7.5z' stroke='${iconColor}' stroke-width='1.5'/></svg>`}
  function normalized(s){return (s||'').toString().trim().toLowerCase();}
  function roleForSpeaker(sid){
    const name = normalized(editedMap[sid] || proposedMap[sid]?.name);
    const caller = normalized(rolesHint.caller);
    const callee = normalized(rolesHint.callee);
    if (name && caller && name === caller) return 'caller';
    if (name && callee && name === callee) return 'callee';
    if (!name && firstSpeakerId && sid === firstSpeakerId && (caller || callee)) return 'caller?';
    return null;
  }

  function getRelevantContext(speakerId) {
    const reasoningIndices = proposedMap[speakerId]?.reasoning_indices || [];
    if (!reasoningIndices.length) return 'Geen context beschikbaar.';
    return reasoningIndices
      .map((i) => contextSnippets[String(i)] ?? `(Snippet ${i} niet gevonden)`)
      .join('\n–––\n');
  }

  function isNameToken(word){
    if (!word || !contextNamesDetected || !contextNamesDetected.length) return false;
    const w = (word||'').toString().replace(/[^A-Za-zÀ-ÖØ-öø-ÿ\-']/g,'').toLowerCase();
    return contextNamesDetected.some(n=>n && n.toLowerCase() === w);
  }

  const STOP_NAMES = new Set(['van','wel','ja','nee','u','uw','de','het','een','oke','oké','ok','goed','dag','hallo','hoi','hey','bedankt','thanks','als','dat','dit','eh','euh','uh','uhm','hm','meneer','mevrouw','sir','madam','beste','goedemiddag','goedenavond','goedemorgen','kun','kan','kunt']);
  function isLikelyName(s){
    if (!s) return false; const t = normalized(s);
    if (!t || STOP_NAMES.has(t)) return false;
    return /^[a-zà-öø-ÿ][a-zà-öø-ÿ\-']{1,}$/i.test(t);
  }
  function greetingMatches() {
    const re = /^(?:ja|hallo|hoi|hey|dag|goedemiddag|goedenavond|goedemorgen|goeiemorgen|goeiemiddag)[,\s]+([A-Z][\w\-]+)/i;
    const matches = [];
    const N = Math.min(8, transcript.length);
    for (let i=0;i<N;i++){
      const seg = transcript[i];
      const txt = (seg?.text||'').trim();
      const m = txt && txt.match(re);
      if (m) matches.push({index:i,speaker:seg?.speaker,name:m[1]});
    }
    return matches;
  }
  function whyFor(sid){
    const lines = [];
    const name = editedMap[sid] || proposedMap[sid]?.name || '';
    if (!isLikelyName(name)) lines.push(`Waarschuwing: '${name||'(leeg)'}' lijkt geen geldige naam.`);
    if (rolesHint?.caller) lines.push(`Context: caller = ${rolesHint.caller}`);
    if (rolesHint?.callee) lines.push(`Context: callee = ${rolesHint.callee}`);
    const role = roleForSpeaker(sid);
    if (role) lines.push(`Rol-hint: deze spreker is '${role}'.`);
    if (greetingCache.length){
      const relevant = greetingCache.map(g=>`[Index ${g.index}] ${g.speaker} begroet '${g.name}' → toegewezen aan andere spreker`).join('\n');
      lines.push('Begroetingspatronen:\n'+relevant);
    }
    const ri = proposedMap[sid]?.reasoning_indices || [];
    if (ri.length){
      const parts = ri.map(i=>contextSnippets[String(i)]||`(snippet ${i} ontbreekt)`).join('\n---\n');
      lines.push('LLM‑context:\n'+parts);
    }
    return lines.join('\n\n');
  }

  function toggleEditTranscript() {
    if (!isEditingTranscript) {
      const tempEditedTranscript = {};
      transcript.forEach((segment, index) => {
        tempEditedTranscript[index] = segment.text;
      });
      editedTranscript = tempEditedTranscript;
    }
    isEditingTranscript = !isEditingTranscript;
    error = '';
    // Scroll editor container to top so user doesn't land at bottom
    try { transcriptContainer && (transcriptContainer.scrollTop = 0); } catch {}
  }

  async function saveTranscriptEdits() {
    isLoading = true;
    error = '';
    try {
      const updatedFullTranscript = transcript.map((segment, index) => ({
        ...segment,
        text: editedTranscript[index] ?? segment.text,
        words: [],
      }));
      // Detect if any of the first N segments changed
      const N = Math.min(8, transcript.length);
      let firstNChanged = false;
      for (let i = 0; i < N; i++) {
        const before = transcript[i]?.text ?? '';
        const after = editedTranscript[i] ?? transcript[i]?.text ?? '';
        if (typeof before === 'string' && typeof after === 'string' && before !== after) {
          firstNChanged = true; break;
        }
      }
      await updateTranscriptData(jobId, updatedFullTranscript);
      transcript = updatedFullTranscript;
      greetingCache = greetingMatches();
      isEditingTranscript = false;
      // If early segments changed, re-run name detection to refresh suggestions
      if (firstNChanged) {
        try {
          const resp = await reDetectNames(jobId);
          if (resp && resp.proposed_map) {
            proposedMap = resp.proposed_map || {};
            contextSnippets = resp.context_snippets || {};
            // Prefill editedMap only where still empty
            Object.keys(proposedMap).forEach((id) => {
              if (!editedMap[id]) editedMap[id] = proposedMap[id]?.name ?? '';
            });
          }
        } catch (e) {
          console.warn('[ReviewDialog] reDetectNames failed:', e);
        }
      }
      console.log('[ReviewDialog] Transcript updated successfully.');
    } catch (e) {
      console.error('[ReviewDialog] Save transcript failed:', e);
      error = `Fout bij opslaan transcriptie: ${e.message}`;
      throw e;
    } finally {
      isLoading = false;
    }
  }

  async function saveSpeakerAssignmentsIfNeeded(){
    if (!hasSpeakerAssignmentChanges) return;
    isLoading = true;
    try{
      await updateTranscriptData(jobId, transcript);
      hasSpeakerAssignmentChanges = false;
      rebuildSpeakerStats();
      try {
        const resp = await reDetectNames(jobId);
        if (resp && resp.proposed_map) {
          proposedMap = resp.proposed_map || {};
          contextSnippets = resp.context_snippets || {};
          Object.keys(proposedMap).forEach((id) => { if (!editedMap[id]) editedMap[id] = proposedMap[id]?.name ?? ''; });
        }
      } catch {}
    } catch(e){
      console.error('[ReviewDialog] Save speaker assignments failed:', e);
      error = `Fout bij opslaan speaker toewijzingen: ${e.message}`;
    } finally { isLoading = false; }
  }

  async function saveAll() {
    if (isSaving) return;
    isSaving = true;
    error = '';
    try {
      if (hasSpeakerAssignmentChanges) {
        await saveSpeakerAssignmentsIfNeeded();
      }
      if (isEditingTranscript && Object.keys(editedTranscript).length) {
        console.log('[ReviewDialog] Transcript is being edited, saving transcript first...');
        await saveTranscriptEdits();
      }
      console.log('[ReviewDialog] Dispatching final speaker map to parent:', editedMap);
      dispatch('submit', editedMap);
    } catch (e) {
      console.error('[ReviewDialog] saveAll operation failed:', e);
      if (!error) {
        error = `Fout bij opslaan van review: ${e.message}`;
      }
    } finally {
      isSaving = false;
    }
  }

  function seekAudioTo(time) {
    if (audioPlayer && time !== undefined) {
      audioPlayer.currentTime = time;
    }
  }

  function handleWordClick(word) {
    if (word.start !== undefined) {
      seekAudioTo(word.start);
    }
  }

  function handleWordKeydown(event, word) {
    if (word.start !== undefined && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      seekAudioTo(word.start);
    }
  }

  function handleTimeUpdate() {
    if (!audioPlayer || !Array.isArray(transcript)) return;
    const currentTime = audioPlayer.currentTime;
    let foundWordId = null;

    for (let i = 0; i < transcript.length; i++) {
      const segment = transcript[i];
      if (Array.isArray(segment.words) && segment.words.length > 0) {
        for (let j = 0; j < segment.words.length; j++) {
          const word = segment.words[j];
          if (word.start !== undefined && word.end !== undefined && currentTime >= word.start && currentTime < word.end) {
            foundWordId = `word-${i}-${j}`;
            break;
          }
        }
      }
      if (foundWordId) break;
    }

    if (foundWordId !== currentWordId) {
      currentWordId = foundWordId;
      if (foundWordId) {
        const element = document.getElementById(foundWordId);
        element?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  }

  function cancelReview() {
    dispatch('cancel');
  }

  $: audioSrc = audioRelativePath ? `${get(apiBaseUrl).replace('/api/v1', '')}/${audioRelativePath}` : null;

</script>

<div class="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
  <div class="rounded-xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl" style="background-color: rgb(var(--page)); color: rgb(var(--text)); border: 1px solid rgb(var(--border));">
    <header class="flex justify-between items-center p-4" style="border-bottom: 1px solid rgb(var(--border));">
      <div class="flex items-center gap-4">
        <h2 class="text-lg font-semibold">Speaker & Transcript Review</h2>
        <div class="flex items-center gap-2 text-sm">
          <label for="expected-speakers" class="muted">Verwacht aantal sprekers</label>
          <input id="expected-speakers" type="number" min="1" class="w-20 px-2 py-1 rounded" bind:value={expectedSpeakers}>
          <button class="btn btn-ghost text-xs px-2 py-1" on:click={consolidateToExpected} disabled={isLoading}>Consolideer</button>
          <button class="btn btn-ghost text-xs px-2 py-1" on:click={toggleAssignSpeakers} aria-pressed={isAssigningSpeakers}>{isAssigningSpeakers ? 'Stop toewijzen' : 'Wijs sprekers toe'}</button>
        </div>
      </div>
      <button on:click={cancelReview} disabled={isSaving} class="text-2xl muted hover:opacity-70 disabled:opacity-50 transition-opacity">&times;</button>
    </header>

    <main class="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
      {#if isLoading && !isSaving}
        <div class="flex justify-center items-center h-full">
          <p class="text-gray-400 text-lg">Review data laden…</p>
        </div>
      {:else if error}
        <div class="p-4 rounded border" style="border-color: rgb(239 68 68); background: rgba(239,68,68,0.08); color: rgb(127 29 29);">
          <strong class="block mb-2">Fout:</strong>
          <p class="mb-3">{error}</p>
          {#if !isSaving}
            <button on:click={fetchReviewData}
              class="btn btn-ghost text-sm">
              Opnieuw proberen
            </button>
          {/if}
        </div>
      {/if}

      {#if !isLoading || error}
        <fieldset disabled={isSaving || (isLoading && !error)} class="space-y-6">
          {#if audioSrc}
            <section>
              <audio
                bind:this={audioPlayer}
                controls
                class="w-full"
                preload="metadata"
                on:timeupdate={handleTimeUpdate}
                src={audioSrc}
              >
                Your browser does not support the audio element.
              </audio>
            </section>
          {/if}

          <section>
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-xl font-semibold">Spreker Namen Toewijzen</h3>
              <div class="flex items-center gap-2 flex-wrap">
                {#each uniqueSpeakers as sid (sid)}
                  <button type="button" class="chip" style={`color:${colorForSpeaker(sid)}; border-color:${colorForSpeaker(sid)};`} on:click={() => scrollToNextFor(sid)} title="Scroll naar volgende voorkomen">
                    {sid} · {speakerCounts[sid] || 0}
                  </button>
                {/each}
                {#if uniqueSpeakers.length === 2}
                  <button type="button" on:click={swapNames}
                    class="btn btn-ghost text-xs px-2 py-1"
                    title="Wissel namen tussen de twee sprekers">
                    ⇄ Wissel
                  </button>
                {/if}
              </div>
            </div>
            {#if extraContext}
              <div class="mb-3 text-sm">
                <div class="opacity-80">Extra context:</div>
                <div class="mt-1 p-2 rounded whitespace-pre-wrap" style="border: 1px solid rgb(var(--border)); background-color: rgb(var(--page));">{extraContext}</div>
                {#if contextNamesDetected && contextNamesDetected.length}
                  <div class="mt-2 text-xs muted">Gedetecteerde namen: {#each contextNamesDetected as nm, i}<span class="font-semibold">{nm}</span>{i<contextNamesDetected.length-1?', ':''}{/each}</div>
                {/if}
              </div>
            {/if}
            {#if consolidationHints.length}
              <div class="mb-3 text-xs space-y-2">
                {#each consolidationHints as h (`${h.fromSid}-${h.toSid}`)}
                  <div class="flex items-center gap-2 rounded px-2 py-1" style="border: 1px solid rgb(var(--border));">
                    <span class="font-mono" style={`color:${colorForSpeaker(h.fromSid)}`}>{h.fromSid}</span>
                    <span class="opacity-70">→</span>
                    <span class="font-mono" style={`color:${colorForSpeaker(h.toSid)}`}>{h.toSid}</span>
                    <span class="opacity-80">· {Math.round(h.avgConfidence*100)}% zeker · {h.count} zinnen</span>
                    <button class="btn btn-ghost text-xs px-2 py-0.5" on:click={() => { const i=h.indices[0]; const el=document.getElementById(`seg-${i}`); el?.scrollIntoView({behavior:'smooth', block:'start'}); }}>Ga naar</button>
                    <button class="btn btn-primary text-xs px-2 py-0.5" on:click={() => applyHint(h)}>Pas toe</button>
                  </div>
                {/each}
              </div>
            {/if}
            {#if uniqueSpeakers.length === 0 && !isLoading}
                <p class="text-gray-400">Geen sprekers geïdentificeerd in dit transcript.</p>
            {/if}
            <div class="space-y-4">
              {#each uniqueSpeakers as speakerId (speakerId)}
                <div class="flex flex-col sm:flex-row items-start sm:items-center space-y-2 sm:space-y-0 sm:space-x-3">
                  <label for={`speaker-name-${speakerId}`} class="w-full sm:w-32 font-mono text-sm shrink-0 flex items-center gap-2" style={`color:${colorForSpeaker(speakerId)}`}>{speakerId}:
                    {#if roleForSpeaker(speakerId) === 'caller'}
                      {@html PhoneOutgoing()}<span class="text-xs text-blue-400">caller</span>
                    {:else if roleForSpeaker(speakerId) === 'callee'}
                      {@html PhoneIncoming()}<span class="text-xs text-blue-400">callee</span>
                    {:else if roleForSpeaker(speakerId) === 'caller?'}
                      {@html PhoneOutgoing()}<span class="text-xs text-blue-400">caller?</span>
                    {/if}
                  </label>
                  <input
                    id={`speaker-name-${speakerId}`}
                    type="text"
                    bind:value={editedMap[speakerId]}
                    placeholder={proposedMap[speakerId]?.name ? `Voorgesteld: ${proposedMap[speakerId].name}` : 'Naam invoeren...'}
                    class="flex-grow p-2 rounded w-full {isLikelyName(editedMap[speakerId]) ? '' : ''}"
                  />
                  {#if proposedMap[speakerId]?.confidence !== undefined}
                    <span class="text-xs text-gray-400">{Math.round((proposedMap[speakerId].confidence||0)*100)}%</span>
                  {/if}
                  <button type="button" class="btn btn-ghost text-xs px-2 py-1" on:click={() => whyVisible[speakerId]=!whyVisible[speakerId]}>Waarom?</button>
                  {#if proposedMap[speakerId]?.reasoning_indices?.length}
                    <button
                      type="button"
                      on:click={() => toggleContext(speakerId)}
                      class="btn btn-ghost text-sm w-full sm:w-auto"
                    >
                      {#if contextVisible[speakerId]}Verberg context{:else}Toon context{/if}
                    </button>
                  {/if}
                  {#if contextNamesDetected && contextNamesDetected.length}
                    {#each contextNamesDetected as nm (nm)}
                      <button type="button" class="btn btn-ghost text-xs px-2 py-1" on:click={() => assignNameToSpeaker(nm, speakerId)}>Koppel ‘{nm}’</button>
                    {/each}
                  {/if}
                </div>
                {#if whyVisible[speakerId]}
                  <pre class="mt-2 p-2 rounded text-xs whitespace-pre-wrap" style="border: 1px solid rgb(var(--border)); background-color: rgb(var(--page));">{whyFor(speakerId)}</pre>
                {/if}
                {#if contextVisible[speakerId]}
                  <pre class="p-3 rounded text-xs overflow-auto max-h-40 custom-scrollbar whitespace-pre-wrap" style="border: 1px solid rgb(var(--border)); background-color: rgb(var(--page));">{getRelevantContext(speakerId)}</pre>
                {/if}
              {/each}
            </div>
            {#if nameEvidence?.name_mentions?.length}
              <div class="mt-4">
                <h4 class="text-lg font-semibold mb-2">Evidence</h4>
                <ul class="space-y-1 text-sm">
                  {#each nameEvidence.name_mentions as ev, ei}
                    <li>
                      <button class="underline hover:text-blue-300" type="button" on:click={() => { const el = document.getElementById(`seg-${ev.index}`); el?.scrollIntoView({behavior:'smooth', block:'start'}); }}>
                        Ga naar segment {ev.index}
                      </button>
                      <span class="opacity-70"> — {ev.snippet?.split('\n')[0] || '(snippet)'} </span>
                    </li>
                  {/each}
                </ul>
              </div>
            {/if}
          </section>

          <section>
              <div class="flex justify-between items-center mb-3">
              <h3 class="text-xl font-semibold">Transcript</h3>
              {#if transcript.length > 0}
              <button
                type="button"
                on:click={isEditingTranscript ? saveTranscriptEdits : toggleEditTranscript}
                disabled={isLoading && isEditingTranscript}
                class="btn btn-primary text-sm"
              >
                {#if isEditingTranscript}
                  {#if isLoading}Opslaan...{:else}Transcriptie Opslaan{/if}
                {:else}
                  Edit Transcriptie
                {/if}
              </button>
              {/if}
              </div>
            {#if transcript.length === 0 && !isLoading}
                <p class="text-gray-400">Geen transcript beschikbaar.</p>
            {/if}
            <div bind:this={transcriptContainer} class="p-4 rounded-lg max-h-96 overflow-y-auto text-base custom-scrollbar" style="background-color: rgb(var(--page)); color: rgb(var(--text)); border: 1px solid rgb(var(--border));">
              {#each transcript as segment, i (segment.id || i)}
                <div class="mb-4" id={`seg-${i}`} data-speaker={segment.speaker}>
                  <div class="flex items-start gap-2">
                    <strong style={`color:${colorForSpeaker(segment.speaker)}`}>{editedMap[segment.speaker] || segment.speaker}:</strong>
                    {#if isAssigningSpeakers}
                      <select class="text-xs rounded px-1 py-0.5" bind:value={segment.speaker} on:change={(e)=>setSegmentSpeaker(i, e.target.value)}>
                        {#each uniqueSpeakers as sid (sid)}
                          <option value={sid}>{sid}</option>
                        {/each}
                      </select>
                    {/if}
                  </div>
                  {#if isEditingTranscript}
                    <textarea
                      rows="3"
                      class="w-full mt-1 p-2 rounded"
                      bind:value={editedTranscript[i]}
                      aria-label={`Transcript segment ${i+1} by speaker ${editedMap[segment.speaker] || segment.speaker}`}
                    ></textarea>
                  {:else}
                    <p class="mt-1 whitespace-pre-wrap leading-relaxed transcript-text">
                      {#if Array.isArray(segment.words) && segment.words.length}
                        {#each segment.words as word, j (`word-${i}-${j}`)}
                          <span
                            id={`word-${i}-${j}`}
                            role="button"
                            tabindex={word.start !== undefined ? 0 : -1}
                            class="word-span"
                            class:namehit={isNameToken(word.word)}
                            class:highlight={currentWordId === `word-${i}-${j}`}
                            class:clickable={word.start !== undefined}
                            on:click={() => handleWordClick(word)}
                            on:keydown={(event) => handleWordKeydown(event, word)}
                            aria-label={`Woord: ${word.word}, ${word.start !== undefined ? `start op ${word.start.toFixed(2)}s` : 'tijdstip onbekend'}`}
                          >{word.word}</span>
                        {/each}
                      {:else}
                        {segment.text || '(Leeg segment)'}
                      {/if}
                    </p>
                  {/if}
                </div>
              {/each}
            </div>
          </section>
        </fieldset>
      {/if}
    </main>

    <footer class="flex justify-end items-center p-4 space-x-3" style="border-top: 1px solid rgb(var(--border));">
      <button
        on:click={cancelReview}
        disabled={isSaving}
        class="btn btn-ghost"
      >
        Annuleren
      </button>
      <button
        on:click={saveAll}
        disabled={isLoading || isSaving || (uniqueSpeakers.length === 0 && transcript.length === 0)}
        class="btn btn-primary"
      >
        {#if isSaving}Opslaan…{:else}Bevestigen &amp; Doorgaan{/if}
      </button>
    </footer>
  </div>
</div>

<style>
  .highlight {
    background-color: #2563eb; /* Tailwind's blue-600 */
    color: white;
    padding: 1px 3px;
    border-radius: 3px;
  }
  .custom-scrollbar::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #4b5563; /* Tailwind's gray-600 */
    border-radius: 4px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: #6b7280; /* Tailwind's gray-500 */
  }
  .word-span.clickable {
    cursor: pointer;
  }
  /* Avoid horizontal scroll and keep natural wrapping */
  .transcript-text { overflow-wrap: anywhere; word-break: break-word; }
  .custom-scrollbar { overflow-x: hidden; }
  .word-span { display: inline-block; margin-right: 0.25em; }
  .word-span.clickable:hover,
  .word-span.clickable:focus {
    text-decoration: underline;
    outline: 1px dashed #60a5fa; /* Tailwind's blue-400, of een andere focus indicator */
    outline-offset: 1px;
  }
  .word-span.namehit {
    background-color: rgba(34,197,94,0.2); /* green-500 alpha */
    border-radius: 3px;
  }
  .word-span:focus {
    outline: none; /* Verwijder default browser outline als we onze eigen focus style hebben */
  }
</style>
