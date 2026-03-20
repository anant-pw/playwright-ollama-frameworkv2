# AI QA Framework — Senior Architect Analysis & Redesign Plan

---

## [System Analysis]

### Current Framework Problems and Root Causes

**Critical Bugs (will cause crashes or silent failures)**

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| 1 | **Self-import** — `agent_controller.py` calls `from agents.agent_controller import run_agent_with_crawling` *inside itself* | `agent_controller.py L117, L154` | Circular import risk; unnecessary overhead |
| 2 | **Duplicate parallel execution** — nearly identical `_run_parallel()` / `_run_sequential()` blocks exist in both `agent_controller.py` AND `run_agents.py` | Both files | Dead code; bugs fixed in one place won't be fixed in the other |
| 3 | **Vision model check on every bug detection call** — `_has_vision_model()` makes an HTTP GET to Ollama every single step | `bug_detector.py L31` | N × 5 HTTP round-trips per run wasted |
| 4 | **`start_agents()` in `agent_controller.py` is unreachable** — pytest entry is `test_run_ai_agents()` in `run_agents.py`; `start_agents()` is never called | `agent_controller.py L77` | Dead code bloat |

**Performance Problems (cause the "slow" complaint)**

| # | Problem | Cost |
|---|---------|------|
| 5 | **3 LLM calls per step** — decision + TC generation + bug detection = 3 × Ollama per step × MAX_STEPS per page × pages | With 5 steps × 3 pages = 45 LLM calls per run. At ~60s each = 45 min sequential |
| 6 | **TC generation runs every step** — should run once per page, not once per step | 5× wasted calls per page |
| 7 | **AI ranks crawl URLs** — `ai_rank_pages()` calls Ollama just to sort already-scored URLs | Extra LLM call that `score_url()` already handles deterministically |
| 8 | **Allure over-attachment** — every micro-step creates a JSON+TEXT+CSV attachment | Allure report bloat → slow report generation |
| 9 | **Ollama global lock** — `_ollama_lock` makes all parallel agents serialized at the Ollama layer, negating thread-level parallelism | Parallel = sequential in practice |

**Architecture Problems (cause "instability" and "debugging difficulty")**

| # | Problem |
|---|---------|
| 10 | No autonomy levels — system is always "full auto" with no manual/semi override |
| 11 | No LLM response cache — identical page patterns trigger identical prompts with identical responses, wasting time |
| 12 | No health pre-flight — framework starts even if Ollama is down; errors buried in step 3 |
| 13 | `StateMemory` and `ExplorationTracker` are trivial wrappers (3 lines each) — unnecessary abstraction |
| 14 | Story auto-generation (Phase 4) is unstable by design — LLM generates YAML that executes as tests; parse failures silently drop stories |

---

## [Simplified Architecture]

### Before (Current)

```
pytest
 └── conftest.py
      └── run_agents.py::test_run_ai_agents()
           ├── _run_agents_parallel()          ← DUPLICATE of agent_controller.py
           │    └── run_agent_with_crawling()  ← agent_controller.py
           │         ├── SmartCrawler
           │         │    └── ai_rank_pages() ← UNNECESSARY LLM call
           │         └── run_agent_on_page()
           │              ├── generate_test_cases()  ← LLM call #1 (EVERY step)
           │              ├── detect_bug()            ← LLM call #2 (EVERY step)
           │              │    └── _has_vision_model() ← HTTP call (EVERY step)
           │              └── decide_next_action()    ← LLM call #3 (EVERY step)
           └── story_generator (PHASE 4)       ← Extra LLM loop
```

### After (Proposed)

```
run_smart.py
 └── Pipeline.run()
      ├── preflight_check()         ← Ollama health + config validation
      ├── autonomy_gate()           ← Level 1/2/3 flag controls what runs
      ├── parallel_workers()
      │    └── AgentWorker.run_url()
      │         ├── SmartCrawler    ← Rule-based only (no AI ranking)
      │         └── per_page_loop()
      │              ├── [once/page] generate_test_cases() ← LLM + cache
      │              ├── [signals-first] detect_bug()      ← LLM only if signals trigger
      │              └── [per_step] decide_next_action()   ← LLM + cache
      └── report_summary()
```

