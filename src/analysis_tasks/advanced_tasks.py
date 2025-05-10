# src/analysis_tasks/advanced_tasks.py

import json  # Keep json for potential future use with structured input/output
import traceback
from pathlib import Path  # Keep Path for potential future use or type hints if needed
from typing import List, Dict, Optional, Any

# Import utilities
from src.utils.log import log
# Import the centralized LLM runner
from src.utils.llm import run_with_fallback

# --- Helper Function: Build Analysis Prompt ---

def _build_analysis_prompt(task_name: str, transcript_text: str, context: Optional[str] = None) -> str:
    """
    Builds a specific analysis prompt for the LLM based on the task and transcript text,
    with concrete, checklist-style instructions for improved focus and structure.
    """

    # More concrete instructions per task, with checklists
    base_instructions = {
        "summary": (
            "Write a clear and structured summary of the conversation below. Use bullet points or "
            "short paragraphs. Include:\n"
            "- Main discussion topics\n"
            "- Key proposals or ideas\n"
            "- Concrete decisions made\n"
            "- Any disagreements or points of confusion"
        ),
        "intent": (
            "For each speaker, infer and describe their primary intentions or goals. "
            "Use bullet points and group insights per speaker."
        ),
        "actions": (
            "Identify and list all concrete action items or next steps. "
            "Start each bullet with an action verb and group items by responsible speaker if possible."
        ),
        "emotion": (
            "Analyze the overall tone and predominant emotions in the conversation. "
            "Mention specific examples or phrases that illustrate each emotion."
        ),
        "questions": (
            "Extract and list the most significant unanswered questions or requests for clarification. "
            "Present them as bullet points."
        ),
        "legal": (
            "Identify any legal or contractual mentions (e.g., agreements, compliance requirements). "
            "Summarize their relevance and any actions needed."
        ),
        # Add more task instructions here if extending functionality
    }

    # Fallback for unknown tasks
    instruction = base_instructions.get(
        task_name,
        f"Perform a focused analysis on '{task_name}' for the conversation below, using bullet points where possible."
    )

    # Assemble the prompt
    prompt_parts: List[str] = []
    prompt_parts.append("You are an AI assistant specialized in analyzing conversation transcripts for business or professional contexts.")
    if context:
        prompt_parts.append(f"Consider the following context and roles: {context.strip()}")

    prompt_parts.append(f"\nYour Task: {instruction}")
    prompt_parts.append("\n--- Start Transcript ---")
    prompt_parts.append(transcript_text)
    prompt_parts.append("--- End Transcript ---")
    prompt_parts.append("\nPlease provide your analysis according to the above instructions:")

    return "\n".join(prompt_parts)


# --- Internal Helper to Run a Single Task ---

