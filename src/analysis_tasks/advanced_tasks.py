# src/analysis_tasks/advanced_tasks.py

import json # Keep json for potential future use with structured input/output
import traceback
from pathlib import Path # Keep Path for potential future use or type hints if needed
from typing import List, Dict, Optional, Any

# Import utilities
from src.utils.log import log
# Import the centralized LLM runner
from src.utils.llm import run_with_fallback

# --- Helper Function: Build Analysis Prompt ---
# (This function remains largely the same, but now receives text directly)

def _build_analysis_prompt(task_name: str, transcript_text: str, context: Optional[str] = None) -> str:
    """Builds a specific analysis prompt for the LLM based on the task and transcript text."""

    # Define base instructions for each analysis task - refine these prompts as needed for better results
    base_instructions = {
        "summary": "Provide a concise summary of the key discussion points, decisions, and outcomes from the following conversation transcript. Use bullet points for clarity.",
        "intent": "Analyze and describe the primary intentions, goals, or motivations of each speaker (if discernible) in the conversation transcript. What does each party seem to want to achieve?",
        "actions": "Identify and list all concrete action items, assigned tasks, or agreed-upon next steps mentioned in the transcript. Specify who is responsible if mentioned.",
        "emotion": "Analyze the overall tone and predominant emotions conveyed in the conversation. Consider aspects like frustration, agreement, urgency, enthusiasm, etc.",
        "questions": "Extract and list the most significant unanswered questions, points of confusion, or requests for clarification raised during the conversation.",
        "legal": "Identify any specific mentions of legal terms, contracts, agreements, compliance requirements, liabilities, or other potentially sensitive legal or contractual matters discussed.",
        # Add more task instructions here if extending functionality
    }

    # Use the specific instruction or a general default if task_name is unknown
    instruction = base_instructions.get(task_name, f"Perform a general analysis regarding '{task_name}' on the following conversation transcript.")

    # Construct the prompt parts systematically
    prompt_parts = []
    prompt_parts.append("You are an AI assistant specialized in analyzing conversation transcripts for business or professional contexts.")
    # Add user-provided context if available
    if context:
        prompt_parts.append(f"Consider the following context: {context.strip()}")

    # Add the specific task instruction
    prompt_parts.append(f"\nYour Task: {instruction}")
    # Add the transcript text, clearly demarcated
    prompt_parts.append("\n--- Start Transcript ---")
    prompt_parts.append(transcript_text) # Use the provided text string
    prompt_parts.append("--- End Transcript ---")
    # Final instruction for the LLM
    prompt_parts.append("\nProvide your analysis below:")

    return "\n".join(prompt_parts)


# --- Internal Helper to Run a Single Task ---

def _run_single_task(
    task_name: str,
    transcript_text: str, # Accepts text string directly
    config: dict,
    context: Optional[str] = None
    ) -> Optional[str]:
    """
    Internal helper to build prompt and run a single LLM analysis task on the provided text.

    Args:
        task_name: The key for the task (used for prompt building and model selection).
        transcript_text: The full transcript text as a single string.
        config: The job configuration dictionary.
        context: Optional user-provided context string.

    Returns:
        The analysis result string from the LLM, or None if the task failed.
    """
    log(f"Preparing LLM analysis task: '{task_name}'", "INFO")

    # Validate transcript text input
    if not transcript_text or not isinstance(transcript_text, str):
        log(f"Cannot run task '{task_name}': Invalid or empty transcript text provided.", "ERROR")
        return None

    # Build the specific prompt for this task using the text
    try:
        prompt = _build_analysis_prompt(task_name, transcript_text, context)
        log(f"Generated prompt for task '{task_name}' ({len(prompt)} chars).", "DEBUG")
    except Exception as e:
        log(f"Failed to build prompt for task '{task_name}': {e}", "ERROR")
        return None

    # Determine timeout from config (using default for now)
    timeout = config.get("llm_default_timeout")

    # Run the prompt using the centralized LLM runner with fallback logic
    # This uses the model list defined for 'task_name' in config['llm_models']
    llm_result = run_with_fallback(task_name, prompt, config, timeout=timeout)

    # Handle the result from the LLM call
    if llm_result is None:
        log(f"LLM analysis task '{task_name}' failed (run_with_fallback returned None).", "ERROR")
        return None # Failure
    else:
        log(f"LLM analysis task '{task_name}' completed successfully.", "SUCCESS")
        # Return the stripped result to remove potential leading/trailing whitespace
        return llm_result.strip()


