# ai/bug_detector.py
#
# FIXES:
#   1. _has_vision_model() result is now CACHED at module level
#      Before: HTTP request to Ollama on EVERY detect_bug() call
#      After:  One HTTP call per run, cached in _vision_model_cache
#   2. _get_available_model() is also cached
#   3. Public interface unchanged — all callers work without modification

import allure
import json
import base64
import hashlib
import os
import requests
from ai.ollama_client import generate, OllamaUnavailableError, OLLAMA_HOST
from config import CFG

# Track reported bugs to avoid duplicates within a run
_reported_hashes: set = set()

_CATEGORIES = [
    "broken_layout",
    "missing_content",
    "broken_form",
    "navigation_error",
    "console_error",
    "auth_issue",
    "performance",
    "visual_issue",
]

# ── Vision model cache — checked ONCE per run, not per call ──────────────────

_vision_model_cache: dict = {"checked": False, "available": False, "model": "llava"}


def _check_vision_model_once():
    """Check Ollama for vision models exactly once per run."""
    if _vision_model_cache["checked"]:
        return
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        models = [m.get("name", "") for m in r.json().get("models", [])]
        vision = [m for m in models if any(
            v in m.lower() for v in ["llava", "bakllava", "vision", "moondream"]
        )]
        _vision_model_cache["available"] = bool(vision)
        _vision_model_cache["model"]     = vision[0] if vision else "llava"
        if vision:
            print(f"[VISUAL] Vision model available: {vision[0]}")
        else:
            print("[VISUAL] No vision model found — visual detection disabled")
    except Exception as e:
        print(f"[VISUAL] Could not check vision models: {e}")
        _vision_model_cache["available"] = False
    finally:
        _vision_model_cache["checked"] = True


def _has_vision_model() -> bool:
    _check_vision_model_once()
    return _vision_model_cache["available"]


def _get_vision_model() -> str:
    _check_vision_model_once()
    return _vision_model_cache["model"]


# ── Visual detection (unchanged logic, uses cached model) ────────────────────

