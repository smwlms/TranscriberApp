<script>
  import { onMount, onDestroy, createEventDispatcher, tick } from 'svelte';
  import { get } from 'svelte/store'; // CORRECTED IMPORT
  import { apiBaseUrl } from '../stores.js';
  import contextDefaults from '../config/context_defaults.json';
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
  let contextTermList = [];
  let uniqueSpeakers = [];
  let editedMap = {};
  let contextVisible = {};
  let whyVisible = {};
  let greetingCache = [];
  let rolesHint = {};
  let firstSpeakerId = null;
  let lastSavedTexts = [];
  let improvements = [];

  // --- Speaker assist features ---
  let expectedSpeakers = 2; // adjustable in UI
  let isAssigningSpeakers = false;
  let hasSpeakerAssignmentChanges = false;
  let speakerCounts = {}; // { sid: count of segments }
  let speakerIndexMap = {}; // { sid: [segment indices] }
  let speakerNavPos = {}; // { sid: pointer }
  const SPEAKER_COLORS = ['#93c5fd','#fca5a5','#86efac','#fcd34d','#f9a8d4','#a7f3d0','#fbbf24','#c4b5fd','#fda4af','#99f6e4'];
  function colorForSpeaker(sid){ const idx = uniqueSpeakers.indexOf(sid); return SPEAKER_COLORS[(idx>=0?idx:0)%SPEAKER_COLORS.length]; }

  let contextStopwords = new Set();
  let knownCorrections = new Map();

  function mergeContextStopwords(words){
    const source = Array.isArray(words)
      ? words
      : words instanceof Set
        ? Array.from(words)
        : [];
    if (!source.length) return;
    const normalized = source
      .map((word) => (word ?? '').toString().trim().toLowerCase())
      .filter(Boolean);
    if (!normalized.length) return;
    contextStopwords = new Set([...contextStopwords, ...normalized]);
  }

  function mergeKnownCorrections(corrections){
    if (!corrections) return;
    const pairs = Array.isArray(corrections)
      ? corrections
      : corrections instanceof Map
        ? Array.from(corrections.entries())
        : typeof corrections === 'object'
          ? Object.entries(corrections)
          : [];
    if (!pairs.length) return;
    const next = new Map(knownCorrections);
    pairs.forEach(([candidate, correction]) => {
      const key = (candidate ?? '').toString().trim().toLowerCase();
      const value = (correction ?? '').toString().trim();
      if (!key || !value) return;
      next.set(key, correction);
    });
    knownCorrections = next;
  }

  mergeContextStopwords(contextDefaults?.stopwords || []);
  mergeKnownCorrections(contextDefaults?.knownCorrections || {});

  function addTermToBucket(term, bucket, { force = false, titleCaseFallback = false, keepFull = false } = {}, stopwords = contextStopwords){
    if (!term || typeof term !== 'string') return;
    const trimmed = term.trim();
    if (!trimmed) return;
    if (keepFull){
      const fullClean = trimmed.replace(/^[^A-Za-zÀ-ÖØ-öø-ÿ]+|[^A-Za-zÀ-ÖØ-öø-ÿ]+$/g, '');
      const lowered = fullClean.toLowerCase();
      if (fullClean && !stopwords.has(lowered)){
        bucket.add(titleCaseFallback ? fullClean.charAt(0).toUpperCase() + fullClean.slice(1) : fullClean);
      }
    }
    const fragments = trimmed.split(/[\s\/]+/);
    for (const fragment of fragments){
      const cleaned = fragment.replace(/^[^A-Za-zÀ-ÖØ-öø-ÿ]+|[^A-Za-zÀ-ÖØ-öø-ÿ]+$/g, '');
      const lower = cleaned.toLowerCase();
      if (!cleaned) continue;
      if (stopwords.has(lower)) continue;
      if (!force && cleaned.length < 4) continue;
      let finalToken = cleaned;
      if (titleCaseFallback && /^[a-z]/.test(cleaned)) {
        finalToken = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
      }
      bucket.add(finalToken);
    }
  }

  function deriveContextTerms(extraCtx, contextNames, proposedMapState, currentMapState, stopwords = contextStopwords){
    const bucket = new Set();
    if (Array.isArray(contextNames)) contextNames.forEach((name) => addTermToBucket(name, bucket, { force: true, keepFull: true }, stopwords));
    if (proposedMapState && typeof proposedMapState === 'object'){
      Object.values(proposedMapState).forEach((entry) => addTermToBucket(entry?.name, bucket, { force: true, keepFull: true }, stopwords));
    }
    if (currentMapState && typeof currentMapState === 'object'){
      Object.values(currentMapState).forEach((value) => addTermToBucket(value, bucket, { force: true, keepFull: true }, stopwords));
    }
    if (typeof extraCtx === 'string' && extraCtx.trim()){
      const matches = extraCtx.match(/[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'\-]{2,}(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'\-]{2,})*/g);
      if (matches) matches.forEach((token) => addTermToBucket(token, bucket, { titleCaseFallback: true, keepFull: true }, stopwords));
    }
    return Array.from(bucket);
  }

  function buildImprovementsFromTranscript(ts){
    if (!Array.isArray(ts)) return [];
    const list = [];
    ts.forEach((seg, i) => {
      if (!seg) return;
      const words = Array.isArray(seg.words) ? seg.words : [];
      words.forEach((w, j) => {
        if (!w) return;
        const raw = (w.word ?? '').toString();
        const suggestion = (w.corrected ?? '').toString();
        if (suggestion && suggestion !== raw){
          list.push({
            segment: i,
            word: j,
            speaker: seg.speaker,
            from: raw,
            to: suggestion,
            flags: w.flags || {},
            start: w.start,
            end: w.end,
          });
        }
      });
    });
    return list;
  }

  function refreshImprovements(){
    improvements = buildImprovementsFromTranscript(transcript).filter((item) => {
      return !(item?.flags && item.flags.confirmed === true);
    });
  }

  function focusImprovement(item){
    if (!item) return;
    const el = document.getElementById(`w-${item.segment}-${item.word}`);
    if (el){
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('pulse');
      setTimeout(() => el.classList.remove('pulse'), 900);
      if (typeof item.start === 'number') {
        seekAudioTo(item.start);
      }
    }
  }

  function normalizeTranslationsArray(arr, targetLen){
    if (!Number.isInteger(targetLen) || targetLen <= 0) return [];
    if (!Array.isArray(arr)) return new Array(targetLen).fill('');
    const out = arr.slice(0, targetLen);
    while (out.length < targetLen) out.push('');
    return out;
  }

  function normalizeTokenForContext(value){
    if (!value) return '';
    return value
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

  function maxEditFor(length){
    if (length <= 3) return 0;
    if (length <= 6) return 1;
    if (length <= 10) return 2;
    return 3;
  }

  function skeletonDistance(a, b){
    const collapse = (value) => normalizeTokenForContext(value)
      .replace(/[aeiou]/g, '')
      .replace(/(.)\1+/g, '$1');
    return levenshtein(collapse(a), collapse(b));
  }

  async function confirmImprovement(item){
    if (!item) return;
    const seg = transcript[item.segment];
    const words = Array.isArray(seg?.words) ? seg.words.slice() : null;
    if (!words || !words[item.word]) return;
    const baseWord = words[item.word];
    const updatedWord = {
      ...baseWord,
      flags: { ...(baseWord.flags || {}), confirmed: true }
    };
    words[item.word] = updatedWord;
    applyTranscriptWordChange(item.segment, words);
    hasCorrectionEdits = true;
    editorDirtyIndices.add(item.segment);
    improvements = improvements.filter(({ segment, word }) => segment !== item.segment || word !== item.word);
    refreshImprovements();
    await enqueueTranslations([item.segment]);
  }

  async function rejectImprovement(item){
    if (!item) return;
    const seg = transcript[item.segment];
    const words = Array.isArray(seg?.words) ? seg.words.slice() : null;
    if (!words || !words[item.word]) return;
    const current = words[item.word];
    const nextFlags = { ...(current.flags || {}) };
    delete nextFlags.suggestedByContext;
    delete nextFlags.confirmed;
    const updatedWord = { ...current };
    delete updatedWord.corrected;
    if (Object.keys(nextFlags).length) updatedWord.flags = nextFlags; else delete updatedWord.flags;
    words[item.word] = updatedWord;
    applyTranscriptWordChange(item.segment, words);
    hasCorrectionEdits = true;
    editorDirtyIndices.add(item.segment);
    improvements = improvements.filter(({ segment, word }) => segment !== item.segment || word !== item.word);
    refreshImprovements();
    await enqueueTranslations([item.segment]);
  }

  function adjustCaseFromContext(original, suggestion){
    if (!suggestion) return suggestion;
    if (!original) return suggestion;
    if (original === original.toUpperCase()) return suggestion.toUpperCase();
    if (original === original.toLowerCase()) return suggestion.toLowerCase();
    if (/^[A-Z]/.test(original) && !/^[A-Z]/.test(suggestion)){
      return suggestion.charAt(0).toUpperCase() + suggestion.slice(1);
    }
    return suggestion;
  }

  function mergePunctuationFromContext(original, suggestion){
    if (!suggestion) return suggestion;
    const leading = original.match(/^["'“”‘’\(\[]+/);
    const trailing = original.match(/["'“”‘’\)\]\.,;:!?]+$/);
    let result = suggestion;
    if (leading) result = leading[0] + result;
    if (trailing) result = result + trailing[0];
    return result;
  }

  function buildNeighborHints(terms){
    const map = new Map();
    if (!Array.isArray(terms)) return map;
    terms.forEach((term) => {
      if (!term || typeof term !== 'string') return;
      const fragments = term
        .split(/\s+/)
        .map((piece) => normalizeTokenForContext(piece))
        .filter(Boolean);
      fragments.forEach((frag, idx) => {
        if (!frag) return;
        const bucket = map.get(frag) || new Set();
        if (idx > 0 && fragments[idx - 1]) bucket.add(fragments[idx - 1]);
        if (idx < fragments.length - 1 && fragments[idx + 1]) bucket.add(fragments[idx + 1]);
        map.set(frag, bucket);
      });
    });
    return map;
  }

  function applyContextCorrectionsToTranscript(ts, terms){
    // Adaptieve Levenshtein, fonetisch skeleton en neighbor hints voor context-gebaseerde autocorrectie.
    if (!Array.isArray(ts) || !Array.isArray(terms) || !terms.length) return;
    const candidates = terms
      .map((raw) => ({ raw, norm: normalizeTokenForContext(raw) }))
      .filter((cand) => cand.norm && cand.norm.length >= 4)
      .sort((a, b) => b.norm.length - a.norm.length);

    const neighborHints = buildNeighborHints(terms);

    ts.forEach((seg) => {
      if (!seg || !Array.isArray(seg.words)) return;
      seg.words.forEach((word, idx) => {
        const original = (word?.word ?? '').toString();
        const normWord = normalizeTokenForContext(original);
        if (!normWord) return;
        if (word?.flags?.manualEdit) return;
        if (typeof word?.corrected === 'string' && word.corrected && word.corrected !== original) return;

        const manualFix = knownCorrections.get(normWord);
        if (manualFix) {
          const adjusted = adjustCaseFromContext(original, manualFix);
          const merged = mergePunctuationFromContext(original, adjusted);
          if (merged && merged !== original){
            const updatedFlags = { ...(word.flags || {}), suggestedByContext: true };
            seg.words[idx] = {
              ...word,
              corrected: merged,
              flags: updatedFlags,
            };
          }
          return;
        }

        const originalAllLower = original === original.toLowerCase();
        const maxDist = maxEditFor(normWord.length);
        if (normWord.length <= 2) return; // never auto-correct very short tokens

        const prevToken = idx>0 ? (seg.words[idx-1]?.corrected || seg.words[idx-1]?.word || '').toString() : '';
        const nextToken = idx<seg.words.length-1 ? (seg.words[idx+1]?.corrected || seg.words[idx+1]?.word || '').toString() : '';
        const prevNorm = normalizeTokenForContext(prevToken);
        const nextNorm = normalizeTokenForContext(nextToken);

        let best = null; // { candidate, effective }

        for (const cand of candidates){
          const candidateLooksName = /^[A-Z][a-zÀ-ÖØ-öø-ÿ'-]*$/.test(cand.raw);
          const candidateIsProbablyPerson = candidateLooksName && (cand.raw.length <= 7);
          if (originalAllLower && candidateIsProbablyPerson) continue;
          if (cand.norm === 'realo' && normWord.length <= 4 && normWord !== 'realo') continue;

          const distance = levenshtein(normWord, cand.norm);
          let effective = distance;

          const neighbors = neighborHints.get(cand.norm);
          if (neighbors && (neighbors.has(prevNorm) || neighbors.has(nextNorm))) {
            effective = Math.max(0, effective - 1);
          }

          const lengthGap = Math.abs(normWord.length - cand.norm.length);
          if (lengthGap > 3) continue;

          const skelOk = normWord.length > 3 && cand.norm.length > 3 && skeletonDistance(normWord, cand.norm) <= 2;

          if (normWord.length <= 3 && effective > 0) continue;

          if (effective <= maxDist || skelOk) {
            if (!best || effective < best.effective || (effective === best.effective && cand.norm.length > best.candidate.norm.length)){
              best = { candidate: cand, effective };
            }
          }
        }

        if (best){
          const adjusted = adjustCaseFromContext(original, best.candidate.raw);
          const merged = mergePunctuationFromContext(original, adjusted);
          if (merged && merged !== original){
            const updatedFlags = { ...(word.flags || {}), suggestedByContext: true };
            seg.words[idx] = {
              ...word,
              corrected: merged,
              flags: updatedFlags,
            };
          }
        }
      });
    });
  }

  // Consolidation hints state
  let consolidationHints = [];

  let isEditingTranscript = false;
  let editedTranscript = {};
  let transcriptContainer; // scroll control when toggling editor
  // Transcript Editor integration
  import TranscriptEditor from './TranscriptEditor.svelte';
  let hasCorrectionEdits = false;
  const editorDirtyIndices = new Set();
  const pendingTranslateIndices = new Set();

  async function enqueueTranslations(indices = []){
    if (Array.isArray(indices)) {
      indices.forEach((idx) => {
        if (Number.isInteger(idx)) pendingTranslateIndices.add(idx);
      });
    }
    if (isTranslatingEN) return;
    if (!pendingTranslateIndices.size) return;
    const batch = Array.from(pendingTranslateIndices).sort((a, b) => a - b);
    pendingTranslateIndices.clear();
    let failed = false;
    try {
      await translateWithSync({ indices: batch });
    } catch (err) {
      failed = true;
      console.warn('translateWithSync failed for queued indices', err);
    }
    if (failed) batch.forEach((idx) => pendingTranslateIndices.add(idx));
    if (!failed && pendingTranslateIndices.size) {
      await enqueueTranslations();
    }
  }
  function onEditorChanged(event){
    hasCorrectionEdits = true;
    const dirty = event?.detail?.dirtyIndices;
    if (Array.isArray(dirty)) {
      dirty.forEach((idx) => { if (Number.isInteger(idx)) editorDirtyIndices.add(idx); });
    }
    refreshImprovements();
  }
  import { translateTranscript } from '../api.js';
  let isTranslatingEN = false;

  function segmentTextFromWords(words){
    if (!Array.isArray(words) || !words.length) return '';
    const tokens = words
      .map((w) => {
        const corr = (w?.corrected ?? '').toString();
        const raw = (w?.word ?? '').toString();
        return (corr || raw).trim();
      })
      .filter(Boolean);
    return tokens.join(' ').replace(/\s+([,.;:!?])/g, '$1');
  }

  // Build segment.text from word-level corrections so translation reflects edits
  function rebuildSegmentTextsFromWords(ts){
    if (!Array.isArray(ts)) return ts;
    return ts.map((seg)=>{
      try{
        const words = Array.isArray(seg?.words) ? seg.words : [];
        if (!words.length) return seg;
        const text = segmentTextFromWords(words);
        return { ...seg, text };
      }catch{ return seg; }
    });
  }

  function applyTranscriptWordChange(segmentIndex, words){
    const seg = transcript?.[segmentIndex];
    if (!seg) return;
    const nextWords = Array.isArray(words) ? words : [];
    const updated = {
      ...seg,
      words: nextWords,
      text: nextWords.length ? segmentTextFromWords(nextWords) : seg.text
    };
    transcript = transcript.map((entry, idx) => (idx === segmentIndex ? updated : entry));
    return updated;
  }

  // Ensure unsaved edits are synced server-side before requesting translation
  function handleTranslateRequest(event){
    const detail = event?.detail ?? {};
    if (Array.isArray(detail?.indices)) {
      detail.indices.forEach((idx) => { if (Number.isInteger(idx)) editorDirtyIndices.add(idx); });
    }
    return translateWithSync(detail);
  }

  async function translateWithSync(options = {}){
    try{
      isTranslatingEN = true;
      let didSave = false;
      const requested = new Set();
      if (Array.isArray(options?.indices)) {
        for (const idx of options.indices){
          if (Number.isInteger(idx)) requested.add(idx);
        }
      }
      for (const idx of editorDirtyIndices){
        requested.add(idx);
      }
      if (hasCorrectionEdits){
        const updated = rebuildSegmentTextsFromWords(transcript);
        transcript = updated;
        try{ await updateTranscriptData(jobId, transcript); didSave = true; hasCorrectionEdits = false; } catch(e){ console.warn('Failed to save word edits before translate', e); }
      }
      if (isEditingTranscript && Object.keys(editedTranscript||{}).length){
        try { await saveTranscriptEdits(); didSave = true; } catch(e){ console.warn('Failed to save text edits before translate', e); }
        requested.clear();
      }
      const currentTexts = (transcript||[]).map(s => (s?.text ?? ''));
      if (!Array.isArray(lastSavedTexts) || lastSavedTexts.length !== currentTexts.length){
        lastSavedTexts = currentTexts.slice();
      }
      const diff = [];
      for (let i=0;i<currentTexts.length;i++){
        if (currentTexts[i] !== (lastSavedTexts[i] ?? '')) diff.push(i);
      }
      diff.forEach((idx)=> requested.add(idx));

      const indices = Array.from(requested).sort((a,b)=>a-b);

      let res;
      if (indices.length > 0){
        const payloadTexts = indices.map(i => currentTexts[i] ?? '');
        res = await translateTranscript(jobId,'en',{ indices, texts: payloadTexts });
        let updated = false;
        if (res && Array.isArray(res.indices) && Array.isArray(res.translations)){
          const base = (Array.isArray(translationsEN) && translationsEN.length === currentTexts.length)
            ? translationsEN.slice()
            : new Array(currentTexts.length).fill('');
          res.indices.forEach((idx, k) => {
            if (typeof idx === 'number') {
              const val = res.translations?.[k] || '';
              if (val.trim()) updated = true;
              base[idx] = val || base[idx] || '';
            }
          });
          translationsEN = base;
        } else if (res && Array.isArray(res.translations)) {
          const out = res.translations.slice(0, currentTexts.length);
          while (out.length < currentTexts.length) out.push('');
          updated = out.some((txt) => txt && txt.trim());
          translationsEN = out;
        }
        if (!updated) {
          try {
            const fallback = await translateTranscript(jobId,'en');
            if (fallback && Array.isArray(fallback.translations)) {
              translationsEN = normalizeTranslationsArray(fallback.translations, currentTexts.length);
            }
          } catch (fallbackErr) {
            console.warn('Fallback translate failed', fallbackErr);
          }
        }
      } else if (!didSave) {
        res = await translateTranscript(jobId,'en');
        if (res && Array.isArray(res.translations)) {
          translationsEN = normalizeTranslationsArray(res.translations, currentTexts.length);
        }
      }
      lastSavedTexts = currentTexts.slice();
      editorDirtyIndices.clear();
    } finally {
      isTranslatingEN = false;
    }
  }

  // Map speaker ids → display names and colors for editor
  $: speakerNames = Object.fromEntries((uniqueSpeakers||[]).map(s => [s, editedMap[s] || s]));
  $: speakerColors = Object.fromEntries((uniqueSpeakers||[]).map(s => [s, colorForSpeaker(s)]));
  $: contextTermList = deriveContextTerms(extraContext, contextNamesDetected, proposedMap, editedMap, contextStopwords).filter(isLikelyName);

  let audioPlayer;
  let currentWordId = null;

  onMount(async () => {
    await fetchReviewData();
    // Auto-translate preview (preload) on open so the editor shows EN immediately
    try {
      await translateWithSync();
    } catch (e) {
      console.warn('[ReviewDialog] initial translate failed:', e);
    } finally { /* state managed in translateWithSync */ }
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
      mergeContextStopwords(Array.isArray(data.context_stopwords) ? data.context_stopwords : []);
      mergeKnownCorrections(data.known_corrections);
      if (Array.isArray(data.initial_translations)) {
        translationsEN = normalizeTranslationsArray(data.initial_translations, (transcript||[]).length);
      }
      lastSavedTexts = transcript.map((s) => s?.text ?? '');
      editorDirtyIndices.clear();
      nameEvidence = data.name_evidence || {};
      contextNamesDetected = (data.context_names_detected || []).filter(isLikelyName);
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

      const derivedTerms = deriveContextTerms(extraContext, contextNamesDetected, proposedMap, initialEditedMap, contextStopwords);
      applyContextCorrectionsToTranscript(transcript, derivedTerms);
      transcript = rebuildSegmentTextsFromWords(transcript);

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

      refreshImprovements();

    } catch (e) {
      console.error('[ReviewDialog] Fetch review data failed:', e);
      error = `Fout bij laden review data: ${e.message}`;
    } finally {
      isLoading = false;
    }
  }

  async function toggleContext(speakerId) {
    contextVisible[speakerId] = !contextVisible[speakerId];
    if (contextVisible[speakerId]) {
      await tick();
      const el = document.getElementById(`context-${speakerId}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
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

  const GREETING_PREFIXES = ['hallo','hoi','hey','dag','goedemiddag','goedenavond','goedemorgen','hi','hello'];
  const INTRO_PHRASES = ['ik ben','dit is','mijn naam is','je spreekt met','u spreekt met','this is','i am',"i'm",'you are speaking with',"you're speaking with"];
  const WITH_LINKERS = ['met','with'];
  const fallbackNameHints = new Map();

  function normalizeLoose(value){
    if (!value && value !== 0) return '';
    return value.toString().trim().toLowerCase();
  }

  function cleanForMatch(value){
    let s = normalizeLoose(value);
    [',', '.', '!', '?', ':', ';', "\n", "\t"].forEach((ch) => {
      s = s.split(ch).join(' ');
    });
    return s.split(' ').filter(Boolean).join(' ');
  }

  function nameVariantsForSpeaker(sid){
    const variants = new Set();
    const direct = normalizeLoose(editedMap[sid]);
    if (direct) {
      variants.add(direct);
      const parts = direct.split(' ');
      if (parts.length > 1) variants.add(parts[0]);
    }
    const proposed = normalizeLoose(proposedMap[sid]?.name);
    if (proposed && proposed !== direct) {
      variants.add(proposed);
      const parts = proposed.split(' ');
      if (parts.length > 1) variants.add(parts[0]);
    }
    if (!variants.size && fallbackNameHints.has(sid)) {
      const hint = normalizeLoose(fallbackNameHints.get(sid));
      if (hint) {
        variants.add(hint);
        const parts = hint.split(' ');
        if (parts.length > 1) variants.add(parts[0]);
      }
    }
    return Array.from(variants);
  }

  function detectIntroSpeaker(text, candidateIds){
    if (!text) return null;
    const line = cleanForMatch(text);
    for (const sid of candidateIds){
      const variants = nameVariantsForSpeaker(sid);
      if (!variants.length) continue;
      for (const name of variants){
        if (!name) continue;
        for (const phrase of INTRO_PHRASES){
          const seq = `${phrase} ${name}`;
          if (line.includes(seq)) return sid;
        }
        for (const linker of WITH_LINKERS){
          const seq = `${linker} ${name}`;
          if (line.includes(seq)) return sid;
        }
      }
    }
    return null;
  }

  function detectGreetingSpeaker(text, candidateIds){
    if (!text) return null;
    const line = cleanForMatch(text);
    const startsGreeting = GREETING_PREFIXES.some((prefix) => line.startsWith(prefix));
    if (!startsGreeting) return null;
    for (const sid of candidateIds){
      const variants = nameVariantsForSpeaker(sid);
      if (!variants.length) continue;
      for (const name of variants){
        if (name && line.includes(name)) return sid;
      }
    }
    return null;
  }

  function applyTwoSpeakerHeuristics(keptIds){
    if (!Array.isArray(keptIds) || keptIds.length !== 2) return false;
    const [speakerA, speakerB] = keptIds;
    fallbackNameHints.clear();
    greetingCache.forEach(({ speaker, name }) => {
      const target = speaker === speakerA ? speakerB : speakerA;
      if (typeof name === 'string' && !fallbackNameHints.has(target)) {
        fallbackNameHints.set(target, name);
      }
    });
    const contextFallbacks = (contextNamesDetected || []).map((n) => normalizeLoose(n)).filter(Boolean);
    if (!fallbackNameHints.has(speakerA) && contextFallbacks.length) fallbackNameHints.set(speakerA, contextFallbacks[0]);
    if (!fallbackNameHints.has(speakerB) && contextFallbacks.length > 1) fallbackNameHints.set(speakerB, contextFallbacks[1]);

    let changed = false;
    const lookahead = Math.min(transcript.length, 12);
    for (let i = 0; i < lookahead; i++){
      const seg = transcript[i];
      if (!seg || !seg.text) continue;
      const variantTexts = [];
      const raw = normalizeLoose(seg.text);
      if (raw) variantTexts.push(raw);
      if (Array.isArray(translationsEN) && typeof translationsEN[i] === 'string'){
        const tr = normalizeLoose(translationsEN[i]);
        if (tr && !variantTexts.includes(tr)) variantTexts.push(tr);
      }
      let resolvedSpeaker = null;
      for (const candidateText of variantTexts){
        if (!candidateText) continue;
        const introMatch = detectIntroSpeaker(candidateText, keptIds);
        if (introMatch){
          resolvedSpeaker = introMatch;
          break;
        }
      }
      if (!resolvedSpeaker){
        for (const candidateText of variantTexts){
          if (!candidateText) continue;
          const greeted = detectGreetingSpeaker(candidateText, keptIds);
          if (greeted){
            // Greeting mentions the other speaker → actual speaker is the opposite id
            resolvedSpeaker = greeted === speakerA ? speakerB : speakerA;
            break;
          }
        }
      }
      if (resolvedSpeaker && seg.speaker !== resolvedSpeaker){
        transcript[i].speaker = resolvedSpeaker;
        changed = true;
      }
    }
    return changed;
  }

  function consolidateToExpected(){
    const n = Math.max(1, parseInt(expectedSpeakers||2,10));
    const counts = {};
    transcript.forEach(s=>{ if(s?.speaker) counts[s.speaker]=(counts[s.speaker]||0)+1; });
    const sorted = Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([sid])=>sid);
    const keep = new Set(sorted.slice(0,n));
    let kept = Array.from(keep);
    if (kept.length === 2){
      const applied = applyTwoSpeakerHeuristics(kept);
      if (applied){
        hasSpeakerAssignmentChanges = true;
        const recompute = {};
        transcript.forEach(s=>{ if(s?.speaker) recompute[s.speaker]=(recompute[s.speaker]||0)+1; });
        const resort = Object.entries(recompute).sort((a,b)=>b[1]-a[1]).map(([sid])=>sid);
        keep.clear();
        resort.slice(0,n).forEach((sid)=>keep.add(sid));
        kept = Array.from(keep);
      }
    }
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
  let translationsEN = [];

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

  async function reRunNameDetection(){
    try {
      const resp = await reDetectNames(jobId);
      if (resp && resp.proposed_map) {
        proposedMap = resp.proposed_map || {};
        contextSnippets = resp.context_snippets || {};
        // Vul enkel lege velden bij
        Object.keys(proposedMap).forEach((id) => { if (!editedMap[id]) editedMap[id] = proposedMap[id]?.name ?? ''; });
      }
    } catch (e) {
      console.warn('[ReviewDialog] reRunNameDetection failed:', e);
      error = 'Kon speaker detectie niet herstarten';
    }
  }

  async function saveTranscriptEdits() {
    isLoading = true;
    error = '';
    try {
      const prevTexts = transcript.map((segment) => segment?.text ?? '');
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
      const changedIndices = [];
      updatedFullTranscript.forEach((seg, idx) => {
        const newText = seg?.text ?? '';
        if (newText !== (prevTexts[idx] ?? '')){
          changedIndices.push(idx);
        }
      });
      await updateTranscriptData(jobId, updatedFullTranscript);
      transcript = updatedFullTranscript;
      lastSavedTexts = transcript.map(s => (s?.text ?? ''));
      refreshImprovements();
      greetingCache = greetingMatches();
      isEditingTranscript = false;
      // Refresh English translations after content changes
      if (changedIndices.length){
        try {
          const payloadTexts = changedIndices.map((idx) => transcript[idx]?.text ?? '');
          const res = await translateTranscript(jobId, 'en', { indices: changedIndices, texts: payloadTexts });
          let updated = false;
          if (res && Array.isArray(res.indices) && Array.isArray(res.translations)){
            const base = normalizeTranslationsArray(translationsEN, transcript.length);
            res.indices.forEach((idx, k) => {
              if (typeof idx === 'number') {
                const val = res.translations?.[k] || '';
                if (val.trim()) updated = true;
                base[idx] = val || base[idx] || '';
              }
            });
            translationsEN = base;
          } else if (res && Array.isArray(res.translations)) {
            const normalized = normalizeTranslationsArray(res.translations, transcript.length);
            updated = normalized.some((txt) => txt && txt.trim());
            translationsEN = normalized;
          }
          if (!updated) {
            const fallback = await translateTranscript(jobId, 'en');
            if (fallback && Array.isArray(fallback.translations)) {
              translationsEN = normalizeTranslationsArray(fallback.translations, transcript.length);
            }
          }
        } catch (e) {
          console.warn('[ReviewDialog] translate after save failed:', e);
        }
      }
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
      if (hasSpeakerAssignmentChanges || hasCorrectionEdits) {
        await saveSpeakerAssignmentsIfNeeded();
        if (hasCorrectionEdits) {
          // Auto-confirm all corrected words so Part 2 materializes them
          try {
            for (const seg of transcript){
              if (!seg || !Array.isArray(seg.words)) continue;
              for (const w of seg.words){
                if (w && w.corrected && (!w.flags || !w.flags.confirmed)){
                  w.flags = { ...(w.flags||{}), confirmed: true };
                }
              }
            }
          } catch {}
          refreshImprovements();
          // Keep segment.text in sync with corrected words before saving
          transcript = rebuildSegmentTextsFromWords(transcript);
          try { await updateTranscriptData(jobId, transcript); } catch (e) { console.warn('Failed saving editor corrections', e); }
          lastSavedTexts = transcript.map((s) => s?.text ?? '');
          // After saving word-level corrections, refresh translations as well
          try {
            const res = await translateTranscript(jobId,'en');
            if(res && Array.isArray(res.translations)){
              translationsEN = normalizeTranslationsArray(res.translations, transcript.length);
            }
          } catch {}
          hasCorrectionEdits = false;
        }
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
            foundWordId = `w-${i}-${j}`;
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
  <div class="rounded-xl w-full max-w-6xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl" style="background-color: rgb(var(--page)); color: rgb(var(--text)); border: 1px solid rgb(var(--border));">
    <header class="flex justify-between items-center p-4" style="border-bottom: 1px solid rgb(var(--border));">
      <div class="flex items-center gap-4">
        <h2 class="text-lg font-semibold">Speaker & Transcript Review</h2>
        <div class="flex items-center gap-2 text-sm">
          <label for="expected-speakers" class="muted">Expected number of speakers</label>
          <input id="expected-speakers" type="number" min="1" class="w-20 px-2 py-1 rounded" bind:value={expectedSpeakers}>
          <button class="btn btn-ghost text-xs px-2 py-1" on:click={consolidateToExpected} disabled={isLoading}>Consolidate</button>
          <button class="btn btn-ghost text-xs px-2 py-1" on:click={toggleAssignSpeakers} aria-pressed={isAssigningSpeakers}>{isAssigningSpeakers ? 'Stop assigning' : 'Assign speakers'}</button>
        </div>
      </div>
      <button on:click={cancelReview} disabled={isSaving} class="text-2xl muted hover:opacity-70 disabled:opacity-50 transition-opacity">&times;</button>
    </header>

    <main class="flex-1 overflow-hidden p-6 custom-scrollbar">
      {#if isLoading && !isSaving}
        <div class="flex justify-center items-center h-full">
          <p class="text-gray-400 text-lg">Loading review data…</p>
        </div>
      {:else if error}
        <div class="p-4 rounded border" style="border-color: rgb(239 68 68); background: rgba(239,68,68,0.08); color: rgb(127 29 29);">
          <strong class="block mb-2">Error:</strong>
          <p class="mb-3">{error}</p>
          {#if !isSaving}
            <button on:click={fetchReviewData}
              class="btn btn-ghost text-sm">
              Try again
            </button>
          {/if}
        </div>
      {/if}

      {#if !isLoading || error}
        <fieldset disabled={isSaving || (isLoading && !error)}>
          <div class="review-grid">
            <div class="col-left custom-scrollbar">

          <section>
            <div class="assign-head">
              <h3 class="text-xl font-semibold">Assign Speaker Names</h3>
              <div class="tools flex items-center gap-2 flex-wrap">
                {#each uniqueSpeakers as sid (sid)}
                  <button type="button" class="chip" style={`color:${colorForSpeaker(sid)}; border-color:${colorForSpeaker(sid)};`} on:click={() => scrollToNextFor(sid)} title="Scroll to next occurrence">
                    {sid} · {speakerCounts[sid] || 0}
                  </button>
                {/each}
                {#if uniqueSpeakers.length === 2}
                  <button type="button" on:click={swapNames}
                    class="btn btn-ghost text-xs px-2 py-1"
                    title="Swap names between the two speakers">
                    ⇄ Swap
                  </button>
                {/if}
              </div>
            </div>
            {#if extraContext}
                <div class="mb-3 text-sm">
                <div class="opacity-80">Extra context:</div>
                <div class="mt-1 p-2 rounded whitespace-pre-wrap" style="border: 1px solid rgb(var(--border)); background-color: rgb(var(--page));">{extraContext}</div>
                {#if contextNamesDetected && contextNamesDetected.length}
                  <div class="mt-2 text-xs muted">Detected names: {#each contextNamesDetected as nm, i}<span class="font-semibold">{nm}</span>{i<contextNamesDetected.length-1?', ':''}{/each}</div>
                {/if}
              </div>
            {/if}
            {#if false}
              <!-- Consolidation hints intentionally hidden as requested -->
            {/if}
            {#if uniqueSpeakers.length === 0 && !isLoading}
                <p class="text-gray-400">No speakers identified in this transcript.</p>
            {/if}
            <div class="space-y-4">
              {#each uniqueSpeakers as speakerId (speakerId)}
                <div class="spk-row flex flex-col gap-2">
                  <div class="spk-title text-xs font-mono opacity-70" style={`color:${colorForSpeaker(speakerId)}`}>{speakerId}</div>
                  <div class="spk-line flex items-center gap-2">
                  <label for={`speaker-name-${speakerId}`} class="w-28 text-xs shrink-0 flex items-center gap-2" style={`color:${colorForSpeaker(speakerId)}`}></label>
                    {#if roleForSpeaker(speakerId) === 'caller'}
                      {@html PhoneOutgoing()}<span class="text-xs text-blue-400">caller</span>
                    {:else if roleForSpeaker(speakerId) === 'callee'}
                      {@html PhoneIncoming()}<span class="text-xs text-blue-400">callee</span>
                    {:else if roleForSpeaker(speakerId) === 'caller?'}
                      {@html PhoneOutgoing()}<span class="text-xs text-blue-400">caller?</span>
                    {/if}
                  </div>
                  <input
                    id={`speaker-name-${speakerId}`}
                    type="text"
                    bind:value={editedMap[speakerId]}
                    placeholder={proposedMap[speakerId]?.name ? `Suggested: ${proposedMap[speakerId].name}` : 'Enter name...'}
                    class="flex-grow p-2 rounded w-full {isLikelyName(editedMap[speakerId]) ? '' : ''}"
                  />
                  {#if proposedMap[speakerId]?.confidence !== undefined}
                    <span class="text-xs text-gray-400">{Math.round((proposedMap[speakerId].confidence||0)*100)}%</span>
                  {/if}
                  <div class="spk-actions">
                    <button type="button" class="btn btn-ghost text-xs px-2 py-1" on:click={() => whyVisible[speakerId]=!whyVisible[speakerId]}>Why?</button>
                    {#if proposedMap[speakerId]?.reasoning_indices?.length}
                      <button
                        type="button"
                        on:click={() => toggleContext(speakerId)}
                        class="btn btn-ghost text-xs px-2 py-1"
                      >
                        {#if contextVisible[speakerId]}Hide context{:else}Show context{/if}
                      </button>
                    {/if}
                  </div>
                  {#if contextNamesDetected && contextNamesDetected.length}
                    {#each contextNamesDetected as nm (nm)}
                      <button type="button" class="btn btn-ghost text-xs px-2 py-1" on:click={() => assignNameToSpeaker(nm, speakerId)}>Assign ‘{nm}’</button>
                    {/each}
                  {/if}
                </div>
                {#if whyVisible[speakerId]}
                  <pre class="mt-2 p-2 rounded text-xs whitespace-pre-wrap" style="border: 1px solid rgb(var(--border)); background-color: rgb(var(--page));">{whyFor(speakerId)}</pre>
                {/if}
                {#if contextVisible[speakerId]}
                  <pre id={`context-${speakerId}`} class="p-3 rounded text-xs overflow-auto max-h-40 custom-scrollbar whitespace-pre-wrap" style="border: 1px solid rgb(var(--border)); background-color: rgb(var(--page));">{getRelevantContext(speakerId)}</pre>
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
                        Go to segment {ev.index}
                      </button>
                      <span class="opacity-70"> — {ev.snippet?.split('\n')[0] || '(snippet)'} </span>
                    </li>
                  {/each}
                </ul>
              </div>
            {/if}
          </section>
            </div>
            <div class="col-right custom-scrollbar">
          <section>
            <div class="section-head">
              <h3 class="text-xl font-semibold">Transcript Editor</h3>
              <p class="muted text-sm">Woord‑nauwkeurige sync, contextuele voorstellen en review‑navigatie. Gebruik ←/→/Enter.</p>
            </div>
            {#if improvements.length}
              <div class="improvements-panel">
                <div class="improvements-head">
                  <h4 class="text-sm font-semibold uppercase tracking-wide">Verbeteringen</h4>
                  <span class="count">{improvements.length}</span>
                </div>
                <ul class="improvements-list">
                  {#each improvements as item}
                    <li class="improvement-row">
                      <button type="button" class="improvement-btn" on:click={() => focusImprovement(item)}>
                        <span class="imp-speaker" style={`color:${speakerColors[item.speaker]||'#60a5fa'}`}>{speakerNames[item.speaker] || item.speaker}</span>
                        <span class="imp-change">{item.from} → {item.to}</span>
                        {#if item.flags?.suggestedByContext}
                          <span class="badge badge-context">context</span>
                        {/if}
                        <span class="badge {item.flags?.confirmed ? 'badge-confirmed' : 'badge-open'}">{item.flags?.confirmed ? 'bevestigd' : 'open'}</span>
                      </button>
                      <div class="improvement-actions">
                        <button
                          type="button"
                          class="btn-pill btn-pill--confirm"
                          on:click={async (event) => { event.stopPropagation(); await confirmImprovement(item); }}
                        >
                          <span class="icon" aria-hidden="true">✓</span>
                          <span>Bevestig</span>
                        </button>
                        <button
                          type="button"
                          class="btn-pill btn-pill--reject"
                          on:click={async (event) => { event.stopPropagation(); await rejectImprovement(item); }}
                        >
                          <span class="icon" aria-hidden="true">✕</span>
                          <span>Weiger</span>
                        </button>
                      </div>
                    </li>
                  {/each}
                </ul>
              </div>
            {/if}
            <div class="editor-head-actions">
              <button class="btn btn-ghost text-xs px-2 py-1" title="Re-run speaker detection" on:click={reRunNameDetection}>↻ Re-detect names</button>
              <button
                class="btn btn-ghost text-xs px-2 py-1"
                title="Translate view (EN)"
                on:click={() => translateWithSync()}
                disabled={isTranslatingEN}
              >{isTranslatingEN ? 'Translating…' : 'Translate (preload)'}</button>
            </div>
            <TranscriptEditor
              {transcript}
              {audioRelativePath}
              {speakerNames}
              {speakerColors}
              bind:audioElement={audioPlayer}
              speakerIds={uniqueSpeakers}
              contextSpeakers={Object.keys(contextVisible||{}).filter(k=>contextVisible[k])}
              contextTerms={contextTermList}
              externalTranslations={translationsEN}
              on:changed={onEditorChanged}
              on:requestTranslate={handleTranslateRequest}
            />
          </section>
            </div>
          </div>

          
        </fieldset>
      {/if}
    </main>

    <footer class="flex justify-between items-center p-3 px-4 gap-3" style="border-top: 1px solid rgb(var(--border));">
      <div class="footer-legend muted text-sm">
        Legende: <span class="chip-live" style="background:#94a3b8"></span> huidig · <span class="chip-corr">vakje</span> voorstel
      </div>
      <div class="flex items-center gap-3">
      <button
        on:click={cancelReview}
        disabled={isSaving}
        class="btn btn-ghost"
      >
        Cancel
      </button>
      <button
        on:click={saveAll}
        disabled={isLoading || isSaving || (uniqueSpeakers.length === 0 && transcript.length === 0)}
        class="btn btn-primary"
      >
        {#if isSaving}Saving…{:else}Confirm &amp; Continue{/if}
      </button>
      </div>
    </footer>
  </div>
</div>

<style>
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
  .custom-scrollbar { overflow-x: hidden; }
  .review-grid { display: flex; align-items: stretch; gap: 20px; height: 100%; }
  .review-grid .col-left { flex: 0 0 400px; max-width: 460px; overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 14px; }
  .review-grid .col-right { flex: 1 1 auto; overflow-y: auto; padding-left: 4px; }
  .review-grid .col-left section, .review-grid .col-right section {
    border: 1px solid rgb(var(--border)); border-radius: 10px; padding: 12px;
    background: rgb(var(--page)); color: rgb(var(--text));
  }
  .assign-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .spk-row { border: 1px dashed rgb(var(--border)); border-radius: 10px; padding: 10px; }
  .footer-legend .chip-live { display: inline-block; width: 18px; height: 10px; border-radius: 4px; margin: 0 4px; vertical-align: middle; }
  .spk-actions { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-left: 4px; }
  .editor-head-actions { display:flex; justify-content:flex-end; margin: 4px 0 8px; }
  .improvements-panel { border: 1px dashed rgb(var(--border)); border-radius: 10px; padding: 10px; margin-bottom: 12px; background: rgba(148, 163, 184, 0.08); }
  .improvements-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
  .improvements-head .count { font-size: 0.75rem; background: rgba(148, 163, 184, 0.35); padding: 2px 6px; border-radius: 9999px; }
  .improvements-list { display:flex; flex-direction:column; gap:6px; max-height:180px; overflow:auto; }
  .improvement-btn { width:100%; text-align:left; display:flex; flex-wrap:wrap; align-items:center; gap:8px; font-size:0.9rem; padding:6px 8px; border:1px solid transparent; border-radius:8px; background:rgba(15,23,42,0.02); color:inherit; }
  .improvement-btn:hover { border-color: rgba(148, 163, 184, 0.6); background: rgba(148, 163, 184, 0.16); }
  .imp-speaker { font-weight:600; }
  .imp-change { flex:1; min-width:150px; }
  .improvement-actions { display:flex; gap:6px; }
  .btn-pill { display:inline-flex; align-items:center; gap:6px; padding:4px 10px; border-radius:9999px; border:1px solid rgba(148, 163, 184, 0.4); background:transparent; color:inherit; font-size:0.75rem; }
  .btn-pill:hover { border-color: rgba(148, 163, 184, 0.8); background: rgba(148, 163, 184, 0.12); }
  .btn-pill--confirm { border-color: rgba(34, 197, 94, 0.6); color: #22c55e; }
  .btn-pill--confirm:hover { background: rgba(34, 197, 94, 0.15); }
  .btn-pill--reject { border-color: rgba(248, 113, 113, 0.6); color: #f87171; }
  .btn-pill--reject:hover { background: rgba(248, 113, 113, 0.18); }
  .btn-pill .icon { display:inline-flex; align-items:center; justify-content:center; font-size:0.85rem; }
  .badge { font-size:0.65rem; padding:2px 6px; border-radius:9999px; text-transform:uppercase; letter-spacing:0.05em; }
  .badge-context { background:#f97316; color:white; }
  .badge-open { background:#facc15; color:#1f2937; }
  .badge-confirmed { background:#22c55e; color:white; }
</style>
