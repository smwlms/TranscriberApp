# TranscriberApp

TranscriberApp is een lokale webapplicatie waarmee je audio kunt transcriberen en analyseren. Alle AI-modellen draaien lokaal (Whisper, Pyannote, Ollama) zodat je opnames privé blijven. De applicatie is geoptimaliseerd voor Apple Silicon maar werkt ook op Linux.

## Functionaliteiten
- Snelle transcriptie via FasterWhisper.
- Automatische sprekerherkenning met Pyannote.
- (Optioneel) naamvoorstellen via een lokaal LLM.
- Handmatige review van sprekers in de interface.
- Analyse in **fast** of **advanced** modus via Ollama.
- HTML-transcript en andere resultaatbestanden.
- Logging van jobs in een SQLite database.

## Voorwaarden
- macOS of Linux (Apple Silicon aanbevolen).
- Python 3.11 of 3.12.
- Node.js 18+.
- Ollama geïnstalleerd en draaiend.
- Hugging Face account + token.
- Systeemprogramma's: `ffmpeg`, `cmake`, `pkg-config`, `protobuf`.

## Installatie
1. Repository clonen:
   ```bash
   git clone https://github.com/GPTSam/TranscriberApp.git
   cd TranscriberApp
   ```
2. Virtuele omgeving aanmaken:
   ```bash
   python3.11 -m venv venv
   ```
3. Activeer de omgeving:
   ```bash
   source venv/bin/activate      # Windows: venv\Scripts\activate
   ```
4. Installeer systeemafhankelijkheden indien nodig.
   macOS:
   ```bash
   brew install ffmpeg cmake pkg-config protobuf
   ```
   Debian/Ubuntu:
   ```bash
   sudo apt update && sudo apt install -y ffmpeg cmake pkg-config libprotobuf-dev protobuf-compiler
   ```
5. Python packages installeren (snelle dev of volledige installatie):
   - Snelle API‑ontwikkeling (lichte dependencies):
     ```bash
     make PYTHON_INTERPRETER=python3.11 install-dev
     ```
   - Volledige installatie (incl. ML‑deps, kan lang duren):
     ```bash
     make PYTHON_INTERPRETER=python3.11 install
     ```
6. `.env` aanmaken met je Hugging Face token:
   ```bash
   echo "HUGGING_FACE_TOKEN=hf_jouw_token" > .env
   ```
7. Ollama modellen downloaden (volgens `config.yaml`):
   ```bash
   ollama pull llama3:8b
   ollama pull mistral:7b
   ```
8. Configuratie genereren en aanpassen:
   ```bash
   python -m src.utils.generate_config_from_schema
   ```
   Pas daarna `config.yaml` aan en zet `input_audio` naar een bestand in `audio/`.

