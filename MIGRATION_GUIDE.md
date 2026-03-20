# MIGRATION GUIDE — Applying Improvements to Your Framework

## What Changed and Why

This guide explains exactly which files to update in your existing
`ai_tester_project` to apply all improvements.

---

## Step 1: Add New Files (drop-in additions)

Copy these new files into your project:

```
core/                         ← NEW DIRECTORY
  __init__.py                 ← empty
  autonomy.py                 ← autonomy level controller
  cache.py                    ← LLM response cache
run_smart.py                  ← new clean entry point (optional)
```

---

## Step 2: Replace Existing Files (bug fixes + improvements)

| File | Changes Summary |
|------|----------------|
| `agents/agent_controller.py` | Removed self-import bug; removed dead `start_agents()`; removed duplicate parallel code |
| `agents/ai_agent_worker.py` | TC generation moved to once/page; bug detection signal-gated; autonomy-aware |
| `ai/bug_detector.py` | Vision model check cached at module level (was HTTP call per step) |
| `brain/smart_crawler.py` | `ai_rank_pages()` disabled by default; only called at AUTONOMY_LEVEL=3 |
| `config.env` | Added AUTONOMY_LEVEL, CACHE_ENABLED, CACHE_TTL_HOURS, LOG_LEVEL |
| `requirements.txt` | Added `pyyaml` (was missing, already used by story_generator.py) |

---

## Step 3: Files to Delete (dead code)

```bash
# Safe to delete — never called by anything:
rm ai/ai_client.py          # 100% duplicate of ollama_client.py::generate()
rm ai/parser.py             # empty stub, never imported
rm browser/element_ranker.py # never called
rm browser/validator.py      # 1-line stub, never called
```

---

## Step 4: Verify the Fix

### Before (broken):
```python
# agents/agent_controller.py — line 117 (self-import bug)
from agents.agent_controller import run_agent_with_crawling  # ← WRONG: importing from self!
```

### After (fixed):
```python
# The function is defined IN this file — no import needed
# It's just called directly: bugs, tcs = run_agent_with_crawling(pw, url, agent_id)
```

---

## Step 5: Test the New Entry Point

```bash
# Old way (still works):
python run.py

# New way (with pre-flight + autonomy levels):
python run_smart.py                   # uses config.env settings
python run_smart.py --level 1        # manual mode only
python run_smart.py --level 2        # semi-auto (recommended)
python run_smart.py --level 3        # full auto
python run_smart.py --check          # pre-flight only (no tests)
python run_smart.py --clear-cache    # clear LLM cache then run
```

---

## Step 6: Recommended Pilot Settings

```ini
# config.env for first pilot run
TARGET_URLS=https://www.saucedemo.com
AUTONOMY_LEVEL=2
PARALLEL_AGENTS=1
MAX_CRAWL_PAGES=3
MAX_STEPS=3
HEADLESS=true
OLLAMA_MODEL=llama3:latest
CACHE_ENABLED=true
STORY_ENABLED=false
```

---

## Expected Performance Improvement

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| LLM calls (3 pages, 3 steps) | ~27 | ~12 | **55% fewer** |
| Vision model HTTP checks | 27 | 1 | **97% fewer** |
| AI URL ranking calls | 3 | 0 | **eliminated** |
| Self-import crash risk | Present | Fixed | ✅ |
| Missing pyyaml | Yes | Fixed | ✅ |
| Autonomy control | None | 3 levels | ✅ |
| LLM response cache | None | Active | ✅ |

---

## Pilot-Ready Checklist

- [ ] `python run_smart.py --check` passes without errors
- [ ] `python run_smart.py --level 2` completes without crashing
- [ ] Allure report opens automatically
- [ ] bug_reports/ directory has at least 1 bug (or 0 if site is clean)
- [ ] generated_test_cases/ has TCs in Excel
- [ ] Run time < 15 minutes for 1 URL, 3 pages, 3 steps on 16GB machine

When all boxes are checked: **STOP BUILDING. The pilot is ready.**
