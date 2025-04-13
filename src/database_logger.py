# src/database_logger.py
import json
import traceback # Keep json for dumps
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import time

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, Float, DateTime, insert, inspect, select # Added select

# Use the configured logger
from src.utils.log import log
from src.utils.load_config import load_config

# Assuming PROJECT_ROOT is defined consistently
try:
    from src.utils.config_schema import PROJECT_ROOT
except ImportError:
    # Fallback if import fails during early stages
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    log("WARNING: Could not import PROJECT_ROOT from config_schema in database_logger, using fallback.", "WARNING")


# --- Constants ---
DEFAULT_DB_NAME = "llm_training_data.db"
DEFAULT_DB_PATH = PROJECT_ROOT / DEFAULT_DB_NAME
JOB_RESULTS_TABLE_NAME = "job_results"
DEFAULT_SPEAKER_MAP_FILENAME = "speaker_map.yaml" # Default filename if not specified in config

# --- Table Definition ---
metadata = MetaData()

job_results_table = Table(
    JOB_RESULTS_TABLE_NAME,
    metadata,
    Column("id", Integer, primary_key=True),
    Column("job_id", String, unique=True, index=True, nullable=False),
    Column("audio_relative_path", Text, nullable=False),
    Column("processing_start_time", DateTime),
    Column("processing_end_time", DateTime),
    Column("duration_seconds", Float),
    Column("status", String),
    Column("error_message", Text),
    # --- Configuration Used ---
    Column("config_whisper_model", String),
    Column("config_compute_type", String),
    Column("config_language", String),
    Column("config_mode", String),
    Column("config_speaker_map_path", Text),
    Column("config_llm_context_prompt", Text),
    # --- Results ---
    Column("result_speaker_mapping_json", Text), # JSON dump
    Column("result_transcript_json", Text),      # JSON dump
    Column("result_transcript_html_path", Text),
    Column("result_llm_summary", Text),
    Column("result_llm_intent", Text),
    Column("result_llm_actions", Text),
    Column("result_llm_emotion", Text),
    Column("result_llm_questions", Text),
    Column("result_llm_legal", Text),
    Column("result_llm_final_analysis", Text),
    Column("result_advanced_analysis_path", Text),
    Column("result_summary_path", Text),
    Column("result_raw_transcript_path", Text) # Path to intermediate transcript used for analysis
)

# --- Engine Cache ---
_engines: Dict[Path, Any] = {}

def get_engine(db_path: Path):
    """Returns (or creates and caches) a SQLAlchemy engine for the given database path."""
    global _engines
    if db_path not in _engines:
        try:
            # Use 'future=True' for SQLAlchemy 2.0 style compatibility
            _engines[db_path] = create_engine(f"sqlite:///{db_path}", future=True)
            log(f"Database engine created for: {db_path}", "DEBUG")
        except Exception as e:
            log(f"Failed to create database engine for {db_path}: {e}", "CRITICAL")
            raise # Re-raise the exception after logging
    return _engines[db_path]

# --- Database Path Determination ---
def get_db_path(config: Optional[Dict[str, Any]] = None) -> Path:
    """
    Determines the path for the SQLite database file based on configuration.

    Args:
        config: The configuration dictionary (optional). If None, loads the default config.

    Returns:
        A Path object pointing to the database file.
    """
    if config is None:
        try:
            config = load_config()
        except Exception as e:
            log(f"Failed to load config in get_db_path, using default DB name. Error: {e}", "WARNING")
            config = {} # Use empty dict to proceed with default name

    db_filename = config.get("database_filename", DEFAULT_DB_NAME)
    db_path_config = Path(db_filename)

    # Return absolute path if provided, otherwise resolve relative to project root
    if db_path_config.is_absolute():
        return db_path_config
    else:
        return PROJECT_ROOT / db_filename

