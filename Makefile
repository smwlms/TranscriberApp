# Makefile for the TranscriberApp project

# --- Configuration ---
PYTHON_INTERPRETER ?= python3.11
DB_FILE           ?= llm_training_data.db

# --- Phony Targets ---
.PHONY: all install clean clean-build clean-pyc clean-db \
        run-cli run-web run-frontend run-backend run-dev \
        freeze lint format check generate-config help

# Default
all: help

# --- Installation ---
install: requirements.txt ## Install/update Python dependencies
	@echo "🔧 Ensuring pip is up-to-date..."
	$(PYTHON_INTERPRETER) -m pip install --upgrade pip
	@echo "🔧 Installing dependencies from requirements.txt..."
	$(PYTHON_INTERPRETER) -m pip install -r requirements.txt
	@echo "✅ Dependencies installed/updated."

# --- Running the Application ---
run-cli: ## Run the CLI interface (ARGS="...")
	@echo "▶️  Starting CLI application..."
	@echo "Command: $(PYTHON_INTERPRETER) -m src $(ARGS)"
	$(PYTHON_INTERPRETER) -m src $(ARGS)

run-web: ## Run Flask via app.py (zonder venv-activate)
	@echo "▶️  Starting Flask (app.py)..."
	@echo "Command: $(PYTHON_INTERPRETER) app.py"
	$(PYTHON_INTERPRETER) app.py

run-frontend: ## Start frontend (Vite)
	@echo "▶️  Starting frontend (Vite)…"
	cd frontend && npm run dev

run-backend: ## Installeer deps + start Flask in .venv
	@echo "🔧 Installing backend dependencies…"
	$(MAKE) install
	@echo "▶️  Starting Flask server…"
	# activeer je virtualenv en run app.py
	source .venv/bin/activate && $(PYTHON_INTERPRETER) app.py

run-dev: ## 🛠  Start zowel frontend als backend
	@echo "🛠  Spinning up both frontend & backend…"
	$(MAKE) run-frontend & \
	sleep 1; \
	$(MAKE) run-backend

# --- Dependency Management ---
freeze: ## Update requirements.txt
	@echo "Updating requirements.txt…"
	$(PYTHON_INTERPRETER) -m pip freeze > requirements.txt
	@echo "✅ requirements.txt updated."

# --- Code Quality & Formatting ---
lint: ## Lint met Ruff (auto-fix)
	@echo "Running Ruff linter (with --fix)…"
	$(PYTHON_INTERPRETER) -m ruff check . --fix
	@echo "✅ Linting complete."

format: ## Format met Ruff
	@echo "Running Ruff formatter…"
	$(PYTHON_INTERPRETER) -m ruff format .
	@echo "✅ Formatting complete."

check: lint

# --- Cleaning ---
clean: clean-build clean-pyc clean-db ## Alles schoonmaken
	@echo "🧹 Full project cleanup complete."

clean-build: ## Verwijder build artifacts
	@echo "Removing build artifacts…"
	rm -rf build/ dist/ .eggs/
	find . -depth -name '*.egg-info' -exec rm -rf {} + 
	find . -depth -name '*.egg' -exec rm -f {} +

clean-pyc: ## Verwijder Python cache/temp
	@echo "Removing Python artifacts and temp files…"
	find . -depth \( -name '*.pyc' -o -name '*.pyo' -o -name '*~' \) -exec rm -f {} + 
	find . -depth -name '__pycache__' -exec rm -rf {} +
	rm -f .coverage
	rm -f audio/*__????????_temp.wav

clean-db: ## Verwijder de SQLite database
	@echo "Removing database file: $(DB_FILE)…"
	rm -f $(DB_FILE)
	@echo "✅ Database file removed."

# --- Config Generation ---
generate-config: ## Maak config.yaml van schema
	@echo "Generating default config.yaml from schema…"
	$(PYTHON_INTERPRETER) -m src.utils.generate_config_from_schema --overwrite
	@echo "✅ config.yaml generated/updated."

# --- Help ---
help: ## Toon deze help
	@echo "Available Make targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' | sort
