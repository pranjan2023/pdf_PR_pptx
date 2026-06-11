import re
import json
import yaml
import requests
from pathlib import Path


# --- Config loader ---

def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

CONFIG = load_config()


# --- LLM ---

def call_llm(system: str, user: str) -> str:
    resp = requests.post(
        CONFIG["llm"]["base_url"],
        json={
            "model":  CONFIG["llm"]["model"],
            "stream": CONFIG["llm"]["stream"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        },
        timeout=CONFIG["llm"]["timeout"],
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# --- JSON parsing ---

def parse_json(raw: str) -> dict | list | None:
    clean = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None


# --- Logging ---

def log(stage: str, msg: str) -> None:
    print(f"[{stage}] {msg}")