# --- Public functions exposed by this module ---
# These functions now accept the transcript text directly.

def summary(transcript_text: str, config: dict, context: Optional[str] = None) -> Optional[str]:
    """Generates a summary of the transcript text using the 'summary' LLM configuration."""
    return _run_single_task("summary", transcript_text, config, context)

def intent(transcript_text: str, config: dict, context: Optional[str] = None) -> Optional[str]:
    """Analyzes speaker intentions from the text using the 'intent' LLM configuration."""
    return _run_single_task("intent", transcript_text, config, context)

def actions(transcript_text: str, config: dict, context: Optional[str] = None) -> Optional[str]:
    """Identifies action items from the text using the 'actions' LLM configuration."""
    return _run_single_task("actions", transcript_text, config, context)

def emotion(transcript_text: str, config: dict, context: Optional[str] = None) -> Optional[str]:
    """Analyzes conversation tone/emotions from text using the 'emotion' LLM configuration."""
    return _run_single_task("emotion", transcript_text, config, context)

def questions(transcript_text: str, config: dict, context: Optional[str] = None) -> Optional[str]:
    """Identifies key questions/concerns from text using the 'questions' LLM configuration."""
    return _run_single_task("questions", transcript_text, config, context)

def legal(transcript_text: str, config: dict, context: Optional[str] = None) -> Optional[str]:
    """Identifies legal mentions in the text using the 'legal' LLM configuration."""
    return _run_single_task("legal", transcript_text, config, context)


# --- Final Aggregating Analysis ---
# This function still accepts the dictionary of intermediate results.

def run_final_analysis(
    intermediate_results: Dict[str, Optional[str]],
    config: dict,
    context: Optional[str] = None
    ) -> Optional[str]:
    """
    Generates a final, comprehensive analysis by synthesizing the results
    from the intermediate analysis tasks.

    Args:
        intermediate_results: A dictionary containing the string results from previous
                              tasks (e.g., "summary", "intent"). Values can be None if a task failed.
        config: The job configuration dictionary (used for model/timeout selection).
        context: Optional user-provided context string relevant to the overall analysis.

    Returns:
        The final synthesized analysis string from the LLM, or None on failure.
    """
    log("Preparing final aggregating analysis prompt...", "INFO")

    # --- Build Prompt Using Intermediate Results ---
    prompt_parts = []
    prompt_parts.append("You are an AI assistant creating a final, synthesized analysis based on several preliminary analyses of a conversation transcript.")
    if context:
        prompt_parts.append(f"Consider this overall context: {context.strip()}")

    prompt_parts.append("\nHere are the results from the preliminary analyses (use 'Not available' if a section is missing):")
    # Include each intermediate result clearly labelled, handling None values
    prompt_parts.append(f"\n## Preliminary Summary:\n{intermediate_results.get('summary', 'Not available')}\n")
    prompt_parts.append(f"## Speaker Intentions/Goals:\n{intermediate_results.get('intent', 'Not available')}\n")
    prompt_parts.append(f"## Action Items/Decisions:\n{intermediate_results.get('actions', 'Not available')}\n")
    prompt_parts.append(f"## Tone/Emotion Analysis:\n{intermediate_results.get('emotion', 'Not available')}\n")
    prompt_parts.append(f"## Key Questions/Concerns:\n{intermediate_results.get('questions', 'Not available')}\n")
    prompt_parts.append(f"## Legal/Contractual Mentions:\n{intermediate_results.get('legal', 'Not available')}\n")

    # --- Instructions for Final Analysis ---
    prompt_parts.append("---")
    prompt_parts.append("\nYour Task: Based *only* on the preliminary analyses provided above, synthesize these findings into a single, cohesive final report.")
    prompt_parts.append("Do not refer back to the original transcript data. Your goal is to integrate the provided pieces into a meaningful overview.")
    prompt_parts.append("Highlight the most critical aspects, potential risks or opportunities apparent from the combined analyses, and any logical next steps or conclusions that can be drawn.")
    prompt_parts.append("Structure your response logically (e.g., using clear paragraphs or thematic sections).")
    prompt_parts.append("\nFinal Synthesized Analysis:")

    prompt = "\n".join(prompt_parts)
    log(f"Generated prompt for final analysis ({len(prompt)} chars).", "DEBUG")

    # --- Run Final Analysis LLM ---
    task_name = "final" # Use the 'final' task key for model selection
    # Determine timeout: check for specific final timeout, fallback to default
    timeout = config.get("llm_final_analysis_timeout", config.get("llm_default_timeout"))

    final_result = run_with_fallback(task_name, prompt, config, timeout=timeout)

    # --- Handle Result ---
    if final_result is None:
        log(f"Final aggregating analysis task ('{task_name}') failed.", "ERROR")
        return None
    else:
        log(f"Final aggregating analysis task ('{task_name}') completed successfully.", "SUCCESS")
        return final_result.strip() # Return stripped result


