#!/usr/bin/env bash
# =============================================================================
# run_analysis.sh
#
# Draai alle advanced analyses op een bestaand intermediate_transcript.json,
# en gebruik de context uit config.yaml (extra_context_prompt).
# =============================================================================

# Pas deze paden aan indien nodig:
CONFIG_PATH="/Users/samuelwillems/Documents/GitHub/TranscriberApp/config.yaml"
TRANSCRIPT_JSON="/Users/samuelwillems/Documents/GitHub/TranscriberApp/transcripts/intermediate_transcript.json"

python3 <<PYCODE
import yaml, json, sys
from src.analysis_tasks.advanced_tasks import (
    summary,
    intent,
    actions,
    emotion,
    questions,
    legal,
    run_final_analysis
)

# --- Laad config ---
try:
    config = yaml.safe_load(open("$CONFIG_PATH", encoding="utf-8"))
except Exception as e:
    print(f"❌ Kon config niet laden: {e}")
    sys.exit(1)

# --- Haal context uit config ---
ctx = config.get("extra_context_prompt", "")
if not ctx:
    print("ℹ️ Geen 'extra_context_prompt' gevonden in config.yaml, geen extra context toegepast.")

# --- Laad transcript JSON en bepaal segments ---
try:
    raw = json.load(open("$TRANSCRIPT_JSON", encoding="utf-8"))
    if isinstance(raw, dict) and "intermediate_transcript" in raw:
        segments = raw["intermediate_transcript"]
    elif isinstance(raw, list):
        segments = raw
    else:
        # fallback: misschien geneste structuur
        segments = raw.get("segments", raw) if isinstance(raw, dict) else raw
except Exception as e:
    print(f"❌ Kon transcript JSON niet laden: {e}")
    sys.exit(1)

# --- Bouw platte tekst van segments ---
try:
    parts = []
    for seg in segments:
        if isinstance(seg, dict):
            words = seg.get("words")
            if isinstance(words, list) and words:
                parts.append(" ".join(w.get("word","") for w in words))
            else:
                # val terug op 'text' of 'text' key
                parts.append(seg.get("text", ""))
        else:
            # als segment geen dict is, zet direct om naar str
            parts.append(str(seg))
    transcript_text = "\n".join(parts)
except Exception as e:
    print(f"❌ Kon transcript verwerken: {e}")
    sys.exit(1)

# --- Voer per-task analyses uit ---
intermediate = {}
for fn in [summary, intent, actions, emotion, questions, legal]:
    name = fn.__name__
    print(f"\n{'='*10} {name.upper()} {'='*10}\n")
    try:
        res = fn(transcript_text, config, ctx)
        print(res or "")
    except Exception as e:
        print(f"❌ {name} task failed: {e}")
        res = None
    intermediate[name] = res

# --- Final Aggregated Analysis ---
print(f"\n{'='*10} FINAL ANALYSIS {'='*10}\n")
try:
    final = run_final_analysis(intermediate_results=intermediate, config=config, context=ctx)
    print(final or "")
except Exception as e:
    print(f"❌ Final analysis failed: {e}")

PYCODE
