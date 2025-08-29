# Makefile for the TranscriberApp project

# --- Configuration ---
# Preferred interpreter can be overridden: make PYTHON_INTERPRETER=python3.11 install-full
PYTHON_INTERPRETER ?= python3.11
# Auto-detect fallback if preferred is missing
PY_CMD := $(shell command -v $(PYTHON_INTERPRETER) 2>/dev/null || command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null)
VENV_PY := .venv/bin/python
REPO_ROOT := $(shell pwd)
DB_FILE           ?= llm_training_data.db

# --- Phony Targets ---
.PHONY: all install install-full clean clean-build clean-pyc clean-db \
        run-cli run-web run-frontend run-backend run-dev \
        venv install-dev install-frontend install-node-macos install-node \
        install-python-macos install-homebrew check-python \
        up up-macos up-iterm open-frontend-macos open-frontend-iterm dev-tmux smoke \
        freeze lint format check generate-config help

# Default
all: help

# --- Installation ---
install: requirements.txt venv ## Install/update Python dependencies into .venv
	@echo "🔧 Ensuring pip is up-to-date..."
	$(VENV_PY) -m pip install --upgrade pip setuptools wheel
	@echo "🔧 Installing dependencies from requirements.txt..."
	$(VENV_PY) -m pip install -r requirements.txt
	@echo "✅ Dependencies installed/updated."
	@echo "🐍 Venv interpreter: $$($(VENV_PY) -V)"

install-full: ## Recreate .venv with detected Python (override with PYTHON_INTERPRETER=...) and install full requirements
	@echo "🧹 Removing existing virtualenv (.venv)…"
	rm -rf .venv
	@if [ -z "$(PY_CMD)" ]; then echo "❌ No system Python found. Install python3.11 or run: make PYTHON_INTERPRETER=python3 install-full"; exit 1; fi
	@echo "🐍 Creating new virtualenv with: $(PY_CMD)"
	"$(PY_CMD)" -m venv .venv
	@echo "🔧 Upgrading pip/setuptools/wheel in fresh venv…"
	$(VENV_PY) -m pip install --upgrade pip setuptools wheel
	@echo "📦 Installing full requirements from requirements.txt… (this can take a while)"
	$(VENV_PY) -m pip install -r requirements.txt
	@echo "✅ Full installation complete. Interpreter: $$($(VENV_PY) -V)"

check-python: ## Show detected system Python and venv Python
	@if [ -z "$(PY_CMD)" ]; then echo "❌ No system Python found in PATH."; else echo "🔎 Detected system Python: $(PY_CMD) ($$($(PY_CMD) -V))"; fi
	@if [ -x .venv/bin/python ]; then echo "🔎 Venv Python: $$($(VENV_PY) -V)"; else echo "ℹ️  No .venv yet (run 'make venv' or 'make install-full')."; fi

install-python-macos: ## (macOS) Install Python 3.11 with Homebrew if available; otherwise print instructions
	@if command -v python3.11 >/dev/null 2>&1; then \
		echo "✅ python3.11 already installed: $$(command -v python3.11) ($$(python3.11 -V))"; \
	else \
		if command -v brew >/dev/null 2>&1; then \
			echo "🔧 Installing python@3.11 via Homebrew…"; \
			brew install python@3.11 || true; \
			echo "👉 Use: make PYTHON_INTERPRETER=$$(brew --prefix)/bin/python3.11 install-full"; \
		else \
			echo "⚠️  Homebrew not found. Install Homebrew from https://brew.sh and run: brew install python@3.11"; \
			echo "   Or download Python 3.11 installer from https://www.python.org/downloads/"; \
		fi; \
	fi

install-homebrew: ## (macOS) Install Homebrew interactively
	@if [ "$$(/usr/bin/uname -s)" != "Darwin" ]; then \
		echo "❌ This target is intended for macOS (Darwin)."; exit 1; \
	fi; \
	if command -v brew >/dev/null 2>&1; then \
		echo "✅ Homebrew already installed: $$(command -v brew)"; \
	else \
		echo "This will install Homebrew on macOS."; \
		echo "See https://brew.sh for details."; \
		read -p "Proceed with Homebrew install? [y/N] " ans; \
		if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then \
			/bin/bash -c "$$(/usr/bin/curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || true; \
			echo "👉 After install, ensure Homebrew is on your PATH (as per installer output)."; \
		else \
			echo "Aborted Homebrew installation."; exit 1; \
		fi; \
	fi

