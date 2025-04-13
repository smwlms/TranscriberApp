# src/transcript_reformatter.py
import html  # For escaping user-generated text to prevent XSS
import math
from typing import List, Dict, Any, Optional
from pathlib import Path # Keep for test block

# Assuming log utility is set up and functional
from src.utils.log import log

def _format_timestamp(seconds: Optional[float]) -> str:
    """
    Formats a duration in seconds into a user-friendly timestamp string.
    Outputs in [MM:SS] format, or [HH:MM:SS] if hours are present.
    Handles None or invalid inputs gracefully.
    """
    # Validate input type and value
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
        log(f"Received invalid input for timestamp formatting: {seconds}", "DEBUG")
        return "[--:--]" # Placeholder for invalid time
    try:
        # Ensure we work with integer seconds for calculations
        total_seconds = int(math.floor(seconds))
        # Calculate hours, minutes, remaining seconds
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)

        # Format based on whether hours are present
        if hours > 0:
            # Format as [HH:MM:SS]
            return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
        else:
            # Format as [MM:SS]
            return f"[{minutes:02d}:{secs:02d}]"
    except Exception as e:
        # Log unexpected errors during formatting, return placeholder
        log(f"Error formatting timestamp for value: {seconds}. Error: {e}", "WARNING")
        return "[??:??]" # Placeholder indicating an error


def format_transcript_html(transcript_segments: List[Dict[str, Any]]) -> str:
    """
    Formats a list of transcript segments (containing 'start', 'text', and 'speaker_name')
    into a structured and styled HTML string representation.

    Args:
        transcript_segments: The list of transcript segment dictionaries.

    Returns:
        A string containing the complete HTML document.
    """
    # Handle empty transcript input gracefully
    if not transcript_segments:
        log("Cannot format HTML: Input transcript segments list is empty.", "WARNING")
        # Return a minimal valid HTML structure indicating emptiness
        # Added some basic styling for the empty message
        return """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Transcript</title><style>body{font-family:sans-serif;padding:20px;}.empty-transcript{color:grey;font-style:italic;text-align:center;}</style></head>
<body><p class="empty-transcript">[Transcript data is empty or missing]</p></body>
</html>"""

    log(f"Formatting {len(transcript_segments)} segments into HTML...", "INFO")
    html_parts = [] # Use a list to build the HTML string efficiently
    current_speaker_name = None # Track the current speaker to group segments

    # --- HTML Header and Inline CSS Styling ---
    # Inline CSS makes the HTML file self-contained. Can be moved external if preferred.
    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conversation Transcript</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
            line-height: 1.6;
            margin: 1em;
            background-color: #f8f9fa; /* Light grey background */
            color: #212529; /* Dark text color */
        }
        .transcript-container {
            max-width: 800px; /* Limit content width */
            margin: 1em auto; /* Center container */
            background-color: #ffffff; /* White background for content */
            padding: 1.5em 2em; /* Padding inside container */
            border-radius: 8px; /* Rounded corners */
            box-shadow: 0 2px 5px rgba(0,0,0,0.08); /* Subtle shadow */
        }
        h2 {
            text-align: center;
            color: #343a40; /* Darker grey for heading */
            margin-bottom: 1.5em;
            border-bottom: 1px solid #dee2e6; /* Separator line */
            padding-bottom: 0.5em;
        }
        .speaker-block {
            margin-bottom: 1.5em; /* Space between different speakers */
            padding-bottom: 1em;
            border-bottom: 1px solid #f1f3f5; /* Lighter separator between blocks */
        }
        .speaker-block:last-child {
            margin-bottom: 0; /* No bottom margin for the last block */
            border-bottom: none; /* No separator line for the last block */
        }
        .speaker-name {
            font-weight: bold;
            color: #0056b3; /* Blue color for speaker name */
            margin-bottom: 0.6em;
            font-size: 1.05em; /* Slightly larger speaker name */
        }
        .segment {
            margin-bottom: 0.6em; /* Space between segments of the same speaker */
            display: flex; /* Use flexbox for alignment */
            align-items: baseline; /* Align timestamp and text baseline */
        }
        .timestamp {
            font-family: monospace;
            font-size: 0.85em;
            color: #6c757d; /* Medium grey for timestamp */
            margin-right: 0.75em;
            flex-shrink: 0; /* Prevent timestamp from shrinking */
            width: 70px; /* Fixed width for alignment */
            text-align: right;
        }
        .segment-text {
            /* Text takes remaining space */
        }
        /* Basic responsive adjustment */
        @media (max-width: 600px) {
            body { margin: 0.5em; }
            .transcript-container { padding: 1em; }
            .timestamp { width: 60px; margin-right: 0.5em; }
        }
    </style>
</head>
<body>
<div class="transcript-container">
    <h2>Conversation Transcript</h2>""") # Main title for the transcript

    # --- Process Each Transcript Segment ---
    for i, segment in enumerate(transcript_segments):
        # Safely get segment data, providing default fallbacks
        speaker_name = segment.get("speaker_name", "Unknown Speaker")
        start_time = segment.get("start") # Format function handles None
        text = segment.get("text", "").strip() # Use stripped text

        # --- Security: Escape speaker name and text to prevent XSS ---
        safe_speaker_name = html.escape(speaker_name, quote=True)
        safe_text = html.escape(text, quote=True)

        # --- Group Segments by Speaker ---
        # Check if the speaker has changed from the previous segment
        if safe_speaker_name != current_speaker_name:
            # If this isn't the very first segment, close the previous speaker's block
            if i > 0:
                 html_parts.append('</div>') # Close previous speaker-block div
            # Start a new block for the new speaker
            html_parts.append('<div class="speaker-block">')
            html_parts.append(f'<div class="speaker-name">{safe_speaker_name}</div>')
            current_speaker_name = safe_speaker_name # Remember the new current speaker

        # --- Add Formatted Segment Content ---
        # Format the start timestamp using the helper function
        timestamp_str = _format_timestamp(start_time)
        # Create a div for the segment row (timestamp + text)
        html_parts.append(f'<div class="segment">')
        html_parts.append(f'<span class="timestamp">{timestamp_str}</span>')
        # Replace escaped newline characters with HTML <br> tags for display
        safe_text_with_breaks = safe_text.replace('\n', '<br>')
        html_parts.append(f'<span class="segment-text">{safe_text_with_breaks}</span>')
        html_parts.append('</div>') # Close segment div

    # --- Final HTML Cleanup ---
    # Ensure the very last speaker block div is closed if there were segments
    if transcript_segments:
         html_parts.append('</div>') # Close final speaker-block div
    # Close the main container and HTML body/html tags
    html_parts.append('</div>') # Close transcript-container div
    html_parts.append('</body></html>')

    log("HTML transcript formatting complete.", "SUCCESS")
    # Efficiently join all generated HTML parts into a single string
    return "".join(html_parts)


# Example usage block (no changes needed here)
if __name__ == "__main__":
    # ... (test code remains the same) ...
    pass