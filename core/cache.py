# core/cache.py
#
# LLM Response Cache
# ───────────────────
# Problem: Same URL patterns (e.g. login page, dashboard) trigger identical
#          prompts → identical Ollama responses → wasted 60s per call.
#
# Solution: Cache LLM responses keyed by (prompt_type, url_hash).
#           TTL-based expiry — entries older than CACHE_TTL_HOURS are ignored.
#           Persisted to disk so cache survives across test runs in the same day.
#
# Usage:
#   from core.cache import LLMCache
#   cache = LLMCache()
#   result = cache.get("tc_gen", url)
#   if result is None:
#       result = generate(prompt)
#       cache.set("tc_gen", url, result)

import hashlib
import json
import os
import time
from pathlib import Path


_CACHE_DIR     = Path(".llm_cache")
_DEFAULT_TTL_H = int(os.environ.get("CACHE_TTL_HOURS", "24"))
_ENABLED       = os.environ.get("CACHE_ENABLED", "true").lower() in ("1", "true", "yes")


class LLMCache:
    """
    Simple file-based LLM response cache.
    Each entry is a JSON file keyed by (prompt_type, url_hash).
    """

    def __init__(self, cache_dir: str = None, ttl_hours: int = None):
        self.enabled   = _ENABLED
        self.ttl_secs  = (ttl_hours or _DEFAULT_TTL_H) * 3600
        self.cache_dir = Path(cache_dir or _CACHE_DIR)
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, prompt_type: str, url: str) -> Path:
        key = f"{prompt_type}:{url}"
        h   = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{prompt_type}_{h}.json"

    def get(self, prompt_type: str, url: str) -> str | None:
        """Return cached response or None if miss/expired/disabled."""
        if not self.enabled:
            return None
        path = self._key_path(prompt_type, url)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age  = time.time() - data.get("timestamp", 0)
            if age > self.ttl_secs:
                path.unlink(missing_ok=True)
                return None
            print(f"[CACHE] HIT {prompt_type} for {url[:50]}")
            return data.get("response")
        except Exception:
            return None

    def set(self, prompt_type: str, url: str, response: str) -> None:
        """Store a response in the cache."""
        if not self.enabled or not response:
            return
        path = self._key_path(prompt_type, url)
        try:
            data = {
                "prompt_type": prompt_type,
                "url":         url,
                "response":    response,
                "timestamp":   time.time(),
            }
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"[CACHE] STORED {prompt_type} for {url[:50]}")
        except Exception as e:
            print(f"[CACHE] Write error: {e}")

    def invalidate(self, prompt_type: str = None) -> int:
        """Remove all cache entries (or only entries of a given type)."""
        if not self.cache_dir.exists():
            return 0
        count = 0
        for f in self.cache_dir.glob("*.json"):
            if prompt_type is None or f.name.startswith(f"{prompt_type}_"):
                f.unlink(missing_ok=True)
                count += 1
        print(f"[CACHE] Invalidated {count} entries")
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        if not self.cache_dir.exists():
            return {"entries": 0, "enabled": self.enabled}
        entries  = list(self.cache_dir.glob("*.json"))
        now      = time.time()
        valid    = 0
        expired  = 0
        for f in entries:
            try:
                data = json.loads(f.read_text())
                age  = now - data.get("timestamp", 0)
                if age <= self.ttl_secs:
                    valid += 1
                else:
                    expired += 1
            except Exception:
                expired += 1
        return {
            "enabled":     self.enabled,
            "ttl_hours":   self.ttl_secs // 3600,
            "total":       len(entries),
            "valid":       valid,
            "expired":     expired,
            "cache_dir":   str(self.cache_dir),
        }


# Module-level singleton
_cache = LLMCache()


def cached_generate(prompt_type: str, url: str, prompt: str,
                    generate_fn) -> str:
    """
    Convenience wrapper: try cache → call generate_fn on miss → store result.

    Usage:
        from core.cache import cached_generate
        from ai.ollama_client import generate

        result = cached_generate("tc_gen", page_url, prompt, generate)
    """
    cached = _cache.get(prompt_type, url)
    if cached is not None:
        return cached

    result = generate_fn(prompt)
    if result:
        _cache.set(prompt_type, url, result)
    return result
