# TranscriberApp

(A local web application for transcribing and analyzing audio files using local AI models.)

## Key Features

* **Transcription:** Converts audio files (MP3, WAV, M4A, etc.) to text using FasterWhisper.
* **Speaker Diarization:** Identifies different speakers using Pyannote.audio.
* **Speaker Name Detection:** (Optional) LLM-based detection of speaker names.
* **User Review & Edit:** (Planned) UI step for reviewing/correcting speaker names.
* **LLM Analysis:** Two modes via local Ollama: 'Fast' (summary) or 'Advanced' (multi-faceted analysis).
* **HTML Output:** Generates a formatted HTML transcript.
* **Database Logging:** Saves job results to an SQLite database.
* **Local Processing:** Ensures privacy by running Whisper, Pyannote, and Ollama locally.
* **Apple Silicon Optimization:** Uses MPS for performance improvements on M1/M2/M3 Macs.

## Technology Stack

* **Backend:** Python, Flask
* **Transcription:** FasterWhisper
* **Diarization:** Pyannote.audio
* **LLM Interaction:** Ollama (subprocess)
* **Database:** SQLAlchemy Core, SQLite
* **Audio Handling:** Pydub (optional)
* **Frontend:** Svelte, Vite, Tailwind CSS
* **Code Quality:** Ruff

## Demo / Screenshot

*(Insert screenshot or GIF here)*
![image](files/uploaded_screencapture-192-168-0-166-5002-2025-04-12-10_33_51.jpg)

## Requirements

* **OS:** macOS (Apple Silicon recommended). Linux/Windows potentially compatible (CPU/CUDA).
* **Python:** 3.11+
* **Ollama:** Installed & running ([ollama.com](https://ollama.com/)). Required models pulled.
* **Hugging Face Account & Token:** Account needed for Pyannote model terms. Read Access Token required (store in `.env`).
* **System Dependencies:**
    * **macOS (via Homebrew):** `brew install ffmpeg cmake pkg-config protobuf`
    * *(Other OS: Install equivalents via your package manager).*
* **Python Packages:** See `requirements.txt`.

## Installation

1.  **Clone repository:** `git clone <your-repo-url>` and `cd <repo-dir>`
2.  **Create & activate Python venv:** `python3.11 -m venv venv` and `source venv/bin/activate` (or equivalent)
3.  **Install system dependencies:** (e.g., `brew install ffmpeg cmake pkg-config protobuf` on macOS)
4.  **Install Python dependencies:** `pip install -r requirements.txt` (or `make install`)
5.  **Setup Hugging Face Token:** Accept model terms on HF. Create read token. `cp .env.example .env`. Edit `.env` with your token (`HUGGING_FACE_TOKEN=hf_...`).
6.  **Download Ollama Models:** `ollama pull <model_name>` for models listed in `config.yaml`.

## Configuration

* Main configuration via `config.yaml`.
* Schema details in `config_schema.yaml`.
* Key settings: `mode`, `whisper_model`, `llm_models`, etc.
* Default `config.yaml` generated if missing; existing configs auto-updated with defaults. Use `make generate-config` to force regeneration.

## Usage

**1. Web Interface:**

* Start backend: `make run-web` (or `python app.py`)
* Start frontend: `cd frontend && npm install && npm run dev && cd ..`
* Open browser to frontend URL (e.g., `http://localhost:5173`).
* Workflow: Upload -> Configure -> Start -> Monitor -> (Review - Planned) -> Results.

**2. Command Line Interface:**

* Runs full pipeline non-interactively. Uses `config.yaml`, overridable with args. Review step is automatic.
* Examples (from project root):
    ```bash
    python -m src # Uses config.yaml settings
    python -m src --input-audio audio/meeting.mp3 --mode advanced
    make run-cli ARGS="--input-audio audio/call.wav --whisper-model medium"
    ```
* Outputs generated in standard directories (`results/`, `transcripts/`, `llm_training_data.db`).

## Output Files & Data

* `logs/`: Daily log files.
* `transcripts/intermediate_...json`: Raw transcript, proposed map, context snippets.
* `transcripts/final_transcript.json`: Transcript with final names.
* `results/transcript.html`: Formatted HTML transcript.
* `results/summary.txt`: 'Fast' mode output.
* `results/advanced_analysis.json`: 'Advanced' mode output.
* `llm_training_data.db`: SQLite DB with job results.

## Speaker Handling Process

1.  Diarization (Pyannote) -> Speaker IDs (`SPEAKER_00`).
2.  Transcription (Whisper) -> Text segments.
3.  Merge -> Assign ID to text.
4.  (Optional) Name Detection (LLM) -> Propose names.
5.  (Planned) User Review (UI) -> Confirm/edit names.
6.  Final Mapping -> Apply names to transcript.

## Database Logging

Job results are logged to `llm_training_data.db` for potential future use (e.g., analysis, fine-tuning).

## Troubleshooting

* **Pyannote/HF Token:** Accept terms on HF, check `.env` token.
* **Ollama:** Ensure service running, models pulled. Check Ollama logs.
* **Port Conflicts:** Check process using port (e.g., `lsof -i :5001`), change `FLASK_PORT`.
* **ModuleNotFoundError:** Check venv activation, `pip install -r requirements.txt`.
* **Performance:** Check logs for MPS/CUDA. Use smaller models / `int8`.
* **Build Errors:** Ensure system dependencies (`cmake`, `pkg-config`, `protobuf`) installed via package manager.

## Future Enhancements

* Implement speaker review UI.
* Allow transcript text editing.
* Add more analysis tasks.
* Improve UI feedback.
* (Add other ideas...)

## License

MIT License - see [LICENSE](LICENSE) file.

## Author / Contact

Samuel Willems / Legendaddy / willems.samuel@gmail.com