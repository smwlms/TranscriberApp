<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { get } from 'svelte/store';
  import { apiBaseUrl } from '../stores.js';

  export let transcript = [];
  export let audioRelativePath = '';
  export let preRollMs = 150; // configurable pre-roll (ms), clamped >= 0
  export let offsetMs = 0;    // global drift offset (ms), can be +/-
  export let speakerNames = {};
  export let speakerColors = {};
  export let speakerIds = [];
  export let contextSpeakers = [];
  export let contextTerms = [];
  export let audioElement = null;

  const dispatch = createEventDispatcher();

  let audioEl;
  let rafId = null;
  let mounted = false;
  let currentFlatIndex = -1; // index in flat words
  let activeWordId = null;
  let scrollDebounce = null;
  let followPlayback = true; // user can disable auto-follow while scrolling
  let transcriptScrollEl; // scroll container to detect user scroll
  let playUntil = null; // if set, pause when time >= playUntil
  let _contextFingerprint = '';

  // Derived structures
  let sentences = []; // [{id, start, end, wordIds: []}]
  let flatWords = []; // [{ id, i, j, text, start, end, sentId, corrected?, flags?, speaker? }]
  let starts = [];    // number[]
  let ends = [];      // number[]
  let idToFlatIndex = Object.create(null);
  let bands = []; // [{start,end,speaker}]
  let showSettings = false;
  let editMode = false;
  let showTranslation = false;
  let translations = new Map(); // index -> translated string
  export let externalTranslations = null; // optional array from parent
  let isTranslating = false; // UI state for translation loading
  let _lastTranscriptRef = null; // to rebuild structures when parent updates transcript
  const dirtySentences = new Set();
  $: if (externalTranslations && Array.isArray(externalTranslations)) {
    const m = new Map();
    externalTranslations.forEach((t, i)=> m.set(i, t||''));
    translations = m;
    if (translations.size > 0) isTranslating = false;
  }

  $: audioElement = audioEl;

  // Review navigation
  let targets = [];   // indices in flatWords with corrected && !confirmed
  let targetPos = 0;

  // Telemetry
  let total = 0;
  let corrected = 0;
  let confirmed = 0;
  let pending = 0;
  let percentageConfirmed = 0;

  $: audioSrc = audioRelativePath ? `${get(apiBaseUrl).replace('/api/v1', '')}/${audioRelativePath}` : null;

  function clampPreRoll(ms){ return Math.max(0, Math.floor(ms||0)); }

  function buildStructures() {
    dirtySentences.clear();
    sentences = [];
    flatWords = [];
    starts = [];
    ends = [];
    // Build per-segment sentences; enforce half-open [start, end)
    idToFlatIndex = Object.create(null);
    for (let i = 0; i < (transcript?.length || 0); i++) {
      const seg = transcript[i] || {};
      const words = Array.isArray(seg.words) ? seg.words : [];
      const sid = `s-${i}`;
      const wordIds = [];
      let sStart = Number.isFinite(seg.start) ? seg.start : null;
      let sEnd = Number.isFinite(seg.end) ? seg.end : null;
      if (words.length) {
        sStart = Number.isFinite(words[0].start) ? words[0].start : sStart;
        const last = words[words.length - 1];
        sEnd = Number.isFinite(last.end) ? last.end : sEnd;
      }
      for (let j = 0; j < words.length; j++) {
        const w = words[j] || {};
        const id = `w-${i}-${j}`;
        const start = Number.isFinite(w.start) ? w.start : (Number.isFinite(seg.start) ? seg.start : 0);
        const end = Number.isFinite(w.end) ? w.end : start;
        const fw = {
          id, i, j, sentId: sid,
          text: w.word ?? '',
          start, end,
          corrected: w.corrected,
          flags: w.flags || {},
          speaker: seg.speaker
        };
        idToFlatIndex[id] = flatWords.length;
        flatWords.push(fw);
        starts.push(start);
        ends.push(end);
        wordIds.push(id);
      }
      sentences.push({ id: sid, start: sStart ?? 0, end: sEnd ?? (sStart ?? 0), wordIds });
    }

    // Initial suspect detection & suggestions (max 5 per sentence)
    detectSuspects();
    rebuildTargetsAndTelemetry();
    buildBands();
  }

  function detectSuspects(){
    // Simple heuristics: low score (<0.35), weird tokens, repeated chars, stray punctuation
    const bySentence = new Map();
    flatWords.forEach((w) => {
      const sid = w.sentId; if (!bySentence.has(sid)) bySentence.set(sid, []);
      const toks = bySentence.get(sid);
      const score = getWordScore(w);
      const token = (w.text||'').toString();
      const weird = /[^\p{L}\p{N}\-']/u.test(token) || /(.)\1{2,}/.test(token);
      const short = token.length <= 1;
      const filler = /^(uh|uhm|euh|hm|mmm+)$/i.test(token);
      const suspect = (!short && !filler) && ((Number.isFinite(score) && score < 0.35) || weird);
      if (suspect) toks.push(w);
    });
    // Apply up to 5 per sentence as suggestions
    for (const [sid, arr] of bySentence.entries()){
      let count = 0;
      for (const w of arr){
        if (count >= 5) break;
        if (w.corrected && w.corrected !== w.text) continue; // already suggested/edited
        const proposal = suggestReplacement(w.text);
        if (proposal && proposal !== w.text){
          w.corrected = proposal;
          w.flags = { ...(w.flags||{}), outOfContext: true, confirmed: false };
          // propagate into transcript for UI rendering
          const seg = transcript?.[w.i];
          if (seg?.words?.[w.j]){
            seg.words[w.j].corrected = w.corrected;
            seg.words[w.j].flags = w.flags;
          }
          count++;
        }
      }
    }

    applyContextHints();
  }

  function suggestReplacement(token){
    if (!token) return token;
    let s = token.toString();
    // Collapse >2 repeats to 2
    s = s.replace(/(.)\1{2,}/g, '$1$1');
    // Fix random trailing punctuation sequences like ",,", "..," -> trim to single
    s = s.replace(/[\.,;:!?]{2,}$/g, m => m[0]);
    // Normalize weird quotes
    s = s.replace(/[“”]/g, '"').replace(/[‘’]/g, "'");
    // If all caps and long, lowercase except first char
    if (/^[A-Z]{3,}$/.test(s)) s = s[0] + s.slice(1).toLowerCase();
    return s;
  }

  function normalizeToken(token){
    if (!token) return '';
    return token
      .toString()
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]/g, '');
  }

  function levenshtein(a, b){
    if (a === b) return 0;
    const m = a.length;
    const n = b.length;
    if (!m) return n;
    if (!n) return m;
    const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
    for (let i = 0; i <= m; i++) dp[i][0] = i;
    for (let j = 0; j <= n; j++) dp[0][j] = j;
    for (let i = 1; i <= m; i++){
      for (let j = 1; j <= n; j++){
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        dp[i][j] = Math.min(
          dp[i - 1][j] + 1,
          dp[i][j - 1] + 1,
          dp[i - 1][j - 1] + cost
        );
      }
    }
    return dp[m][n];
  }

  function applyContextHints(){
    if (!Array.isArray(contextTerms) || !contextTerms.length) return;
    const targets = [];
    const seen = new Set();
    contextTerms.forEach((term) => {
      if (!term || typeof term !== 'string') return;
      const trimmed = term.trim();
      if (!trimmed) return;
      const norm = normalizeToken(trimmed);
      if (!norm || norm.length < 3) return;
      if (seen.has(norm)) return;
      seen.add(norm);
      targets.push({ raw: trimmed, norm });
    });
    if (!targets.length) return;

    flatWords.forEach((w) => {
      if (!w) return;
      const original = (w.text ?? '').toString();
      const normWord = normalizeToken(original);
      if (!normWord) return;
      const originalAllLower = original === original.toLowerCase();
      if (w.flags?.manualEdit) return;
      if (w.corrected && w.corrected !== original && !w.flags?.suggestedByContext) return;

      const seg = transcript?.[w.i];
      const applySuggestion = (candidateRaw) => {
        if (!candidateRaw) return false;
        const originalLower = original === original.toLowerCase();
        const candidateLooksName = /^[A-Z][a-zÀ-ÖØ-öø-ÿ'-]*$/.test(candidateRaw);
        if (originalLower && candidateLooksName) return false;
        const adjusted = adjustSuggestionCase(original, candidateRaw);
        if (!adjusted || adjusted === original) return false;
        const withPunctuation = mergePunctuation(original, adjusted);
        if (withPunctuation === original) return false;
        w.corrected = withPunctuation;
        const updatedFlags = { ...(w.flags || {}), suggestedByContext: true, confirmed: false };
        w.flags = updatedFlags;
        if (seg?.words?.[w.j]){
          seg.words[w.j].corrected = withPunctuation;
          seg.words[w.j].flags = { ...(seg.words[w.j].flags || {}), ...updatedFlags };
        }
        return true;
      };

      const exactApplied = targets.some((target) => {
        if (normWord !== target.norm) return false;
        return applySuggestion(target.raw);
      });
      if (exactApplied) return;

      let best = null;
      for (const target of targets){
        const distance = levenshtein(normWord, target.norm);
        const maxLen = Math.max(normWord.length, target.norm.length) || 1;
        const sim = 1 - distance / maxLen;
        const closeEnough = sim >= 0.78 || (maxLen <= 4 && distance <= 1);
        if (!closeEnough) continue;
        if (originalAllLower && distance <= 1) continue;
        const adjusted = adjustSuggestionCase(original, target.raw);
        if (!adjusted || adjusted === original) continue;
        if (!best || sim > best.sim){
          best = { adjusted, sim };
        }
      }
      if (best){
        applySuggestion(best.adjusted);
      }
    });
  }

  function adjustSuggestionCase(original, suggestion){
    if (!suggestion) return suggestion;
    if (!original) return suggestion;
    if (original === original.toUpperCase()) return suggestion.toUpperCase();
    if (original === original.toLowerCase()) return suggestion.toLowerCase();
    if (/^[A-Z]/.test(original) && !/^[A-Z]/.test(suggestion)){
      return suggestion.charAt(0).toUpperCase() + suggestion.slice(1);
    }
    return suggestion;
  }

  function mergePunctuation(original, suggestion){
    if (!suggestion) return suggestion;
    const leading = original.match(/^["'“”‘’\(\[]+/);
    const trailing = original.match(/["'“”‘’\)\]\.,;:!?]+$/);
    let result = suggestion;
    if (leading) result = leading[0] + result;
    if (trailing) result = result + trailing[0];
    return result;
  }

  function getWordScore(w){
    // words may carry score from backend (probability)
    const i = w.i, j = w.j;
    const seg = transcript?.[i];
    const wordObj = seg?.words?.[j];
    const sc = wordObj?.score; // as set by backend merge
    return Number.isFinite(sc) ? sc : NaN;
  }

  function rebuildTargetsAndTelemetry(){
    targets = [];
    total = flatWords.length;
    corrected = 0;
    confirmed = 0;
    for (let idx = 0; idx < flatWords.length; idx++){
      const w = flatWords[idx];
      if (w.corrected && w.corrected !== w.text){
        corrected++;
        if (w.flags?.confirmed) confirmed++;
        else targets.push(idx);
      }
    }
    pending = Math.max(0, corrected - confirmed);
    percentageConfirmed = corrected > 0 ? Math.round((confirmed / corrected) * 100) : 0;
    if (targetPos >= targets.length) targetPos = Math.max(0, targets.length - 1);
    dispatch('changed', { corrected, confirmed, pending, dirtyIndices: Array.from(dirtySentences) });
  }

  function buildBands(){
    const tmp = [];
    for (const s of sentences){
      if (!Number.isFinite(s.start) || !Number.isFinite(s.end)) continue;
      const spk = (transcript?.[parseInt(s.id.split('-')[1])]?.speaker) || '';
      if (!spk) continue;
      const start = s.start, end = s.end;
      if (!tmp.length || tmp[tmp.length-1].speaker !== spk) tmp.push({ start, end, speaker: spk });
      else tmp[tmp.length-1].end = end;
    }
    bands = tmp;
  }

  function contextTermsKey(terms){
    if (!Array.isArray(terms) || !terms.length) return '';
    return terms
      .map((t) => normalizeToken(t))
      .filter(Boolean)
      .sort()
      .join('|');
  }

  $: if (mounted) {
    const key = contextTermsKey(contextTerms);
    if (key !== _contextFingerprint) {
      _contextFingerprint = key;
      buildStructures();
    }
  }

  function binarySearchActiveIndex(t){
    // Fuzzy matching to cope with small timestamp drifts
    const EPS = 0.02; // 20 ms tolerance
    let lo = 0, hi = starts.length - 1, ans = -1;
    while (lo <= hi){
      const mid = (lo + hi) >> 1;
      if (starts[mid] - EPS <= t){ ans = mid; lo = mid + 1; }
      else { hi = mid - 1; }
    }
    if (ans === -1) return -1;
    // If we're at the end boundary within EPS → switch to next word
    if (t >= (ends[ans] - EPS)) return Math.min(ans + 1, ends.length - 1);
    // Ensure we're inside the chosen word window (with EPS)
    if (t >= (starts[ans] - EPS) && t < (ends[ans] + EPS)) return ans;
    return -1;
  }

  function highlightIndex(idx){
    if (idx === currentFlatIndex) return;
    currentFlatIndex = idx;
    const id = idx >= 0 ? flatWords[idx]?.id ?? null : null;
    if (id !== activeWordId) {
      activeWordId = id;
      if (followPlayback && activeWordId){
        if (scrollDebounce) cancelAnimationFrame(scrollDebounce);
        scrollDebounce = requestAnimationFrame(() => {
          const el = document.getElementById(activeWordId);
          el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        });
      }
    }
  }

  function handleTimeUpdate(){
    if (!audioEl) return;
    const t = Math.max(0, audioEl.currentTime + (offsetMs || 0) / 1000);
    const idx = binarySearchActiveIndex(t);
    highlightIndex(idx);
  }

  function loop(){
    if (!mounted) return;
    const t = audioEl ? audioEl.currentTime : 0;
    const tt = Math.max(0, t + (offsetMs||0) / 1000);
    const idx = binarySearchActiveIndex(tt);
    highlightIndex(idx);
    if (playUntil != null && audioEl && t >= (playUntil - 0.02)) { audioEl.pause(); playUntil = null; }
    rafId = requestAnimationFrame(loop);
  }

  onMount(() => {
    mounted = true;
    buildStructures();
    rafId = requestAnimationFrame(loop);
  });

  onDestroy(() => {
    mounted = false;
    if (rafId) cancelAnimationFrame(rafId);
    if (scrollDebounce) cancelAnimationFrame(scrollDebounce);
    audioElement = null;
  });

  // Rebuild derived structures whenever parent updates the transcript reference
  $: if (mounted && _lastTranscriptRef !== transcript) {
    _lastTranscriptRef = transcript;
    buildStructures();
  }

  // Jumping / navigation
  function sentenceIndexOfWord(idx){
    const sid = flatWords[idx]?.sentId;
    if (!sid) return 0;
    return sentences.findIndex(s => s.id === sid) || 0;
  }

  function playFromWord(idx){
    if (!audioEl || idx < 0) return;
    const sIdx = sentenceIndexOfWord(idx);
    const prevSentence = sentences[Math.max(0, sIdx - 1)] || sentences[0];
    const start = Math.max(0, (prevSentence?.start || 0) - clampPreRoll(preRollMs)/1000);
    audioEl.currentTime = start;
    audioEl.play().catch(()=>{});
  }

  function playOnlyWord(idx){
    if (!audioEl || idx < 0) return;
    const w = flatWords[idx]; if (!w) return;
    // Determine previous and next word within same sentence (if available)
    let prev = idx - 1; let next = idx + 1;
    const sentId = w.sentId;
    while (prev >= 0 && flatWords[prev]?.sentId !== sentId) prev--;
    while (next < flatWords.length && flatWords[next]?.sentId !== sentId) next++;
    const start = Math.max(0, (flatWords[prev]?.start ?? w.start));
    const end = flatWords[next]?.end ?? w.end ?? (w.start + 0.3);
    audioEl.currentTime = start;
    playUntil = end;
    followPlayback = true;
    audioEl.play().catch(()=>{});
    highlightIndex(idx);
  }

  async function loadTranslations(apiTranslate){
    try {
      const res = await apiTranslate();
      if (res && Array.isArray(res.translations)){
        translations = new Map();
        res.translations.forEach((t, i) => { translations.set(i, t || ''); });
      }
    } catch (e) { console.warn('loadTranslations failed', e); }
  }

  function setSentenceSpeaker(sentIndex, newSid){
    if (!newSid || !transcript?.[sentIndex]) return;
    transcript[sentIndex].speaker = newSid;
    // Update flat words speaker cache for this sentence
    for (const wid of sentences[sentIndex]?.wordIds || []){
      const idx = idToFlatIndex[wid];
      if (idx !== undefined && flatWords[idx]) flatWords[idx].speaker = newSid;
    }
    buildBands();
    dispatch('changed'); // zodat parent kan saven
  }

  function jumpToTarget(pos){
    if (!targets.length) return;
    targetPos = ((pos % targets.length) + targets.length) % targets.length;
    const idx = targets[targetPos];
    playFromWord(idx);
    // Also force highlight this target to make it visible immediately
    highlightIndex(idx);
  }

  function prevTarget(){ jumpToTarget(targetPos - 1); }
  function nextTarget(){ jumpToTarget(targetPos + 1); }

  function confirmTarget(){
    if (!targets.length) return;
    const idx = targets[targetPos];
    const w = flatWords[idx];
    if (!w) return;
    // Enforce only corrected toggles; never change timing or original text
    w.flags = { ...(w.flags||{}), confirmed: true };
    // Persist back into transcript words structure (so that parent can save)
    const seg = transcript[w.i];
    if (seg?.words?.[w.j]) {
      seg.words[w.j].corrected = w.corrected;
      seg.words[w.j].flags = w.flags;
    }
    rebuildTargetsAndTelemetry();
    // Move to next pending automatically
    if (targets.length) nextTarget();
    dispatch('changed', { corrected, confirmed, pending, dirtyIndices: Array.from(dirtySentences) });
  }

  function onEditCorrected(idx, val){
    const w = flatWords[idx]; if (!w) return;
    w.corrected = val ?? '';
    // Push to transcript word
    const seg = transcript[w.i];
    if (seg?.words?.[w.j]){
      seg.words[w.j].corrected = w.corrected;
    }
    const updatedFlags = { ...(w.flags || {}) };
    updatedFlags.manualEdit = true;
    updatedFlags.confirmed = true;
    w.flags = updatedFlags;
    if (seg?.words?.[w.j]){
      seg.words[w.j].flags = { ...(seg.words[w.j].flags || {}), ...updatedFlags };
    }
    dirtySentences.add(w.i);
    rebuildTargetsAndTelemetry();
  }

  function triggerTranslation(reason, { clearDirty = false } = {}){
    isTranslating = true;
    dispatch('requestTranslate', {
      reason,
      indices: Array.from(dirtySentences)
    });
    if (clearDirty) dirtySentences.clear();
  }

  function toggleEditMode(){
    editMode = !editMode;
    if (!editMode && dirtySentences.size){
      triggerTranslation('exit-edit', { clearDirty: true });
    }
  }

  function isEditableTarget(el){
    if (!el) return false;
    const tag = el.tagName && el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || el.isContentEditable) return true;
    return false;
  }
  function handleKey(e){
    if (isEditableTarget(e.target)) return;
    if (e.key === 'ArrowLeft'){ e.preventDefault(); prevTarget(); }
    else if (e.key === 'ArrowRight'){ e.preventDefault(); nextTarget(); }
    else if (e.key === 'Enter'){ e.preventDefault(); confirmTarget(); }
  }

  function onUserScroll(){
    // Any manual scroll disables follow mode until re-enabled
    followPlayback = false;
  }

  function jumpToCurrent(){
    followPlayback = true;
    if (currentFlatIndex >= 0) {
      const el = document.getElementById(flatWords[currentFlatIndex]?.id);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }
  }
</script>

<svelte:window on:keydown={handleKey} />
<section class="te-root">
  <div class="te-toolbar">
    <div class="te-stats">
      <span class="badge">Verbeterd: {corrected}</span>
      <span class="muted">Bevestigd: {confirmed}/{corrected} · {percentageConfirmed}%</span>
      <span class="muted">Open: {pending}</span>
    </div>
    <div class="te-controls">
      <button class="icon-btn" on:click={() => showSettings = !showSettings} title="Instellingen">⚙️</button>
      {#if showSettings}
        <div class="menu">
          <label>Offset (ms)
            <input class="te-input" type="number" bind:value={offsetMs} />
          </label>
          <label>Pre‑roll (ms)
            <input class="te-input" type="number" bind:value={preRollMs} min="0" />
          </label>
          <label class="follow">
            <input type="checkbox" bind:checked={followPlayback} /> Volg afspelen
          </label>
          <button class="btn" on:click={jumpToCurrent}>Naar huidig</button>
        </div>
      {/if}
      <button class="icon-btn" on:click={toggleEditMode} title="Bewerk tekst">✏️</button>
      <button
        class="icon-btn"
        on:click={() => {
          showTranslation = !showTranslation;
          if (showTranslation) {
            isTranslating = translations.size === 0;
            triggerTranslation('toggle');
          }
        }}
        title="Toon vertaling"
        aria-pressed={showTranslation}
      >{isTranslating ? '⏳' : '🌐'}</button>
      {#if isTranslating && showTranslation}
        <span class="muted small">Vertaling laden…</span>
      {/if}
      <div class="nav">
        <button class="btn" on:click={prevTarget} title="Vorige (←)">←</button>
        <button class="btn" on:click={nextTarget} title="Volgende (→)">→</button>
        <button class="btn primary" on:click={confirmTarget} title="Bevestigen (Enter)">Bevestigen</button>
      </div>
    </div>
  </div>

  {#if audioSrc}
    <div class="timeline">
      {#each bands as b}
        <span class="band" style={`left:${(b.start/(audioEl?.duration||bands[bands.length-1]?.end||1))*100}%;width:${((b.end-b.start)/(audioEl?.duration||bands[bands.length-1]?.end||1))*100}%;background:${speakerColors[b.speaker]||'#94a3b8'}`}></span>
      {/each}
      <span class="head" style={`left:${(audioEl? (audioEl.currentTime/(audioEl.duration||1))*100 : 0)}%`}></span>
    </div>
    <audio
      bind:this={audioEl}
      class="w-full"
      controls
      preload="metadata"
      src={audioSrc}
      on:timeupdate={handleTimeUpdate}
      on:seeked={handleTimeUpdate}
      on:play={() => { followPlayback = true; handleTimeUpdate(); }}
    ></audio>
  {/if}

  <div class="te-transcript" bind:this={transcriptScrollEl} on:wheel={onUserScroll} on:scroll={onUserScroll}>
    {#each transcript as seg, i}
      <div class="te-sent {contextSpeakers && contextSpeakers.includes(seg.speaker) ? 'context-on' : ''}" id={`sent-${i}`} style={`--spk:${speakerColors[seg.speaker]||'#1d4ed8'}`}>
        <div class="ts">
          <div class="time">[{Number.isFinite(seg.start)?seg.start.toFixed(2):'--'}]</div>
          <div class="spk">
            {#if Array.isArray(speakerIds) && speakerIds.length}
              <select class="spk-select" bind:value={seg.speaker} on:change={(e)=>setSentenceSpeaker(i, e.target.value)}>
                {#each speakerIds as sid}
                  <option value={sid}>{speakerNames[sid] || sid}</option>
                {/each}
              </select>
            {/if}
          </div>
        </div>
        <div class="tw">
          {#if Array.isArray(seg.words) && seg.words.length}
            {#each seg.words as word, j}
              {#if Number.isFinite(word.start) && Number.isFinite(word.end)}
                <span
                  id={`w-${i}-${j}`}
                  class="word"
                  class:modified={word.corrected && word.corrected !== word.word}
                  class:context-suggested={word.flags?.suggestedByContext}
                  class:active={activeWordId === `w-${i}-${j}`}
                  style={`--spk:${speakerColors[seg.speaker]||'#1d4ed8'}`}
                  title={`${word.start.toFixed(2)}–${word.end.toFixed(2)}`}
                  role="button"
                  tabindex={editMode ? -1 : 0}
                  on:click={() => { if(!editMode) playOnlyWord(idToFlatIndex[`w-${i}-${j}`]); }}
                  on:keydown={(evt)=>{ if(!editMode && (evt.key === 'Enter' || evt.key === ' ')) { evt.preventDefault(); playOnlyWord(idToFlatIndex[`w-${i}-${j}`]); } }}
                >
                  {#if editMode}
                    <input class="w-edit" type="text" value={word.corrected || word.word} on:input={(e)=>{ const v=e.target.value; onEditCorrected(idToFlatIndex[`w-${i}-${j}`], v); }} />
                  {:else}
                    {#if (word.corrected && word.corrected !== word.word)}
                      <span class="w-new">{word.corrected}</span>
                      <span class="w-old">{word.word}</span>
                    {:else}
                      <span class="w-text">{word.word}</span>
                    {/if}
                  {/if}
                </span>
              {:else}
                <span
                  id={`w-${i}-${j}`}
                  class="word"
                  class:modified={word.corrected && word.corrected !== word.word}
                  class:context-suggested={word.flags?.suggestedByContext}
                  class:active={activeWordId === `w-${i}-${j}`}
                  style={`--spk:${speakerColors[seg.speaker]||'#1d4ed8'}`}
                  role="button"
                  tabindex={editMode ? -1 : 0}
                  on:click={() => { if(!editMode) playOnlyWord(idToFlatIndex[`w-${i}-${j}`]); }}
                  on:keydown={(evt)=>{ if(!editMode && (evt.key === 'Enter' || evt.key === ' ')) { evt.preventDefault(); playOnlyWord(idToFlatIndex[`w-${i}-${j}`]); } }}
                >
                  {#if editMode}
                    <input class="w-edit" type="text" value={word.corrected || word.word} on:input={(e)=>{ const v=e.target.value; onEditCorrected(idToFlatIndex[`w-${i}-${j}`], v); }} />
                  {:else}
                    {#if (word.corrected && word.corrected !== word.word)}
                      <span class="w-new">{word.corrected}</span>
                      <span class="w-old">{word.word}</span>
                    {:else}
                      <span class="w-text">{word.word}</span>
                    {/if}
                  {/if}
                </span>
              {/if}
            {/each}
          {:else}
            <span class="word word-plain">
              <span class="w-text">{seg.text || '(leeg segment)'}</span>
            </span>
          {/if}
          {#if showTranslation}
            <div class="tr-line">{translations.get(i) || (isTranslating ? 'Vertaling laden…' : '')}</div>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</section>

<style>
  .te-root { display: flex; flex-direction: column; gap: 1rem; outline: none; }
  .te-toolbar { position: relative; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; padding: 6px 10px; border: 1px solid rgb(var(--border)); border-radius: 8px; background: rgb(var(--page)); }
  .te-stats { display: flex; align-items: center; gap: 0.75rem; }
  .badge { background: #0ea5e9; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85rem; }
  .muted { color: rgb(var(--muted)); font-size: 0.85rem; }
  .muted.small { font-size: 0.8rem; }
  .te-controls { display: flex; align-items: center; gap: 0.5rem; }
  .te-input { width: 6rem; padding: 2px 6px; border: 1px solid rgb(var(--border)); border-radius: 6px; background: rgb(var(--page)); color: rgb(var(--text)); }
  .follow { display: inline-flex; align-items: center; gap: 6px; }
  .icon-btn { border: 1px solid rgb(var(--border)); border-radius: 6px; padding: 4px 8px; background: rgb(var(--page)); cursor: pointer; color: rgb(var(--text)); }
  .menu { position: absolute; top: calc(100% + 6px); right: 10px; background: rgb(var(--page)); border: 1px solid rgb(var(--border)); border-radius: 8px; padding: 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; z-index: 10; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
  .nav .btn { padding: 4px 8px; border: 1px solid rgb(var(--border)); border-radius: 6px; background: rgb(var(--page)); cursor: pointer; color: rgb(var(--text)); }
  .nav .btn.primary { background: #2563eb; color: white; border-color: #2563eb; }
  .timeline { position: relative; height: 8px; background: rgba(var(--border),0.55); border-radius: 4px; margin: 8px 0 6px; overflow: hidden; }
  .timeline .band { position: absolute; top: 0; bottom: 0; border-right: 1px solid rgba(255,255,255,0.4); }
  .timeline .head { position: absolute; top: -2px; bottom: -2px; width: 2px; background: rgb(var(--text)); }
  .te-transcript { display: flex; flex-direction: column; gap: 14px; padding-bottom: 8px; max-height: 62vh; overflow-y: auto; }
  .te-sent { display: grid; grid-template-columns: 120px 1fr; align-items: start; gap: 12px; padding: 10px 12px; border: 1px solid rgb(var(--border)); border-radius: 8px; background: rgb(var(--page)); }
  .te-sent.context-on { background: rgba(99,102,241,0.06); box-shadow: inset 0 0 0 1px rgba(99,102,241,0.25); }
  .ts { color: rgb(var(--muted)); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; display: flex; flex-direction: column; gap: 6px; }
  .ts .spk { display: flex; align-items: center; gap: 6px; }
  .ts .spk-select { font-size: 0.8rem; padding: 2px 6px; border: 1px solid rgb(var(--border)); border-radius: 6px; background: rgb(var(--page)); color: rgb(var(--text)); }
  .tw { line-height: 2.0; }
  .tr-line { margin-top: 6px; font-size: 0.95rem; color: rgb(var(--text)); background: rgba(var(--border),0.18); border: 1px solid rgb(var(--border)); padding: 6px 8px; border-radius: 6px; }
  .word { display: inline-flex; align-items: center; gap: 6px; margin-right: 6px; --spk:#1d4ed8; }
  .word.active { outline: 1px dashed var(--spk); outline-offset: 1px; border-radius: 4px; }
  .word .w-text { padding: 1px 2px; border-radius: 3px; }
  .word.active .w-text { background: var(--spk); color: #fff; }
  .word.active .w-new { background: var(--spk); color: #fff; border-color: var(--spk); }
  .word.active .w-edit { background: var(--spk); color: #fff; }
  .word.modified .w-text { color: rgb(var(--muted)); }
  .word-plain { margin-right: 0; }
  .word.context-suggested:not(.active) .w-new { border-bottom: 2px dotted #f97316; }
  .word.context-suggested:not(.active) .w-text { background: rgba(249, 115, 22, 0.12); border-radius: 4px; }
  .w-edit { font-size: 0.95rem; padding: 1px 4px; border: 1px dashed rgb(var(--border)); border-radius: 4px; background: rgb(var(--page)); color: rgb(var(--text)); }
  .w-new { padding: 1px 2px; border-radius: 3px; background: rgba(99,102,241,0.12); border: 1px solid rgba(99,102,241,0.35); }
  .w-old { color: rgb(var(--muted)); margin-left: 6px; font-size: 0.85em; text-decoration: line-through; }
  :global(.dark) .w-new { background: rgba(99,102,241,0.18); border-color: rgba(99,102,241,0.45); }
  :global(.dark) .te-sent.context-on { background: rgba(99,102,241,0.10); }
  /* Pulse-accent voor focus vanuit ReviewDialog (class wordt toegevoegd op <span class="word">) */
  @keyframes te-pulse-shadow {
    0%   { box-shadow: 0 0 0 0 rgba(37,99,235,0.55); }
    70%  { box-shadow: 0 0 0 8px rgba(37,99,235,0); }
    100% { box-shadow: 0 0 0 0 rgba(37,99,235,0); }
  }
  /* svelte-ignore css-unused-selector */
  :global(.word.pulse) {
    animation: te-pulse-shadow 0.9s ease-in-out 2;
    border-radius: 4px;
  }
  .word[role="button"]:hover:not(.active) .w-text,
  .word[role="button"]:focus-visible:not(.active) .w-text {
    text-decoration: underline;
    outline: 1px dashed var(--spk);
    outline-offset: 1px;
    border-radius: 3px;
  }
</style>