# --- Virtualenv & Dev Install ---
venv: ## Create .venv using detected Python (override with PYTHON_INTERPRETER=...)
	@if [ ! -x .venv/bin/python ]; then \
		if [ -z "$(PY_CMD)" ]; then echo "❌ No system Python found. Install python3.11 or pass PYTHON_INTERPRETER=..."; exit 1; fi; \
		"$(PY_CMD)" -m venv .venv; \
	fi
	@echo "✅ Virtualenv ready: .venv ($$($(VENV_PY) -V))"

install-dev: requirements-dev.txt venv ## Install minimal backend deps for API dev
	@echo "🔧 Upgrading pip in venv..."
	$(VENV_PY) -m pip install --upgrade pip setuptools wheel
	@echo "🔧 Installing dev requirements (lightweight)..."
	$(VENV_PY) -m pip install -r requirements-dev.txt
	@echo "✅ Dev dependencies installed."

install-frontend: ## Install frontend dependencies (npm ci if lockfile exists)
	@echo "🔧 Installing frontend dependencies..."
	@if command -v npm >/dev/null 2>&1; then \
		cd frontend && if [ -f package-lock.json ]; then npm ci; else npm install; fi; \
		echo "✅ Frontend dependencies installed."; \
	else \
		if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh"; fi; \
		if command -v npm >/dev/null 2>&1; then \
			cd frontend && if [ -f package-lock.json ]; then npm ci; else npm install; fi; \
			echo "✅ Frontend dependencies installed (via nvm)."; \
		else \
			echo "⚠️  'npm' not found. Skipping frontend install."; \
		fi; \
	fi

# --- Running the Application ---
run-cli: ## Run the CLI interface (ARGS="...")
	@echo "▶️  Starting CLI application..."
	@echo "Command: $(VENV_PY) -m src $(ARGS)"
	$(VENV_PY) -m src $(ARGS)

run-web: ## Run Flask via app.py (met venv interpreter)
	@echo "▶️  Starting Flask (app.py)..."
	@echo "Command: $(VENV_PY) app.py"
	$(VENV_PY) app.py

run-frontend: ## Start frontend (Vite)
	@echo "▶️  Starting frontend (Vite)…"
	@if command -v npm >/dev/null 2>&1; then \
		cd frontend && npm run dev; \
	else \
		echo "⚠️  'npm' not found. Skipping frontend run."; \
	fi

run-backend: ## Installeer deps + start Flask in .venv
	@echo "🔧 Installing backend dependencies…"
	$(MAKE) install-dev
	@echo "▶️  Starting Flask server…"
	# activeer je virtualenv en run app.py
	$(VENV_PY) app.py

run-dev: ## 🛠  Start zowel frontend als backend
	@echo "🛠  Spinning up both frontend & backend…"
	$(MAKE) run-frontend & \
	sleep 1; \
	$(MAKE) run-backend

up: ## 🚀 Eén commando: venv + deps + frontend + backend
	@echo "🚀 Bootstrapping dev environment (backend + frontend)…"
	$(MAKE) venv
	$(MAKE) install-dev
	$(MAKE) install-frontend
	@echo "▶️  Launching services…"
	$(MAKE) run-dev

open-frontend-macos: ## Open nieuwe macOS Terminal window met frontend
	@if command -v osascript >/dev/null 2>&1; then \
		osascript -e 'tell application "Terminal" to activate' \
		          -e 'tell application "Terminal" to do script "bash \"$(REPO_ROOT)/scripts/frontend_dev.sh\""'; \
	else \
		echo "⚠️  osascript (macOS) not available. Use 'make run-frontend' in another terminal, or 'make dev-tmux'."; \
	fi