**Result:** 3 LLM calls/step → 1 LLM call/step + TC generation moved to once/page + bug detection signal-gated.

---

## [Module Design]

### Simplified Module Map

```
ai_tester_project/
│
├── core/                       ← NEW: central infrastructure
│   ├── pipeline.py             ← Main orchestrator (replaces run_agents.py logic)
│   ├── autonomy.py             ← Flag-based autonomy level (1=manual, 2=semi, 3=full)
│   └── cache.py                ← LLM response cache (TTL-based, URL-keyed)
│
├── agents/
│   ├── agent_controller.py     ← SIMPLIFIED: remove duplicate parallel code + self-import
│   └── ai_agent_worker.py      ← IMPROVED: respect autonomy level, TC once/page
│       (story_generator.py)    ← KEEP but OPTIONAL (STORY_ENABLED=false default)
│       (story_runner.py)       ← KEEP unchanged
│
├── ai/
│   ├── ollama_client.py        ← KEEP (lock is correct; add cache hook)
│   ├── bug_detector.py         ← FIX: cache vision check; signal-first logic
│   ├── test_generator.py       ← KEEP unchanged
│   └── (ai_client.py)          ← REMOVE: duplicate of ollama_client; unused
│       (parser.py)             ← REMOVE: 3-line file, inline it
│
├── brain/
│   ├── smart_crawler.py        ← FIX: remove ai_rank_pages() call by default
│   ├── action_executor.py      ← KEEP unchanged (self-healing is valuable)
│   ├── decision_engine.py      ← KEEP unchanged
│   └── (state_memory.py)       ← SIMPLIFY: inline into ai_agent_worker (3 lines)
│       (exploration_tracker.py)← SIMPLIFY: inline into ai_agent_worker (3 lines)
│
├── browser/
│   ├── login_handler.py        ← KEEP unchanged (robust)
│   ├── dom_extractor.py        ← KEEP unchanged
│   ├── screenshot.py           ← KEEP unchanged
│   ├── stealth.py              ← KEEP unchanged
│   └── (element_ranker.py)     ← REMOVE: unused (returns nothing to callers)
│       (validator.py)          ← REMOVE: 1-line stub
│
├── reporting/
│   ├── bug_reporter.py         ← KEEP unchanged
│   ├── testcase_writer.py      ← KEEP unchanged
│   ├── test_reporter.py        ← KEEP unchanged
│   └── (bug_report_viewer.py)  ← KEEP (HTML viewer)
│       (tc_viewer.py)          ← KEEP (HTML viewer)
│
├── run_smart.py                ← NEW: clean single entry point
├── run.py                      ← KEEP for backward compat
├── run_agents.py               ← SIMPLIFY: remove duplicate parallel code
├── config.py                   ← KEEP + add AUTONOMY_LEVEL field
├── config.env                  ← UPDATE: add autonomy + cache settings
├── conftest.py                 ← KEEP unchanged
├── run_context.py              ← KEEP unchanged
├── pytest.ini                  ← KEEP unchanged
└── requirements.txt            ← UPDATE: add pyyaml (already used, not listed)
```

---

## [Execution Flow]

### Deterministic Step-by-Step Pipeline

