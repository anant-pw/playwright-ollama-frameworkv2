# ai/ollama_client.py
#
# PHASE 3E: Thread-safe Ollama client
# ─────────────────────────────────────
# Problem: 2-3 parallel agents all call Ollama simultaneously
# → Ollama queues them → each waits 300-400s → timeouts
#
# Fix: OllamaLock ensures only ONE agent calls Ollama at a time
# Other agents wait their turn — no timeouts, no resource contention
# This is fine because Ollama is single-threaded anyway

import os
import threading
import requests
from config import CFG

OLLAMA_HOST = CFG.ollama_host

# ── Global lock — one Ollama call at a time ───────────────────────────────────
_ollama_lock = threading.Lock()


class OllamaUnavailableError(Exception):
    pass


def _get_model() -> str:
    """Get current model — re-reads config.env each call."""
    try:
        env_file = os.path.join(os.path.dirname(__file__), "..", "config.env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OLLAMA_MODEL="):
                        return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return CFG.ollama_model


def _get_available_model(requested: str) -> str:
    """Auto-switch to available model if requested not found."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        models = [m.get("name", "") for m in r.json().get("models", [])]
        if not models:
            return requested
        if requested in models:
            return requested
        # Auto-switch to best available
        for preferred in ["llama3:latest", "llama3", "llama2", "mistral"]:
            if preferred in models:
                print(f"[OLLAMA] '{requested}' not found — auto-switching to '{preferred}'")
                return preferred
        print(f"[OLLAMA] Auto-switching to '{models[0]}'")
        return models[0]
    except Exception:
        return requested


def is_healthy() -> bool:
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags",
                         timeout=CFG.ollama_connect_timeout)
        models = [m.get("name","") for m in r.json().get("models", [])]
        print(f"[OLLAMA] Ollama healthy ✓\nHost: {OLLAMA_HOST}")
        print(f"Loaded models: {models}")
        return True
    except Exception as e:
        print(f"[OLLAMA] Ollama unavailable: {e}")
        return False


def generate(prompt: str, model: str = None) -> str:
    """
    Generate text from Ollama.
    Thread-safe: acquires lock so only one agent calls Ollama at a time.
    """
    requested = model or _get_model()
    actual    = _get_available_model(requested)

    retries = CFG.ollama_retries + 1

    for attempt in range(1, retries + 1):
        # ── Acquire lock — wait for other agents to finish ────────────────────
        with _ollama_lock:
            try:
                payload = {
                    "model":  actual,
                    "prompt": prompt,
                    "stream": False,
                }
                response = requests.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json=payload,
                    timeout=(CFG.ollama_connect_timeout,
                             CFG.ollama_read_timeout),
                )
                response.raise_for_status()
                text = response.json().get("response", "").strip()
                chars = len(text)
                print(f"[OLLAMA] Response in "
                      f"{response.elapsed.total_seconds():.1f}s ({chars} chars)")
                return text

            except requests.exceptions.Timeout:
                print(f"[WARN] Ollama timeout after "
                      f"{CFG.ollama_read_timeout}s (attempt {attempt}/{retries})")
                if attempt >= retries:
                    raise OllamaUnavailableError(
                        f"Ollama timed out after {retries} attempts")

            except requests.exceptions.ConnectionError as e:
                raise OllamaUnavailableError(f"Ollama connection failed: {e}")

            except Exception as e:
                print(f"[WARN] Ollama error (attempt {attempt}): {e}")
                if attempt >= retries:
                    raise OllamaUnavailableError(f"Ollama failed: {e}")

    return ""


def generate_vision(prompt: str, image_b64: str,
                     model: str = "llava") -> str:
    """
    Generate vision response from Ollama (llava).
    Thread-safe: acquires same lock as generate().
    """
    with _ollama_lock:
        try:
            payload = {
                "model":  model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
            }
            response = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json=payload,
                timeout=(CFG.ollama_connect_timeout,
                         CFG.ollama_read_timeout),
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            print(f"[VISUAL] Vision call error: {e}")
            return ""