up-macos: ## 🚀 Eén commando: venv + deps + open frontend in nieuw Terminal venster + start backend
	@echo "🚀 Bootstrapping dev environment (backend + frontend in aparte terminals)…"
	$(MAKE) venv
	$(MAKE) install-dev
	$(MAKE) install-node-macos
	$(MAKE) install-frontend
	$(MAKE) open-frontend-macos
	@echo "▶️  Starting backend in current terminal…"
	$(MAKE) run-backend

open-frontend-iterm: ## Open iTerm(2) venster met frontend
	@if command -v osascript >/dev/null 2>&1; then \
		if osascript -e 'id of application "iTerm2"' >/dev/null 2>&1; then \
			osascript -e 'tell application "iTerm2" to activate' \
			          -e 'tell application "iTerm2" to create window with default profile' \
			          -e 'tell current session of current window of application "iTerm2" to write text "bash \"$(REPO_ROOT)/scripts/frontend_dev.sh\""'; \
		elif osascript -e 'id of application "iTerm"' >/dev/null 2>&1; then \
			osascript -e 'tell application "iTerm" to activate' \
			          -e 'tell application "iTerm" to create window with default profile' \
			          -e 'tell current session of current window of application "iTerm" to write text "bash \"$(REPO_ROOT)/scripts/frontend_dev.sh\""'; \
		else \
			echo "⚠️  iTerm(2) not found. Falling back to macOS Terminal."; \
			$(MAKE) open-frontend-macos; \
		fi; \
	else \
		echo "⚠️  osascript (macOS) not available. Use 'make run-frontend' in another terminal, or 'make dev-tmux'."; \
	fi

up-iterm: ## 🚀 Zelfde als up-macos maar opent iTerm(2) venster voor frontend
	@echo "🚀 Bootstrapping dev environment (backend + frontend in iTerm)…"
	$(MAKE) venv
	$(MAKE) install-dev
	$(MAKE) install-node-macos
	$(MAKE) install-frontend
	$(MAKE) open-frontend-iterm
	@echo "▶️  Starting backend in current terminal…"
	$(MAKE) run-backend

install-node-macos: ## (macOS) Installeer Node via Homebrew indien npm ontbreekt
	@if command -v npm >/dev/null 2>&1; then \
		echo "✅ npm already installed."; \
	else \
		if command -v brew >/dev/null 2>&1; then \
			echo "🔧 Installing Node (brew install node)…"; \
			brew install node || (echo "⚠️  Failed to install Node via Homebrew." && exit 0); \
		else \
			echo "⚠️  Homebrew not found. Install Node manually or install Homebrew from https://brew.sh"; \
		fi; \
	fi

install-node: ## Alias: installeer Node (macOS via Homebrew)
	@$(MAKE) install-node-macos

dev-tmux: ## 🪟 Start backend + frontend in tmux (2 panes)
	@if ! command -v tmux >/dev/null 2>&1; then echo "⚠️  tmux not found. Install via 'brew install tmux'"; exit 1; fi
	$(MAKE) venv
	$(MAKE) install-dev
	$(MAKE) install-frontend
	tmux new-session -d -s transcriber 'cd $(REPO_ROOT) && $(VENV_PY) app.py'
	tmux split-window -h -t transcriber 'cd $(REPO_ROOT)/frontend && npm run dev'
	tmux select-layout -t transcriber even-horizontal
	tmux attach -t transcriber

smoke: ## Run smoke tests against running backend
	@echo "🧪 Running smoke tests (backend must be running)…"
	./scripts/smoke_test.sh

# --- Dependency Management ---
freeze: ## Update requirements.txt
	@echo "Updating requirements.txt…"
	$(VENV_PY) -m pip freeze > requirements.txt
	@echo "✅ requirements.txt updated."

# --- Code Quality & Formatting ---
lint: ## Lint met Ruff (auto-fix)
	@echo "Running Ruff linter (with --fix)…"
	$(VENV_PY) -m ruff check . --fix
	@echo "✅ Linting complete."

format: ## Format met Ruff
	@echo "Running Ruff formatter…"
	$(VENV_PY) -m ruff format .
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
