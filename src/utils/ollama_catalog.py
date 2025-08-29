# src/utils/ollama_catalog.py
"""Curated Ollama model catalog with short summaries and suitability hints.

This is a static, hand-maintained list to avoid relying on network access.
It's intended for Apple Silicon and CPU setups; sizes are rough guidance.
"""

from typing import List, Dict


# Fields per entry:
# - name: Ollama identifier (e.g., "llama3:8b")
# - family: base model family
# - params_b: parameter count in billions (approx)
# - size_hint_gb: rough disk footprint when pulled (varies by quantization)
# - summary: short human description
# - best_for: list of tags (e.g., ["summary", "general", "qa"]) used by UI
# - notes: optional extra notes

OLLAMA_MODEL_CATALOG: List[Dict] = [
    {
        "name": "llama3:8b",
        "family": "llama3",
        "params_b": 8,
        "size_hint_gb": 4.0,
        "summary": "Sterke algemene instructiemodel; goed in NL/EN voor samenvattingen en QA.",
        "best_for": ["summary", "final", "general", "qa"],
    },
    {
        "name": "mistral:7b",
        "family": "mistral",
        "params_b": 7,
        "size_hint_gb": 4.0,
        "summary": "Snel en accuraat 7B; goed voor samenvatting en kort redeneren.",
        "best_for": ["summary", "intent", "questions", "general"],
    },
    {
        "name": "phi3:medium",
        "family": "phi3",
        "params_b": 14,
        "size_hint_gb": 2.7,
        "summary": "Compact en efficiënt; verrassend goed voor korte samenvattingen.",
        "best_for": ["summary", "emotion", "lightweight"],
    },
    {
        "name": "qwen2:7b",
        "family": "qwen2",
        "params_b": 7,
        "size_hint_gb": 4.0,
        "summary": "Sterk open model; goed alternatief voor Mistral 7B.",
        "best_for": ["summary", "intent", "questions", "general"],
    },
    {
        "name": "gemma:7b",
        "family": "gemma",
        "params_b": 7,
        "size_hint_gb": 4.0,
        "summary": "Google Gemma 7B; goed taalgevoel, bruikbaar voor samenvattingen.",
        "best_for": ["summary", "emotion", "general"],
    },
    {
        "name": "deepseek-coder:6.7b",
        "family": "deepseek",
        "params_b": 6.7,
        "size_hint_gb": 3.0,
        "summary": "Code-georiënteerd; handig voor transcript naar code/regex taken.",
        "best_for": ["coding", "utilities"],
    },
    {
        "name": "mixtral:8x7b",
        "family": "mixtral",
        "params_b": 46,
        "size_hint_gb": 26.0,
        "summary": "Mixture-of-Experts; zwaar voor laptops. Alleen aanbevolen als je veel RAM hebt.",
        "best_for": ["advanced", "long_context"],
        "notes": "Niet aanbevolen op machines < 32GB RAM.",
    },
]

def get_catalog() -> List[Dict]:
    return OLLAMA_MODEL_CATALOG.copy()