# --- Database Initialization ---
def initialize_database(db_path: Optional[Path] = None) -> bool:
    """
    Initializes the SQLite database connection and creates the results table if it doesn't exist.

    Args:
        db_path: Path to the database file. If None, determined via config/default.

    Returns:
        True if initialization was successful or DB/table already exists, False on error.
    """
    if db_path is None:
        try:
            db_path = get_db_path()
        except Exception as e:
             log(f"Failed to determine DB path during initialization: {e}", "ERROR")
             return False

    log(f"Initializing database connection and schema at: {db_path}", "INFO")
    try:
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        engine = get_engine(db_path) # Get or create engine
        with engine.connect() as connection: # Test connection
            inspector = inspect(engine)
            if not inspector.has_table(JOB_RESULTS_TABLE_NAME):
                log(f"Table '{JOB_RESULTS_TABLE_NAME}' not found. Creating table...", "INFO")
                metadata.create_all(engine) # Create table(s) defined in metadata
                log(f"Table '{JOB_RESULTS_TABLE_NAME}' created successfully.", "SUCCESS")
            else:
                log(f"Table '{JOB_RESULTS_TABLE_NAME}' already exists.", "INFO")
        return True
    except Exception as e:
        log(f"Failed to initialize database at '{db_path}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log full traceback for debugging
        return False

# --- Logging Job Data ---

# Define mappings for clarity and maintainability
CONFIG_KEY_TO_COLUMN = {
    "whisper_model": "config_whisper_model",
    "compute_type": "config_compute_type",
    "language": "config_language",
    "mode": "config_mode",
    "speaker_map_path": "config_speaker_map_path", # Keep this mapping explicit
    "extra_context_prompt": "config_llm_context_prompt",
    "input_audio": "audio_relative_path", # Map from config to top-level column
}

RESULT_KEY_TO_COLUMN = {
    "html_transcript_path": "result_transcript_html_path",
    "summary_content": "result_llm_summary",
    "intent_result": "result_llm_intent",
    "actions_result": "result_llm_actions",
    "emotion_result": "result_llm_emotion",
    "questions_result": "result_llm_questions",
    "legal_result": "result_llm_legal",
    "final_analysis_result": "result_llm_final_analysis",
    "advanced_analysis_path": "result_advanced_analysis_path",
    "summary_path": "result_summary_path",
    "intermediate_transcript_path": "result_raw_transcript_path", # Path to raw transcript used for analysis
    # Note: JSON fields (final_transcript_segments, speaker_mapping_used) are handled separately
}


def log_job_to_db(job_data: Dict[str, Any], db_path: Optional[Path] = None) -> bool:
    """
    Logs the relevant data from a completed or failed job into the database.

    Args:
        job_data: The job status dictionary (expected keys: 'job_id', 'status', 'config',
                  'result', 'start_time', 'end_time', 'error_message', etc.).
        db_path: Path to the database file. If None, determined via config/default.

    Returns:
        True if logging was successful (or skipped due to existing entry), False otherwise.
    """
    job_id = job_data.get("job_id")
    if not job_id:
        log("DB Log: Missing 'job_id', cannot log job.", "ERROR")
        return False

    # Determine DB path using the config associated with *this specific job*
    job_config = job_data.get("config", {})
    if db_path is None:
        try:
            db_path = get_db_path(job_config) # Pass job's config
        except Exception as e:
             log(f"DB Log: Failed to determine DB path for job '{job_id}': {e}", "ERROR")
             return False

    log(f"DB Log: Attempting to log job '{job_id}' to DB: {db_path.name}", "INFO")

    # Ensure DB is initialized before proceeding
    if not initialize_database(db_path):
        log(f"DB Log: Database initialization failed for '{job_id}'. Aborting log attempt.", "ERROR")
        return False

    # --- Prepare Data for Insertion ---
    insert_data = {}
    result_dict = job_data.get("result", {}) or {} # Ensure result is a dict, even if None/empty

    # Basic Job Info
    insert_data["job_id"] = job_id
    insert_data["status"] = job_data.get("status")
    insert_data["error_message"] = job_data.get("error_message")

    # Timestamps and Duration
    start_time = job_data.get("start_time")
    end_time = job_data.get("end_time")
    insert_data["processing_start_time"] = datetime.fromtimestamp(start_time) if start_time else None
    insert_data["processing_end_time"] = datetime.fromtimestamp(end_time) if end_time else None
    insert_data["duration_seconds"] = (end_time - start_time) if start_time and end_time else None

    # Map Config values using the mapping dictionary
    for config_key, col_name in CONFIG_KEY_TO_COLUMN.items():
        # Handle speaker_map_path explicitly using default if not in config
        if config_key == "speaker_map_path":
            insert_data[col_name] = job_config.get(config_key, DEFAULT_SPEAKER_MAP_FILENAME)
        else:
            insert_data[col_name] = job_config.get(config_key)

    # Map Result values using the mapping dictionary
    for result_key, col_name in RESULT_KEY_TO_COLUMN.items():
        insert_data[col_name] = result_dict.get(result_key)

    # Handle JSON serialization separately for specific fields
    try:
        final_transcript_data = result_dict.get("final_transcript_segments")
        insert_data["result_transcript_json"] = json.dumps(final_transcript_data, ensure_ascii=False) if final_transcript_data else None
    except Exception as e:
        log(f"DB Log: Could not serialize transcript segments for '{job_id}': {e}", "WARNING")
        insert_data["result_transcript_json"] = None # Store null on serialization error
    try:
        speaker_map_data = result_dict.get("speaker_mapping_used")
        insert_data["result_speaker_mapping_json"] = json.dumps(speaker_map_data, ensure_ascii=False) if speaker_map_data else None
    except Exception as e:
        log(f"DB Log: Could not serialize speaker mapping for '{job_id}': {e}", "WARNING")
        insert_data["result_speaker_mapping_json"] = None # Store null on serialization error


    # --- Execute Database Insert ---
    try:
        engine = get_engine(db_path)
        with engine.connect() as connection:
            # Check if job_id already exists before inserting to prevent duplicates
            stmt_check = select(job_results_table.c.id).where(job_results_table.c.job_id == job_id).limit(1)
            if connection.execute(stmt_check).first():
                log(f"DB Log: Job '{job_id}' already exists in the database. Skipping insert.", "INFO")
                return True # Considered successful as the data is present

            # Perform the insert if job_id is not found
            stmt_insert = insert(job_results_table).values(**insert_data)
            result_proxy = connection.execute(stmt_insert)
            connection.commit() # Commit the transaction
            inserted_id = result_proxy.inserted_primary_key[0] if result_proxy.inserted_primary_key else 'N/A'
            log(f"DB Log: Job '{job_id}' logged successfully to DB (Record ID: {inserted_id}).", "SUCCESS")
            return True
    except Exception as e:
        log(f"DB Log: Failed to log job '{job_id}' to database '{db_path.name}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log full traceback for debugging database errors
        return False

# --- End of database_logger.py ---