def detect_bug_visual(screenshot_path: str, page_url: str = "",
                      page_title: str = "") -> dict:
    """Send screenshot to llava for visual bug detection."""
    if not screenshot_path or not os.path.exists(screenshot_path):
        return _no_bug()

    vision_model = _get_vision_model()

    try:
        with open(screenshot_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        prompt = f"""You are a senior QA engineer reviewing a screenshot.
URL: {page_url}
Page title: {page_title}

Identify REAL visual bugs only (broken layouts, failed images, cut-off text, error pages).
Do NOT report normal design choices or minor spacing.

Respond in EXACT JSON:
{{"found": true/false, "severity": "Critical/High/Medium/Low", "category": "visual_issue/broken_layout/missing_content", "title": "short title (max 10 words)", "description": "what is wrong (2-3 sentences)"}}

If no bug: {{"found": false, "severity": "None", "category": "none", "title": "No visual bug", "description": ""}}
"""
        payload = {
            "model":  vision_model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
            timeout=(CFG.ollama_connect_timeout, CFG.ollama_read_timeout),
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip()

        clean = raw.strip()
        if "```" in clean:
            clean = clean.split("```")[1].lstrip("json").strip()

        result = json.loads(clean)
        result["raw"]    = raw
        result["source"] = "visual"
        return result

    except json.JSONDecodeError:
        print("[VISUAL] Could not parse llava response as JSON")
        return _no_bug()
    except Exception as e:
        print(f"[VISUAL] Visual detection error: {e}")
        return _no_bug()


def collect_page_signals(page) -> dict:
    """Collect real technical signals from the browser (no AI)."""
    signals = {
        "console_errors":  [],
        "failed_requests": [],
        "js_errors":       [],
        "page_title":      "",
        "current_url":     "",
    }
    try:
        signals["page_title"]  = page.title()
        signals["current_url"] = page.url

        for sel in [
            "[class*='error']:visible",
            "[class*='Error']:visible",
            "[role='alert']:visible",
            ".alert-danger:visible",
            "[data-testid*='error']:visible",
        ]:
            try:
                els = page.locator(sel).all_inner_texts()
                if els:
                    signals["js_errors"].extend(
                        [t.strip() for t in els if t.strip()][:5])
            except Exception:
                pass
    except Exception as e:
        print(f"[BUG] Signal collection error: {e}")
    return signals


def detect_bug(page_text: str, page_signals: dict = None,
               screenshot_path: str = None) -> dict:
    """
    Unified bug detection:
    1. Try visual analysis (llava) if screenshot available and vision model cached
    2. Fall back to text + signal analysis (llama3)
    3. Final fallback: pure signal-based detection

    NOTE: Callers should check for signals BEFORE calling this function.
    Use _has_signals() in ai_agent_worker to gate the call.
    """
    signals         = page_signals or {}
    console_errors  = signals.get("console_errors", [])
    failed_requests = signals.get("failed_requests", [])
    js_errors       = signals.get("js_errors", [])
    current_url     = signals.get("current_url", "unknown")

    # Dedup check
    sig = hashlib.md5(
        f"{current_url}:{sorted(console_errors)}:{sorted(js_errors)}".encode()
    ).hexdigest()[:8]

    if sig in _reported_hashes:
        return {"found": False, "severity": "None", "category": "duplicate",
                "title": "Duplicate", "description": "", "raw": "DUPLICATE"}
    _reported_hashes.add(sig)

    # 1. Visual analysis (uses cached model check)
    if screenshot_path and _has_vision_model():
        page_title    = signals.get("page_title", "")
        visual_result = detect_bug_visual(screenshot_path, current_url, page_title)
        if visual_result.get("found"):
            print(f"[VISUAL] Bug found visually: {visual_result.get('title')}")
            return visual_result

    # 2. Text + signal analysis via LLM
    prompt = f"""You are a senior QA engineer doing exploratory testing.

URL: {current_url}

TECHNICAL SIGNALS (most reliable):
Console errors: {console_errors if console_errors else 'none'}
Failed requests: {failed_requests if failed_requests else 'none'}
Visible errors in DOM: {js_errors if js_errors else 'none'}

PAGE CONTENT (first 2000 chars):
{page_text[:2000]}

Identify REAL bugs. Do NOT report normal UI text, expected validation, or working-as-designed.

Respond in EXACT JSON:
{{"found": true/false, "severity": "Critical/High/Medium/Low", "category": one of {_CATEGORIES}, "title": "short title (max 10 words)", "description": "what is broken and how to reproduce (2-3 sentences)"}}

If no bug: {{"found": false, "severity": "None", "category": "none", "title": "No bug", "description": ""}}
"""

    raw_result = ""
    try:
        raw_result = generate(prompt)
        if not raw_result:
            return _no_bug()

        clean = raw_result.strip()
        if "```" in clean:
            clean = clean.split("```")[1].lstrip("json").strip()

        result = json.loads(clean)
        result["raw"]    = raw_result
        result["source"] = "text"

    except (json.JSONDecodeError, OllamaUnavailableError):
        result = _signal_fallback(console_errors, failed_requests,
                                   js_errors, raw_result)

    try:
        if result["found"]:
            allure.attach(json.dumps(result, indent=2),
                          name="Bug Details",
                          attachment_type=allure.attachment_type.JSON)
    except Exception:
        pass

    return result


def _no_bug() -> dict:
    return {"found": False, "severity": "None", "category": "none",
            "title": "No bug", "description": "", "raw": "NO BUG", "source": "none"}


def _signal_fallback(console_errors, failed_requests, js_errors, raw) -> dict:
    """Pure signal-based detection when AI is unavailable."""
    if console_errors:
        return {"found": True, "severity": "High", "category": "console_error",
                "title": "Console errors detected",
                "description": f"Console errors: {console_errors[:3]}",
                "raw": raw, "source": "signals"}
    if failed_requests:
        return {"found": True, "severity": "High", "category": "navigation_error",
                "title": "Network requests failed",
                "description": f"Failed requests: {failed_requests[:3]}",
                "raw": raw, "source": "signals"}
    if js_errors:
        return {"found": True, "severity": "Medium", "category": "console_error",
                "title": "Visible error messages",
                "description": f"Error elements: {js_errors[:3]}",
                "raw": raw, "source": "signals"}
    return _no_bug()
