# src/job_manager.py

import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Tuple

# Import log directly (assuming log.py is available)
from src.utils.log import log

# --- Status Constants ---
# Define possible job status constants for consistency and clarity
STATUS_QUEUED = "QUEUED"             # Job created, waiting to start
STATUS_RUNNING = "RUNNING"           # Generic running state (used by Part 1 start)
STATUS_PROCESSING_AUDIO = "PROCESSING_AUDIO" # ** NEW: Covers combined Transcription & Diarization step **
STATUS_DETECTING_NAMES = "DETECTING_NAMES" # Optional step after audio processing
STATUS_WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW" # Paused for user input
STATUS_MAPPING_SPEAKERS = "MAPPING_SPEAKERS"   # Step after review
STATUS_REFORMATTING = "REFORMATTING_HTML"    # Step after mapping
STATUS_ANALYZING = "ANALYZING"         # LLM analysis step
STATUS_COMPLETED = "COMPLETED"         # Successfully finished
STATUS_FAILED = "FAILED"               # Finished with an error
STATUS_STOPPED = "STOPPED"             # Explicitly stopped by user request

class JobManager:
    """
    Manages the state and lifecycle of background processing jobs in memory.
    Designed for thread-safe access in multi-threaded applications like a web server.
    Acts as a central repository for job information accessible across threads.
    """
    def __init__(self):
        """Initializes the JobManager with an empty job dictionary and a lock."""
        # The main dictionary holding all job data, keyed by job_id (string UUID)
        self._jobs: Dict[str, Dict[str, Any]] = {}
        # Use a Reentrant Lock (RLock) to allow the same thread to acquire the lock multiple times if needed
        self._lock = threading.RLock()
        log(f"JobManager Initialized (Instance ID: {id(self)})", "DEBUG")

    def create_job(self, initial_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Creates a new job entry with a unique ID and initializes its state.

        Args:
            initial_config: Optional dictionary containing the configuration used for this job.

        Returns:
            The unique job ID (UUID string) for the newly created job.
        """
        job_id = str(uuid.uuid4()) # Generate a unique identifier
        with self._lock: # Ensure exclusive access for modification
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": STATUS_QUEUED,
                "progress": 0, # Percentage (0-100)
                "logs": [],    # List to store (timestamp, level, message) tuples
                "result": None,# To store final results upon completion
                "error_message": None, # To store error details on failure
                "start_time": None,    # Timestamp (float) when processing actually starts
                "end_time": None,      # Timestamp (float) when processing finishes (any state)
                "stop_requested": False, # Flag to signal graceful shutdown request
                "config": initial_config or {}, # Store config used for this specific job
                "review_data_paths": {}, # Paths needed for review (set by Part 1)
            }
            log(f"Created job '{job_id}' with initial status '{STATUS_QUEUED}'.", "INFO")
        return job_id

    def _update_job_state(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """
        Internal helper method to update multiple fields of a job's state thread-safely.
        Handles automatic setting of start/end timestamps based on status changes.

        Args:
            job_id: The ID of the job to update.
            updates: A dictionary containing the key-value pairs to update.

        Returns:
            True if the update was successful, False if the job_id was not found.
        """
        with self._lock: # Acquire lock for safe read-modify-write operation
            job_state = self._jobs.get(job_id)
            if not job_state:
                log(f"Attempted to update non-existent job '{job_id}'. Update ignored.", "WARNING")
                return False # Job not found

            log(f"Updating job '{job_id}': {updates}", "DEBUG") # Log the specific updates being applied

            # --- Automatic Start Time ---
            # Set start_time only if it's currently None and the job is entering a running state
            # or showing progress > 0 for the first time.
            running_statuses = [
                STATUS_RUNNING, STATUS_PROCESSING_AUDIO, STATUS_DETECTING_NAMES,
                STATUS_MAPPING_SPEAKERS, STATUS_REFORMATTING, STATUS_ANALYZING
            ]
            if job_state.get("start_time") is None:
                is_starting = ("status" in updates and updates["status"] in running_statuses) or \
                              ("progress" in updates and updates.get("progress", 0) > 0)
                if is_starting:
                    job_state["start_time"] = time.time()
                    log(f"Job '{job_id}' processing started. Start time set.", "DEBUG")

            # --- Apply Updates Provided ---
            job_state.update(updates)

            # --- Automatic End Time ---
            # Set end_time only if it's currently None and the job is entering a terminal state.
            terminal_states = [STATUS_COMPLETED, STATUS_FAILED, STATUS_STOPPED]
            if "status" in updates and updates["status"] in terminal_states and job_state.get("end_time") is None:
                job_state["end_time"] = time.time()
                log(f"Job '{job_id}' reached terminal state '{updates['status']}'. End time set.", "DEBUG")

            return True # Update successful

    def update_status(self, job_id: str, status: str):
        """Updates only the status field of a specific job."""
        if not self._update_job_state(job_id, {"status": status}):
             log(f"Failed to update status for job '{job_id}' (job not found?).", "WARNING")

    def update_progress(self, job_id: str, progress: int, status: Optional[str] = None):
        """Updates the progress percentage (0-100) and optionally the status."""
        # Ensure progress is an integer and clamped between 0 and 100
        clamped_progress = max(0, min(100, int(progress)))
        updates = {"progress": clamped_progress}
        # Optionally update the status message along with the progress
        if status:
            updates["status"] = status
        if not self._update_job_state(job_id, updates):
            log(f"Failed to update progress for job '{job_id}' (job not found?).", "WARNING")

    def add_log(self, job_id: str, message: str, level: str = "INFO"):
        """Adds a timestamped log entry to the specific job's internal log list."""
        # Quick check outside lock for minor optimization (job existence)
        if job_id not in self._jobs:
            log(f"Attempted to add log to non-existent job '{job_id}'.", "WARNING")
            return

        log_entry = (time.time(), level.upper(), message) # Create log tuple

        with self._lock: # Acquire lock to safely modify the job's log list
            job_state = self._jobs.get(job_id)
            # Check job exists and 'logs' is actually a list inside the lock
            if job_state and isinstance(job_state.get("logs"), list):
                 job_state["logs"].append(log_entry)
                 # Avoid logging the log addition itself unless absolutely needed for debugging
                 # log(f"Added log to job '{job_id}': [{level.upper()}] {message}", "DEBUG")
            elif job_state:
                 # This indicates potential state corruption
                 log(f"Cannot add log to job '{job_id}': 'logs' field is not a list ({type(job_state.get('logs'))}).", "ERROR")
            # Else: Job disappeared between outer check and lock (rare), or outer check logged.

    def set_result(self, job_id: str, result_data: Any):
        """Sets the final result data and marks the job as COMPLETED."""
        log(f"Setting final result for completed job '{job_id}'.", "INFO")
        if not self._update_job_state(job_id, {"result": result_data, "status": STATUS_COMPLETED, "progress": 100}):
             log(f"Failed to set result for job '{job_id}' (job not found?).", "WARNING")

    def set_error(self, job_id: str, error_message: str):
        """Sets the error message and marks the job as FAILED."""
        log(f"Setting error for failed job '{job_id}': {error_message}", "ERROR")
        # Optionally reset progress on failure
        if not self._update_job_state(job_id, {"error_message": error_message, "status": STATUS_FAILED, "progress": 0}):
             log(f"Failed to set error for job '{job_id}' (job not found?).", "WARNING")

    def request_stop(self, job_id: str) -> bool:
        """
        Flags a job requesting it to stop processing gracefully.
        The running pipeline task needs to periodically check `is_stop_requested`.

        Returns:
            True if the stop request flag was successfully set (or already set),
            False if the job was not found or not in a stoppable state.
        """
        with self._lock: # Lock needed for consistent read-modify-write
            job_state = self._jobs.get(job_id)
            if not job_state:
                 log(f"Stop request failed: Job ID '{job_id}' not found.", "WARNING")
                 return False

            current_status = job_state.get("status")
            # Define states where stopping is considered applicable
            # ** UPDATED list including new/removing old statuses **
            stoppable_states = [
                STATUS_QUEUED, STATUS_RUNNING, STATUS_PROCESSING_AUDIO,
                STATUS_DETECTING_NAMES, STATUS_WAITING_FOR_REVIEW,
                STATUS_MAPPING_SPEAKERS, STATUS_REFORMATTING, STATUS_ANALYZING
            ]

            # Check if the job is currently in a state that can be stopped
            if current_status not in stoppable_states:
                 log(f"Stop request ignored for job '{job_id}': Status '{current_status}' is not stoppable.", "WARNING")
                 return False # Cannot stop a job that's not actively processing or queued

            # Set the flag if job is stoppable and flag isn't already set
            if not job_state.get("stop_requested"):
                 log(f"Processing stop request for job '{job_id}'...", "INFO")
                 job_state["stop_requested"] = True
                 return True # Flag successfully set
            else:
                 # If already requested, still return True as the desired state is met
                 log(f"Stop already requested for job '{job_id}'.", "DEBUG")
                 return True

    def is_stop_requested(self, job_id: str) -> bool:
        """Checks if a stop request has been flagged for the specified job."""
        with self._lock: # Read access also needs lock for consistency against updates
            job_state = self._jobs.get(job_id)
            # Return the flag's value, defaulting to False if job doesn't exist
            return job_state.get("stop_requested", False) if job_state else False

    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a copy of the current state dictionary for a specific job.

        Returns:
            A shallow copy of the job's state dictionary, or None if the job_id is not found.
        """
        with self._lock: # Acquire lock for safe read
            job_state = self._jobs.get(job_id)
            # Return a shallow copy to prevent external modification of the internal state
            return job_state.copy() if job_state else None

    def list_jobs(self) -> List[Dict[str, Any]]:
         """
         Returns a list containing a summary dictionary for all current jobs.
         Useful for an overview display (e.g., in a UI). Returns copies of data.
         """
         job_list: List[Dict[str, Any]] = []
         with self._lock: # Ensure a consistent snapshot of all jobs
             # Create list of job summaries inside the lock
             for jid, data in self._jobs.items():
                 # Include key information relevant for a list view
                 job_summary = {
                     "job_id": jid,
                     "status": data.get("status"),
                     "progress": data.get("progress"),
                     "start_time": data.get("start_time"),
                     "end_time": data.get("end_time"),
                     "stop_requested": data.get("stop_requested"),
                     "error_message": data.get("error_message"),
                     # Example: Include input file from config for context
                     "input_audio": data.get("config", {}).get("input_audio")
                 }
                 job_list.append(job_summary)
         # Return the list created while the lock was held
         return job_list


# --- Singleton Instance ---
# Create a single, globally accessible instance of the JobManager.
# Other modules should import this instance: from src.job_manager import job_manager
job_manager = JobManager()

# --- Example Usage / Test Block ---
if __name__ == "__main__":
    # Import necessary modules for testing only within this block
    from src.utils.log import setup_logging
    import logging
    import json # Import json for pretty printing test output

    print("-" * 40); print("--- Testing Job Manager ---"); print("-" * 40)
    # Setup logging to see JobManager's internal logs during the test
    setup_logging(level=logging.DEBUG)

    # Test job creation and basic updates
    test_job_id_1 = job_manager.create_job({"model": "test_model_1", "input_audio": "test1.mp3"})
    print(f"\nCreated job 1: {test_job_id_1}")
    status_1 = job_manager.get_status(test_job_id_1)
    print(f"Initial status job 1:\n{json.dumps(status_1, indent=2)}")

    print("\nUpdating job 1 progress and status...")
    job_manager.update_progress(test_job_id_1, 30, STATUS_PROCESSING_AUDIO) # Use new status
    job_manager.add_log(test_job_id_1, "Audio processing started.")
    time.sleep(0.1) # Simulate work
    job_manager.update_progress(test_job_id_1, 60, STATUS_ANALYZING)
    job_manager.add_log(test_job_id_1, "Analysis started.")
    print(f"Updated status job 1:\n{json.dumps(job_manager.get_status(test_job_id_1), indent=2)}")

    print("\nSetting job 1 result...")
    job_manager.set_result(test_job_id_1, {"output_path": "results/test1.html", "analysis_score": 0.85})
    print(f"Final status job 1:\n{json.dumps(job_manager.get_status(test_job_id_1), indent=2)}")

    # Test job failure
    print("-" * 40)
    test_job_id_2 = job_manager.create_job({"model": "test_model_2", "input_audio": "test2.wav"})
    print(f"\nCreated job 2: {test_job_id_2}")
    print("\nSetting job 2 error...")
    job_manager.set_error(test_job_id_2, "LLM model not available during analysis.")
    print(f"Final status job 2:\n{json.dumps(job_manager.get_status(test_job_id_2), indent=2)}")

    # Test job listing
    print("-" * 40)
    print("\nListing all jobs (summary):")
    all_jobs = job_manager.list_jobs()
    print(json.dumps(all_jobs, indent=2))
    print("-" * 40)

    # Test stop request logic
    test_job_id_3 = job_manager.create_job({"input_audio": "stoppable.mp3"})
    print(f"\nCreated job 3: {test_job_id_3}")
    job_manager.update_status(test_job_id_3, STATUS_ANALYZING) # Put in a stoppable state
    print(f"Job 3 Status: {job_manager.get_status(test_job_id_3)['status']}")
    print(f"Requesting stop for job 3 (should succeed): {job_manager.request_stop(test_job_id_3)}")
    print(f"Is stop requested for job 3? {job_manager.is_stop_requested(test_job_id_3)}")
    print(f"Requesting stop again for job 3 (should return True, already requested): {job_manager.request_stop(test_job_id_3)}")
    # Test stopping a completed job
    print(f"Requesting stop for job 1 (COMPLETED, should fail/return False): {job_manager.request_stop(test_job_id_1)}")
    # Test stopping a failed job
    print(f"Requesting stop for job 2 (FAILED, should fail/return False): {job_manager.request_stop(test_job_id_2)}")
    print("-" * 40)
    print("--- Job Manager Testing Complete ---")
    print("-" * 40)