```
STEP 0: PRE-FLIGHT (always runs, ~2s)
─────────────────────────────────────
  ✓ Load config.env → CFG
  ✓ Check AUTONOMY_LEVEL (1/2/3)
  ✓ Ping Ollama → if LEVEL≥2 and Ollama down → WARN and degrade to LEVEL 1
  ✓ Verify target URLs are reachable (HTTP HEAD, 5s timeout)
  ✓ Print run plan to console

STEP 1: URL DISPATCH
─────────────────────
  If PARALLEL_AGENTS=1 → sequential loop
  If PARALLEL_AGENTS>1 → ThreadPoolExecutor with N workers
  Each worker gets: (url, agent_id)

STEP 2: PER-URL AGENT LOOP
───────────────────────────
  For each URL:
    2a. Launch browser (stealth or plain, per config)
    2b. Navigate + login if credentials set
    2c. Init SmartCrawler (rule-based scoring, no AI ranking)
    2d. Loop over pages (max MAX_CRAWL_PAGES):
        → per_page_processing(page)

STEP 3: PER-PAGE PROCESSING
─────────────────────────────
  3a. Extract DOM  (deterministic, no AI)
  3b. Screenshot   (always)
  3c. [ONCE per page] Generate TCs
       - Check cache(url_hash) → hit: skip LLM, reuse
       - miss: call Ollama → save to cache + Excel
  3d. Signal collection (console errors, failed requests, DOM errors)
       - If ANY signals found → call bug detector (LLM)
       - If NO signals → skip LLM, mark "clean"
  3e. Loop over steps (MAX_STEPS):
       - decide_next_action() → LLM (with cache)
       - execute_action() → self-healing
       - collect_page_signals() → if new errors → bug detector
       - if "stop" → break

STEP 4: CRAWL NEXT PAGE
─────────────────────────
  4a. extract_crawlable_links() → score_url() sorts them
  4b. Add top-N to queue (NO ai_rank_pages call)
  4c. Repeat from STEP 3

STEP 5: POST-RUN REPORTING
───────────────────────────
  5a. Attach crawl map to Allure
  5b. [if STORY_ENABLED=true] generate_stories_from_tcs()
  5c. Close browser
  5d. Print per-agent summary

STEP 6: FINAL REPORT
─────────────────────
  6a. Generate Allure report
  6b. Open bug_report_viewer HTML
  6c. Open tc_viewer HTML
  6d. Print PASS/FAIL summary to console
```

---

## [Agent Strategy]

### Keep / Merge / Remove

| Agent/Component | Decision | Reason |
|----------------|----------|--------|
| `agent_controller.py::run_agent_with_crawling()` | **KEEP** | Core crawl loop; well-built |
| `agent_controller.py::start_agents()` | **REMOVE** | Dead code — never called by pytest |
| `agent_controller.py::_run_parallel/_run_sequential` | **REMOVE** | Exact duplicate of `run_agents.py` logic |
| `run_agents.py::test_run_ai_agents` | **KEEP** | Pytest entry point |
| `agents/ai_agent_worker.py` | **IMPROVE** | Move TC gen to once/page; add autonomy |
| `agents/story_generator.py` | **KEEP** | Off by default (STORY_ENABLED=false); useful for Phase 4 |
| `agents/story_runner.py` | **KEEP** | Solid implementation |
| `ai/ai_client.py` | **REMOVE** | 100% duplicate of `ollama_client.generate()` |
| `ai/parser.py` | **REMOVE** | Empty file / never used |
| `brain/state_memory.py` | **INLINE** | 3 lines; not worth a module |
| `brain/exploration_tracker.py` | **INLINE** | 3 lines; not worth a module |
| `browser/element_ranker.py` | **REMOVE** | Never called anywhere |
| `browser/validator.py` | **REMOVE** | 1-line stub; never called |

**Net result:** 2 agents (crawler worker + page worker) instead of the implied 4-5 agent system. Clear roles, no overlap.

---

## [Performance Optimization]

### LLM Call Reduction (Biggest Win)

| Current | Improved | Savings |
|---------|----------|---------|
| TC generation: every step | TC generation: once per page | **5× fewer calls** |
| Bug detection: every step (no filter) | Bug detection: only when signals exist | **~70% fewer calls** (most pages are clean) |
| AI URL ranking: every page crawl | Score-based ranking (deterministic) | **1 call per page eliminated** |
| Vision check HTTP: every detect_bug() | Cached at startup (boolean) | **N × 5 HTTP calls eliminated** |