def _run_single_task(
    task_name: str,
    transcript_text: str,  # Accepts text string directly
    config: dict,
    context: Optional[str] = None
) -> Optional[str]:
    """
    Internal helper to build prompt and run a single LLM analysis task on the provided text.
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
    llm_result = run_with_fallback(task_name, prompt, config, timeout=timeout)

    if llm_result is None:
        log(f"LLM analysis task '{task_name}' failed (run_with_fallback returned None).", "ERROR")
        return None
    else:
        log(f"LLM analysis task '{task_name}' completed successfully.", "SUCCESS")
        return llm_result.strip()


# --- Public functions exposed by this module ---

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

def run_final_analysis(
    intermediate_results: Dict[str, Optional[str]],
    config: dict,
    context: Optional[str] = None
) -> Optional[str]:
    """
    Generates a final, comprehensive analysis by synthesizing the results
    from the intermediate analysis tasks.
    """
    log("Preparing final aggregating analysis prompt...", "INFO")

    # Build Prompt Using Intermediate Results
    prompt_parts: List[str] = []
    prompt_parts.append("You are an AI assistant creating a final, synthesized analysis based on several preliminary analyses of a conversation transcript.")
    if context:
        prompt_parts.append(f"Use the participant context and roles: {context.strip()}")

    prompt_parts.append("\nHere are the results from the preliminary analyses (use 'Not available' if a section is missing):")
    prompt_parts.append(f"\n## Preliminary Summary:\n{intermediate_results.get('summary', 'Not available')}\n")
    prompt_parts.append(f"## Speaker Intentions/Goals:\n{intermediate_results.get('intent', 'Not available')}\n")
    prompt_parts.append(f"## Action Items/Decisions:\n{intermediate_results.get('actions', 'Not available')}\n")
    prompt_parts.append(f"## Tone/Emotion Analysis:\n{intermediate_results.get('emotion', 'Not available')}\n")
    prompt_parts.append(f"## Key Questions/Concerns:\n{intermediate_results.get('questions', 'Not available')}\n")
    prompt_parts.append(f"## Legal/Contractual Mentions:\n{intermediate_results.get('legal', 'Not available')}\n")

    # Instructions for Final Analysis
    prompt_parts.append("---")
    prompt_parts.append(
        "Your Task: Based *only* on the preliminary analyses provided above, synthesize these findings into a single, cohesive final report. "
        "Structure your response with clear sections (e.g., Key Themes, Actions & Responsibilities, Risks & Challenges, Opportunities, Recommendations)."
    )
    prompt_parts.append("\nFinal Synthesized Analysis:")

    prompt = "\n".join(prompt_parts)
    log(f"Generated prompt for final analysis ({len(prompt)} chars).", "DEBUG")

    # Run Final Analysis LLM
    task_name = "final"
    timeout = config.get("llm_final_analysis_timeout", config.get("llm_default_timeout"))
    final_result = run_with_fallback(task_name, prompt, config, timeout=timeout)

    if final_result is None:
        log(f"Final aggregating analysis task ('{task_name}') failed.", "ERROR")
        return None
    else:
        log(f"Final aggregating analysis task ('{task_name}') completed successfully.", "SUCCESS")
        return final_result.strip()


# Example usage block (needs adaptation if run standalone)
if __name__ == "__main__":
    print("-" * 40)
    print("--- Testing Advanced Analysis Tasks (Refactored) ---")
    print("Note: This test block requires manual setup or mocking.")
    print("-" * 40)

    mock_transcript_text = """Speaker A: We need to finalize the Q3 report.
Speaker B: Agreed. I'll compile the sales data by tomorrow. Is the template ready?
Speaker A: Yes, I sent it yesterday. Are there any legal concerns with the new partner agreement mentioned last week?
Speaker B: I don't think so, but let's have legal double-check paragraph 5 just to be safe."""

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
        test_config = {
            "llm_models": {
                "summary": ["mock-model"], "intent": ["mock-model"],
                "actions": ["mock-model"], "emotion": ["mock-model"],
                "questions": ["mock-model"], "legal": ["mock-model"],
                "final": ["mock-model"]
            }
        }

    try:
        from src.utils.log import setup_logging
        import logging
        setup_logging(level=logging.DEBUG)
    except ImportError:
        print("Skipping logger setup.")

    print("\nRunning individual tasks with mock text...")
    summary_result = summary(mock_transcript_text, test_config, context="Internal project meeting")
    print("\n--- Example Task Result (Summary) ---")
    print(summary_result or "Task failed or returned None.")

    print("\n--- Testing Final Analysis (with mock intermediate results) ---")
    mock_intermediate = {
        "summary": "Q3 report needs finalizing. Sales data due tomorrow. Template sent.",
        "intent": "A wants report done, B agrees to provide data.",
        "actions": "B to compile sales data by tomorrow. Legal to double-check paragraph 5.",
        "emotion": "Task-oriented, collaborative.",
        "questions": "Is the template ready? Any legal concerns with agreement?",
        "legal": "Partner agreement paragraph 5 requires legal review."
    }
    final_analysis_result = run_final_analysis(mock_intermediate, test_config, context="Internal project meeting")
    print("\nFinal Synthesized Analysis Result:")
    print(final_analysis_result or "Final analysis task failed or returned None.")

    print("-" * 40)
    print("--- Testing Complete ---")
    print("-" * 40)