## Project openen in Visual Studio Code
1. Open de map in VS Code.
2. Start een terminal (``Ctrl+` ``) en activeer de virtuele omgeving:
   ```bash
   source venv/bin/activate
   ```
3. Eén commando om alles te starten (backend +, indien beschikbaar, frontend):
   ```bash
   make up               # gebruikt .venv/bin/python en start services
   ```
   - Geen Node/npm? Dan slaat `make up` het frontend automatisch over en draait alleen de backend.
4. macOS: frontend in nieuw Terminal‑venster + backend in huidige terminal
   ```bash
   make up-macos
   ```
   - Opent een nieuw Terminal‑venster met `npm run dev`; backend draait in je huidige terminal.
   - Geen macOS/osascript? Gebruik dan `make dev-tmux` (zie hieronder) of handmatig twee terminals.
   - iTerm(2) gebruiker? Gebruik `make up-iterm`.
5. Alternatief: afzonderlijk starten
   ```bash
   make run-backend      # alleen backend
   make run-frontend     # alleen frontend (vereist npm)
   ```
6. Smoke‑test tegen draaiende backend:
   ```bash
   make smoke
   ```

### Alternatief: tmux (2 panelen in één terminal)
```bash
brew install tmux   # indien nog niet aanwezig
make dev-tmux       # opent 2 panelen: backend links, frontend rechts
```

### Python installeren/upgraden (macOS)
- Detecteer welke Python wordt gebruikt:
  ```bash
  make check-python
  ```
- Homebrew installeren (macOS):
  ```bash
  make install-homebrew   # interactieve bevestiging; opent het officiële installatie-script
  ```
- Installeer Python 3.11 via Homebrew (indien aanwezig):
  ```bash
  make install-python-macos
  # daarna:
  make PYTHON_INTERPRETER=$(brew --prefix)/bin/python3.11 install-full
  ```
- Zonder Homebrew: installeer Python 3.11 via https://www.python.org/downloads/ en gebruik het pad:
  ```bash
  make PYTHON_INTERPRETER=/pad/naar/python3.11 install-full
  ```

### Node/npm installeren (macOS)
```bash
brew install node                   # snelste manier
# of via nvm:
brew install nvm && mkdir -p ~/.nvm
export NVM_DIR="$HOME/.nvm" && . /opt/homebrew/opt/nvm/nvm.sh
nvm install --lts
```

### Windows: twee vensters (PowerShell)
```powershell
./scripts/up_windows.ps1
```
Dit opent twee PowerShell‑vensters: backend (venv) en frontend (npm run dev) als npm beschikbaar is.
5. Ga naar `http://localhost:5173` in je browser en gebruik de webinterface om de pipeline te starten.

### CLI (optioneel)
De pipeline is ook via de command line te draaien:
```bash
make PYTHON_INTERPRETER=python3.11 run-cli ARGS="--input-audio audio/sample.mp3 --mode advanced"
```

## Output
- `logs/` – logbestanden per dag.
- `transcripts/` – tussenresultaten en `final_transcript.json`.
- `results/` – `transcript.html`, `summary.txt` en `advanced_analysis.json`.
- `llm_training_data.db` – opgeslagen jobdata.

## Probleemoplossing
- Controleer of Ollama draait en de modellen aanwezig zijn.
- Fouten rond Pyannote? Check je `.env` en geaccepteerde modelvoorwaarden.
- Gebruik kleinere modellen of `int8` voor snellere verwerking.

## Licentie
MIT – zie `LICENSE`.

## Contact
Samuel Willems – willems.samuel@gmail.com

---

## API Cheatsheet (Dev)

- Health:
  - `GET /` → `{ status: "ok" }`

- Upload audio:
  - `POST /api/v1/upload_audio` (multipart: `audio_file=@file.wav`)

- Pipeline starten:
  - `POST /api/v1/start_pipeline` (form: `relative_audio_path=audio/<bestand>` + optionele overrides volgens schema)

- Status polling:
  - `GET /api/v1/status/<job_id>`

- Review data ophalen (wanneer status `WAITING_FOR_REVIEW`):
  - `GET /api/v1/get_review_data/<job_id>`

- Review data opslaan (samengevoegd endpoint):
  - `POST /api/v1/update_review_data/<job_id>`
  - Body verwacht: `{ "final_speaker_map": { ... } }`
  - Backwards‑compatible alias: `{ "speaker_map": { ... } }` werkt ook

- Transcript bijwerken (intermediate):
  - `POST /api/v1/update_transcript_data/<job_id>` met `{ "transcript": [...] }`

- Losse adjust endpoint (snelle export):
  - `POST /api/v1/transcriptions/<id>/adjust`
  - `{ "text": "..." }` → `results/<id>.txt` (append met `{"append": true}`)
  - `{ "transcript": [ ... ] }` → `transcripts/<id>.json` en `results/<id>.html`

- Statische bestanden:
  - `GET /results/<bestand>` → resultaten (HTML/TXT)
  - `GET /audio/<bestand>` → geuploade audio
  - `GET /transcripts/<bestand>.json` → transcript JSON (read‑only)