# Example usage block (needs adaptation if run standalone)
if __name__ == "__main__":
    print("-" * 40)
    print("--- Testing Advanced Analysis Tasks (Refactored) ---")
    print("Note: This test block requires manual setup or mocking.")
    print("-" * 40)

    # This block now requires transcript *text* and a loaded config dictionary.
    # Mock data for demonstration:
    mock_transcript_text = """Speaker A: We need to finalize the Q3 report.
Speaker B: Agreed. I'll compile the sales data by tomorrow. Is the template ready?
Speaker A: Yes, I sent it yesterday. Are there any legal concerns with the new partner agreement mentioned last week?
Speaker B: I don't think so, but let's have legal double-check paragraph 5 just to be safe."""

    # Mock or load a config dictionary (ensure llm_models section exists)
    # You would typically use load_config() here if running within the project context
    try:
        from src.utils.load_config import load_config
        test_config = load_config()
        if not test_config.get("llm_models"):
             print("WARNING: 'llm_models' not found in config. Providing mock models.")
             test_config["llm_models"] = {
                 "summary": ["mock-model"], "intent": ["mock-model"], "actions": ["mock-model"],
                 "emotion": ["mock-model"], "questions": ["mock-model"], "legal": ["mock-model"],
                 "final": ["mock-model"]
             }
    except ImportError:
         print("WARNING: Could not load config. Using mock config.")
         test_config = {"llm_models": {"summary": ["mock-model"], "intent": ["mock-model"], "actions": ["mock-model"], "emotion": ["mock-model"], "questions": ["mock-model"], "legal": ["mock-model"], "final": ["mock-model"]}}

    # Setup basic logging
    try:
         from src.utils.log import setup_logging; import logging
         setup_logging(level=logging.DEBUG)
    except ImportError: print("Skipping logger setup.")


    print("\nRunning individual tasks with mock text (requires working LLM setup to get real results):")
    print(f"Input Text Snippet:\n---\n{mock_transcript_text[:100]}...\n---")

    # Run one task as an example
    summary_result = summary(mock_transcript_text, test_config, context="Internal project meeting")
    print("\n--- Example Task Result (Summary) ---")
    print(summary_result or "Task failed or returned None (check Ollama connection and model availability).")

    # Example for final analysis (using mock intermediate results)
    print("\n--- Testing Final Analysis (with mock intermediate results) ---")
    mock_intermediate = {
        "summary": "Q3 report needs finalizing. Sales data due tomorrow. Template sent.",
        "intent": "A wants report done, B agrees to provide data.",
        "actions": "B to compile sales data by tomorrow. Legal to double-check paragraph 5 of partner agreement.",
        "emotion": "Task-oriented, collaborative.",
        "questions": "Is the template ready? Any legal concerns with partner agreement?",
        "legal": "Mention of partner agreement paragraph 5, requires legal check."
    }
    final_analysis_result = run_final_analysis(mock_intermediate, test_config, context="Internal project meeting")
    print("\nFinal Synthesized Analysis Result:")
    print(final_analysis_result or "Final analysis task failed or returned None.")

    print("-" * 40)
    print("--- Testing Complete ---")
    print("-" * 40)