**Example:** 2 URLs × 3 pages × 5 steps  
- Before: 2×3×5×3 = **90 LLM calls**  
- After: 2×3×1 (TC) + 2×3×~1 (bugs, gated) + 2×3×5 (decisions) = **~48 LLM calls** (47% reduction)

### Memory Optimization (16GB Constraint)

```ini
# config.env tuning for 16GB RAM:
PARALLEL_AGENTS=1          # Start with 1; each agent = ~800MB browser + Ollama
MAX_CRAWL_PAGES=3          # Don't let crawl explode
MAX_STEPS=3                # 3 steps is enough for pilot
HEADLESS=true              # Saves ~200MB vs headed Chrome

# Ollama model selection for 16GB:
OLLAMA_MODEL=llama3.2      # 2B params = ~1.4GB vs llama3 = ~4.7GB
# OR: phi3:mini = ~2.3GB, much faster than llama3
```

**Memory budget at PARALLEL_AGENTS=1:**
- Ollama (llama3.2): ~1.4 GB  
- Python/pytest: ~200 MB  
- Chromium (headless): ~600 MB  
- **Total: ~2.2 GB** ✓ Safe on 16GB  

**Memory budget at PARALLEL_AGENTS=2:**
- Ollama: ~1.4 GB (shared)  
- 2× Python: ~400 MB  
- 2× Chromium: ~1.2 GB  
- **Total: ~3 GB** ✓ Still safe  

### Speed Optimization

```python
# Add to core/cache.py — simple URL-keyed cache
# Identical pages = same hash = skip LLM
CACHE_TTL_HOURS = 24  # Don't re-analyze same page within 24h
```

---

## [AI Usage Strategy]

### Where AI Adds Value (KEEP)

| Use | Model | Why |
|-----|-------|-----|
| `decide_next_action()` | llama3.2 | Context-aware navigation decisions beat random walks |
| `generate_test_cases()` | llama3.2 | Generating domain-specific TCs from page content is hard to rule-encode |
| `detect_bug()` — when signals present | llama3.2 | Classifying whether console errors are real bugs needs reasoning |
| `detect_bug_visual()` — if llava available | llava | Visual layout bugs are impossible to catch with text |
| `generate_stories_from_tcs()` | llama3.2 | Converts TCs to runnable YAML — useful for regression |

### Where AI Should NOT Be Used (REPLACE with logic)

| Current | Replacement | Why |
|---------|-------------|-----|
| `ai_rank_pages()` in crawler | `score_url()` sorting (already exists!) | Score function is deterministic and already scores correctly. AI adds no value here. |
| `detect_bug()` when no signals | Skip entirely | If console is clean, requests all succeed, no DOM errors → no bug. LLM can't invent signals. |
| `_has_vision_model()` per call | Cache boolean at startup | It never changes mid-run |
| `_get_available_model()` per call | Cache at startup | Model list doesn't change mid-run |

---

## [Tech Stack Decisions]

### Current Stack: KEEP AS-IS

| Tech | Decision | Reason |
|------|----------|--------|
| Playwright | ✅ KEEP | Best-in-class for browser automation; no alternative needed |
| Ollama | ✅ KEEP | Local LLM is the right choice for 16GB/CPU-bound system |
| pytest | ✅ KEEP | Standard; Allure integration works well |
| Allure | ✅ KEEP | Good reporting; but reduce attachment frequency |
| ThreadPoolExecutor | ✅ KEEP | Correct parallelism model for this use case |

### Rejected Additions (Would Overengineer the Pilot)

| Tech | Verdict | Why Rejected |
|------|---------|--------------|
| **RAG** (vector DB + embeddings) | ❌ NOT NOW | Adds Chroma/FAISS dependency. The simple `cache.py` (dict + file) achieves the same cache benefit for this use case. Add later if TC base > 10,000. |
| **n8n** | ❌ NO | External workflow orchestrator for what is already a 200-line pipeline. Over-engineering. |
| **MCP server** | ❌ NO | The framework already has direct Playwright access. MCP adds indirection with no benefit here. |
| **LangChain/CrewAI** | ❌ NO | Adds 500MB deps and unpredictable agent loops. ThreadPoolExecutor + direct Ollama calls are better for a QA pipeline. |

