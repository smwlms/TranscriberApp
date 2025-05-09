# src/constants.py

# Define constants used across the backend for clarity and easier management.

STATIC_FOLDER_NAME = "static"

# --- Job Status Constants ---
STATUS_QUEUED = "QUEUED"
STATUS_RUNNING = "RUNNING"
STATUS_PROCESSING_AUDIO = "PROCESSING_AUDIO"
STATUS_DETECTING_NAMES = "DETECTING_NAMES"
STATUS_WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
STATUS_MAPPING_SPEAKERS = "MAPPING_SPEAKERS"
STATUS_REFORMATTING = "REFORMATTING_HTML"
STATUS_ANALYZING = "ANALYZING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"
STATUS_STOPPED = "STOPPED"
STATUS_UNKNOWN = "UNKNOWN" # Added UNKNOWN for robustness

TERMINAL_STATUSES = [STATUS_COMPLETED, STATUS_FAILED, STATUS_STOPPED, STATUS_UNKNOWN]
STOPPABLE_STATUSES = [
    STATUS_QUEUED, STATUS_RUNNING, STATUS_PROCESSING_AUDIO,
    STATUS_DETECTING_NAMES, STATUS_WAITING_FOR_REVIEW,
    STATUS_MAPPING_SPEAKERS, STATUS_REFORMATTING, STATUS_ANALYZING
]


# --- Folder Names (Relative to Project Root) ---
AUDIO_FOLDER_NAME = "audio"
RESULTS_FOLDER_NAME = "results"
TRANSCRIPTS_FOLDER_NAME = "transcripts"


# --- Default & Intermediate File Names ---
# Intermediate files (used after Part 1)
INTERMEDIATE_TRANSCRIPT_JSON_FILENAME = "intermediate_transcript.json"
INTERMEDIATE_PROPOSED_MAP_FILENAME = "intermediate_proposed_map.json"
INTERMEDIATE_CONTEXT_SNIPPETS_FILENAME = "intermediate_context.json"

# Final result files (used after Part 2)
FINAL_TRANSCRIPT_JSON_FILENAME = "final_transcript.json"
FINAL_HTML_TRANSCRIPT_FILENAME = "transcript.html"
FINAL_SUMMARY_FILENAME = "summary.txt"
FINAL_ADVANCED_ANALYSIS_FILENAME = "advanced_analysis.json"
DEFAULT_SPEAKER_MAP_FILENAME = "speaker_map.yaml" # Used in DB logger config fallback


# --- Pipeline Progress Percentages ---
# Base progress is 0-100. These are markers within that range.
PROGRESS_START = 5
PROGRESS_AFTER_CONFIG = 10
PROGRESS_AFTER_VALIDATION = 15
PROGRESS_AFTER_AUDIO_PROCESSING = 75 # Increased as this is the main work
PROGRESS_AFTER_NAME_DETECT = 90
PROGRESS_WAITING_REVIEW = 95 # Progress before waiting for user input in Part 1
PROGRESS_AFTER_MAPPING = 50 # Progress marker in Part 2 after mapping
PROGRESS_AFTER_REFORMAT = 55 # Progress marker in Part 2 after HTML format
PROGRESS_AFTER_ANALYSIS = 95 # Progress marker in Part 2 after LLM analysis
PROGRESS_COMPLETE = 100 # Final state


# --- Database Constants ---
DEFAULT_DB_NAME = "llm_training_data.db"
JOB_RESULTS_TABLE_NAME = "job_results"


# --- Default Model Names ---
DEFAULT_WHISPER_MODEL = "small"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_PYANNOTE_PIPELINE = "pyannote/speaker-diarization-3.1"


# --- LLM Task Names (from advanced_tasks.py) ---
LLM_TASK_SUMMARY = "summary"
LLM_TASK_INTENT = "intent"
LLM_TASK_ACTIONS = "actions"
LLM_TASK_EMOTION = "emotion"
LLM_TASK_QUESTIONS = "questions"
LLM_TASK_LEGAL = "legal"
LLM_TASK_FINAL_ANALYSIS = "final_analysis" # Key used in final results dict

# List of advanced tasks keys for iteration if needed
LLM_ADVANCED_TASK_KEYS = [
    LLM_TASK_SUMMARY, LLM_TASK_INTENT, LLM_TASK_ACTIONS,
    LLM_TASK_EMOTION, LLM_TASK_QUESTIONS, LLM_TASK_LEGAL
]