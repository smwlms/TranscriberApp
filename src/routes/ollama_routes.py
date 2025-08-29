from typing import Dict, Any
import threading
from flask import Blueprint, jsonify, request

from src.utils.log import log
from src.utils.llm import get_local_models, _run_ollama_command
from src.utils.ollama_catalog import get_catalog
from src.utils.system_specs import get_system_specs
from src.core.model_loader import get_compute_device
from src.utils.config_schema import PROJECT_ROOT
import yaml

ollama_bp = Blueprint('ollama_bp', __name__)


@ollama_bp.route('ollama/catalog', methods=['GET'])
def ollama_catalog_route():
    """Return curated catalog with availability flags.

    Response: { catalog: [ {name, summary, best_for, available, ...}, ... ], local: [..] }
    """
    log("API: Request received for /ollama/catalog", "INFO")
    local = set(get_local_models())
    catalog = get_catalog()
    for item in catalog:
        item["available"] = item.get("name") in local
    specs = get_system_specs()
    # Simple recommendations derived from device and memory
    device = specs.get("device") or get_compute_device()
    mem_gb = specs.get("memory_gb") or 8
    def rec_primary():
        if device == 'cuda':
            return 'llama3:8b'
        if device == 'mps':
            return 'llama3:8b' if (mem_gb and mem_gb >= 16) else 'mistral:7b'
        # CPU fallback
        return 'phi3:medium' if (mem_gb and mem_gb < 16) else 'mistral:7b'

    primary = rec_primary()
    recommendations = {
        "summary": primary,
        "final": primary,
        "intent": 'mistral:7b' if primary != 'mistral:7b' else primary,
        "actions": primary,
        "emotion": 'phi3:medium',
        "questions": 'llama3:8b' if device in ('mps','cuda') and (mem_gb and mem_gb >= 16) else 'mistral:7b',
        "legal": 'llama3:8b' if device in ('mps','cuda') and (mem_gb and mem_gb >= 16) else primary,
        "name_detection": primary,
    }
    return jsonify({
        "catalog": catalog,
        "local": sorted(list(local)),
        "specs": specs,
        "recommended": recommendations,
    })


@ollama_bp.route('ollama/pull', methods=['POST'])
def ollama_pull_route():
    """Pull an Ollama model. JSON body: { "model": "llama3:8b" }"""
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({"error": "Missing 'model' in body"}), 400
    log(f"API: Pull requested for model '{model}'", "INFO")

    # Run pull synchronously; this can take time. Optional: allow background.
    output = _run_ollama_command(["ollama", "pull", model], timeout=None)
    if output is None:
        return jsonify({"error": f"Failed to pull model '{model}'. Check logs and Ollama status."}), 500
    # Return updated list
    local = get_local_models()
    return jsonify({"message": f"Pulled {model}", "local": local})


@ollama_bp.route('ollama/assign', methods=['POST'])
def ollama_assign_models_route():
    """Assign models to tasks by updating config.yaml

    Body: { "llm_models": { "summary": ["llama3:8b"], ... } }
    """
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    mapping = data.get('llm_models')
    if not isinstance(mapping, dict):
        return jsonify({"error": "Body must include 'llm_models' object"}), 400

    config_path = PROJECT_ROOT / 'config.yaml'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        cfg_llm = config.get('llm_models') or {}
        if not isinstance(cfg_llm, dict):
            cfg_llm = {}

        # Only accept list-of-strings per task
        updated = {}
        for task, models in mapping.items():
            if isinstance(models, list) and all(isinstance(m, str) and m for m in models):
                updated[task] = models
        cfg_llm.update(updated)
        config['llm_models'] = cfg_llm

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)

        log(f"Updated llm_models assignments in config.yaml: {list(updated.keys())}", "SUCCESS")
        return jsonify({"message": "Assignments saved", "llm_models": cfg_llm})
    except Exception as e:
        log(f"Failed to update llm_models in config.yaml: {e}", "ERROR")
        return jsonify({"error": "Failed to update config.yaml"}), 500