### One Justified Addition: `pyyaml` in requirements.txt

```
# Already used in story_generator.py and story_runner.py
# Missing from requirements.txt — add it:
pyyaml
```

---

## [Feature Decision Table]

| Feature | Decision | Reason |
|---------|----------|--------|
| Multi-page SmartCrawler | ✅ KEEP | Core value; well-implemented |
| Score-based URL prioritization | ✅ KEEP | Already good; just remove AI ranking on top |
| AI-powered TC generation | ✅ KEEP | Core value |
| Signal-based bug detection | ✅ KEEP + IMPROVE | Add gating so LLM only fires when signals present |
| Visual bug detection (llava) | ✅ KEEP | Unique value; optional |
| Self-healing action executor | ✅ KEEP | Excellent implementation |
| Smart login handler | ✅ KEEP | Robust multi-strategy login |
| Stealth mode | ✅ KEEP | Real-world sites need it |
| Parallel agents | ✅ KEEP | But fix duplicate code |
| Allure reporting | ✅ KEEP | But reduce attachment noise |
| Jenkins/CI integration | ✅ KEEP | Professional requirement |
| Auto story generation | ⚠️ KEEP OPTIONAL | Off by default; useful for Phase 5 |
| `ai_rank_pages()` | ❌ REMOVE | Replaced by existing `score_url()` |
| `start_agents()` dead code | ❌ REMOVE | Never called |
| `ai_client.py` duplicate | ❌ REMOVE | 100% duplicate of `ollama_client.py` |
| `element_ranker.py` | ❌ REMOVE | Never called |
| `validator.py` 1-liner | ❌ REMOVE | Never called |
| `StateMemory` / `ExplorationTracker` wrappers | ⬇️ INLINE | 3 lines each; not worth modules |
| **Autonomy levels (1/2/3)** | ✅ ADD | Core ask; needed for pilot |
| **LLM response cache** | ✅ ADD | Biggest single performance win |
| **Pre-flight health check** | ✅ ADD | Prevent silent failures |
| **`pyyaml` in requirements.txt** | ✅ ADD | Fix missing dependency |

---

## [Debugging & Stability Plan]

### Log Level System

Add `LOG_LEVEL` to config.env:

```
LOG_LEVEL=INFO   # INFO | DEBUG | QUIET
```

- `QUIET`: Only PASS/FAIL + summary
- `INFO`: Module-level events (current behavior, good)
- `DEBUG`: Every selector tried, every Ollama response

### Allure Attachment Noise Reduction

Currently attaches for every micro-step. New rule:

```python
# Only attach to Allure if:
ATTACH_RULES = {
    "bug_found":      ALWAYS,     # Always attach bug details
    "tc_generated":   ALWAYS,     # Always attach TCs
    "healing_needed": ALWAYS,     # Always attach when self-healing was used
    "ai_decision":    INFO_ONLY,  # Only attach if LOG_LEVEL >= INFO
    "page_text":      DEBUG_ONLY, # Only attach if LOG_LEVEL == DEBUG
    "dom_extract":    DEBUG_ONLY,
    "prompts":        DEBUG_ONLY,
}
```

### Failure Handling Rules

```
Ollama unavailable      → signal-only bug detection + template TCs (no crash)
Browser launch failure  → skip URL, log error, continue with next URL
Page timeout            → retry once with 2× timeout, then skip
Login failure           → log warning, continue unauthenticated
YAML parse error        → skip story, log warning, continue
```

### Pre-flight Check (add to `run_smart.py`)

```python
def preflight_check():
    issues = []
    if not ollama_client.is_healthy():
        issues.append("⚠️  Ollama is DOWN — AI features disabled (autonomy=1)")
    for url in CFG.target_urls:
        if not _url_reachable(url):
            issues.append(f"⚠️  URL unreachable: {url}")
    return issues
```

---

## [Pros & Cons]

