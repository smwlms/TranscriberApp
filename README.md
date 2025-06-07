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
5. Python packages installeren:
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
3. Start de backend:
   ```bash
   make PYTHON_INTERPRETER=python3.11 run-web
   ```
4. Open een tweede terminal en start het frontend:
   ```bash
   cd frontend
   npm install          # alleen de eerste keer
   npm run dev
   ```
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