### Current System

**Pros:**
- Comprehensive feature set (crawl + login + TC + bugs + visual + stories + CI)
- Good self-healing action executor
- Thread-safe design
- Real Allure integration

**Cons:**
- Self-import bug in agent_controller.py
- 3 LLM calls per step is too heavy; TC generation should be once/page
- Duplicate parallel execution code in 2 files
- No autonomy levels — always full-auto
- No caching — every identical page re-calls Ollama
- `_has_vision_model()` makes HTTP call on every bug check
- `ai_rank_pages()` LLM call adds latency with no benefit over score_url()
- Missing `pyyaml` in requirements.txt
- Dead code (start_agents, ai_client.py, element_ranker, validator)
- Allure report bloat from over-attachment

### Proposed System

**Pros:**
- All existing strengths preserved
- 47%+ fewer LLM calls (cache + gating + TC once/page)
- Autonomy levels allow manual/semi/full-auto modes
- Pre-flight prevents silent failures
- Dead code removed
- Single entry point (`run_smart.py`) is clean and obvious
- Deterministic crawl ordering (remove AI ranking of URLs)

**Cons:**
- Refactoring has some risk (tests should still pass after)
- Cache adds file I/O (small, negligible on local disk)
- Autonomy Level 1 (manual only) requires pre-written stories — team must author them

---

## [Pilot Definition]

### ✅ The system is "pilot-ready" when:

1. `python run_smart.py` works end-to-end on a real site with no crashes
2. `AUTONOMY_LEVEL=1` (manual stories) runs clean regression
3. `AUTONOMY_LEVEL=2` (semi-auto) generates TCs and detects bugs without hanging
4. Total run time for 1 URL, 3 pages, 3 steps ≤ 15 minutes on 16GB machine
5. Allure report generates and opens automatically
6. Bug reports and TC Excel file are created in correct `run_id` directories
7. Parallel agents (PARALLEL_AGENTS=2) doesn't crash

### 🛑 STOP building when:

- The above 7 criteria are met
- Do NOT add: RAG, vector stores, multi-model routing, self-improvement loops, MCP servers, n8n
- Do NOT add Phase 5/6/7 features until the pilot is validated by real QA engineers
- Story auto-generation (Phase 4) is already built — leave it off by default

---

## [Final Recommendations]

### Priority Order (Do These First)

1. **[5 min] Fix circular self-import** in `agent_controller.py` — remove `from agents.agent_controller import...` inside the same file
2. **[10 min] Add `pyyaml` to `requirements.txt`** — it's already used, just missing
3. **[30 min] Add `core/autonomy.py`** — flag-based level control (delivered below)
4. **[30 min] Add `core/cache.py`** — LLM cache (delivered below)
5. **[20 min] Move TC generation to once/page** in `ai_agent_worker.py` (delivered below)
6. **[20 min] Gate bug detection on signals** — only call LLM if signals present (delivered below)
7. **[10 min] Cache `_has_vision_model()`** result at module level
8. **[15 min] Remove `ai_rank_pages()` from default path** — use score_url() only
9. **[30 min] Add `run_smart.py`** — clean entry point with pre-flight (delivered below)
10. **[2 hrs] Remove dead code** — `start_agents()`, `ai_client.py`, `element_ranker.py`, `validator.py`

### Files to Deliver (in this analysis)

All improved files are in the `improved_framework/` directory alongside this document.

### Config for Pilot Start

```ini
# Recommended pilot settings (config.env)
TARGET_URLS=https://www.saucedemo.com
AUTONOMY_LEVEL=2        # Semi-auto: crawl + TC gen, but gated bug detection
PARALLEL_AGENTS=1       # Start sequential for pilot stability
MAX_CRAWL_PAGES=3
MAX_STEPS=3
HEADLESS=true
OLLAMA_MODEL=llama3.2   # Lighter model for 16GB
CACHE_ENABLED=true
LOG_LEVEL=INFO
STORY_ENABLED=false     # Enable only after pilot validates core loop
```
