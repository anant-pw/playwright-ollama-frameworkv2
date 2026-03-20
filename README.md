# AI Autonomous QA Framework v2

A self-driving QA system that crawls websites, logs in automatically, generates test cases, detects bugs, tests API endpoints, and produces Allure reports — powered by Playwright, Python, and a fully local Ollama LLM.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Start Ollama
ollama pull llama3.2
ollama serve               # in a separate terminal

# 3. Set your target URL in config.env
TARGET_URLS=https://your-site.com

# 4. Run
python run_smart.py
```

Reports open automatically when the run completes.

---

## What It Does

| Capability | Description |
|-----------|-------------|
| 🔐 **Auto Login** | Detects login forms and authenticates — handles Cloudflare, multi-step login, cookie banners, SSO detection |
| 🕷️ **Smart Crawl** | Discovers and prioritises pages — checkout, auth, and forms visited first |
| 🧠 **AI Navigation** | Local LLM decides what to explore next — no fixed scripts |
| 🧪 **TC Generation** | Generates 5 specific test cases per page based on actual UI elements — saved to Excel |
| 🐛 **Bug Detection** | Signal-gated — LLM only fires when console errors, failed requests, or DOM errors exist |
| 🔌 **API Testing** | Captures all XHR/fetch calls during crawl, tests each endpoint directly |
| 👁️ **Visual Detection** | Optional llava vision model catches layout breaks and broken images |
| 🔧 **Self-Healing** | Actions retry with up to 5 fallback strategies when selectors shift |
| 🔄 **Regression Stories** | Auto-generates YAML regression stories from discovered TCs |
| 📊 **Allure Reports** | Clean, flat reports — bugs + screenshots + TCs visible without digging |

---

## Running the Framework

```bash
# Standard run
python run_smart.py

# With CLI overrides
python run_smart.py --level 2                        # autonomy level (1/2/3)
python run_smart.py --urls https://your-site.com     # override URL
python run_smart.py --model llama3.2:latest          # override model
python run_smart.py --pages 5 --steps 4              # more coverage
python run_smart.py --agents 2                       # parallel agents
python run_smart.py --check                          # pre-flight only
python run_smart.py --clear-cache                    # clear LLM cache then run

# View Allure report
allure serve allure-results
```

---

## Autonomy Levels

| Level | Mode | Features | Use when |
|-------|------|----------|---------|
| `1` | Manual | Pre-written stories only — no AI calls | Daily CI regression, Ollama unavailable |
| `2` | Semi-Auto | AI navigation + TC gen + signal-gated bugs | Daily smoke testing (recommended) |
| `3` | Full Auto | Everything + visual detection + story gen | Weekly full exploration |

---

## Configuration (`config.env`)

```ini
TARGET_URLS=https://www.saucedemo.com   # comma-separated, no spaces
AUTONOMY_LEVEL=2                        # 1=manual, 2=semi, 3=full
HEADLESS=true
BROWSER=chromium
MAX_STEPS=3
MAX_CRAWL_PAGES=3
MAX_CRAWL_DEPTH=2
PARALLEL_AGENTS=1
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:latest            # must match 'ollama list' output
OLLAMA_READ_TIMEOUT=300
API_TESTING=true                        # test captured XHR/fetch endpoints
API_TIMEOUT_MS=3000                     # response time budget in ms
LOGIN_EMAIL=your@email.com
LOGIN_PASSWORD=yourpassword
STEALTH_MODE=true                       # bypass bot detection
SELF_HEALING=true                       # true=exploratory, false=strict
CACHE_ENABLED=true                      # cache LLM responses 24h
STORY_ENABLED=false                     # auto-generate regression stories
```

---

## Project Structure

```
ai_tester_project/
├── run_smart.py                ← Main entry point (use this)
├── run_agents.py               ← pytest orchestrator
├── config.py / config.env      ← Settings
├── conftest.py                 ← pytest + Allure setup
├── pytest.ini
├── requirements.txt
├── Jenkinsfile                 ← CI/CD pipeline
│
├── api/                        ← NEW in v2
│   └── api_tester.py           ← Captures + tests XHR/fetch endpoints
│
├── core/                       ← NEW in v2
│   ├── autonomy.py             ← Level 1/2/3 feature flag controller
│   └── cache.py                ← LLM response cache
│
├── agents/
│   ├── agent_controller.py     ← Multi-page crawl loop
│   ├── ai_agent_worker.py      ← Per-page: TC gen + bug detect + actions
│   ├── story_generator.py      ← Auto-generates regression stories
│   └── story_runner.py         ← Executes YAML stories
│
├── ai/
│   ├── ollama_client.py        ← Thread-safe Ollama client
│   ├── bug_detector.py         ← Signal-gated bug detection
│   └── test_generator.py       ← TC generation
│
├── brain/
│   ├── decision_engine.py      ← AI navigation decisions
│   ├── action_executor.py      ← Self-healing (5 strategies)
│   └── smart_crawler.py        ← URL discovery + scoring
│
├── browser/
│   ├── login_handler.py        ← Auto-login (20+ selector strategies)
│   ├── dom_extractor.py        ← DOM extraction
│   ├── screenshot.py           ← Screenshots
│   └── stealth.py              ← 12-patch anti-bot fingerprinting
│
├── reporting/
│   ├── bug_reporter.py
│   ├── bug_report_viewer.py
│   ├── testcase_writer.py
│   ├── test_reporter.py
│   └── tc_viewer.py
│
└── tests/
    ├── test_agent_results.py   ← Per-agent: bugs + TCs + summary
    ├── test_api_results.py     ← NEW: per-agent API endpoint results
    ├── test_bugs.py            ← One Allure card per bug
    ├── test_generated_tcs.py   ← TCs grouped by page
    └── test_user_stories.py    ← Story execution
```

---

## Allure Report Cards

| Card | What it shows |
|------|--------------|
| 🤖 Agent Run Results | Per-agent: bugs found, TCs generated, duration, screenshots |
| 🔌 API Test Results | Per-agent: endpoints tested, status codes, response times, security |
| 🐛 Bugs Detected | One card per bug — severity, screenshot, error signals |
| 🧪 AI Generated TCs | All TCs grouped by page with Excel download |
| 🔄 Regression Stories | Story execution results (STORY_ENABLED=true only) |

**Note:** FAILED tests = bugs found. This is intentional — bugs show RED in Allure.

---

## API Testing

Runs automatically after each crawl. Checks per endpoint:
- Status codes — 5xx = Critical, unexpected 404 = High
- Response time vs `API_TIMEOUT_MS` budget — slow = Medium
- Security headers — missing X-Frame-Options, CSP, HSTS = Low
- Sensitive endpoints (user, account, admin) accessible without auth = High

To disable: `API_TESTING=false`

---

## Output Files

```
bug_reports/<run_id>/
    bug_001.json                ← Browser bug
    bug_002.json                ← API bug
    api_summary_Agent-1.json    ← API test summary
    bug_report_viewer.html      ← HTML bug list

generated_test_cases/<run_id>/
    test_cases.xlsx             ← All TCs
    tc_viewer.html              ← Filterable TC table

screenshots/<run_id>/           ← Per-step + bug screenshots
stories/auto/                   ← Auto-generated story YAML files
allure-results/                 ← Raw Allure data
allure-report/                  ← Generated HTML report
```

---

## Performance Tips (16GB RAM)

```ini
OLLAMA_MODEL=llama3.2      # 1.4GB vs 4.7GB for llama3 full
PARALLEL_AGENTS=1          # start with 1 for stability
HEADLESS=true              # saves ~200MB
MAX_CRAWL_PAGES=3
CACHE_ENABLED=true         # huge win on repeat runs
```

Memory at `PARALLEL_AGENTS=1`: ~2.2GB total.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Ollama not responding | `ollama serve` then `curl http://localhost:11434/api/tags` |
| "Model not found" | Set `OLLAMA_MODEL=llama3.2:latest` (exact output of `ollama list`) |
| Config prints twice | Remove last line of `config.py`: `print("\n" + CFG.summary() + "\n")` |
| Site blocked / Access Denied | Pre-flight check fails but Playwright stealth browser will still reach it |
| SSL warnings in output | Already suppressed — add `PYTHONWARNINGS=ignore` to env if still showing |
| Allure CLI not found | `scoop install allure` or `allure serve allure-results` manually |
| Stories all failing | Stories start from base URL (pre-login) — expected, not a framework bug |

---

## Jenkins

See `JENKINS_SETUP.md` for full CI/CD setup guide.

Quick summary: `Jenkinsfile` includes all v2 parameters — autonomy level, API testing, story generation, self-healing mode, cache, and parallel agents. All configurable per-build without editing files.

---

## What This Is and Isn't

**Is:** A QA accelerator — finds bugs faster than manual exploration, generates first-draft TCs, gives a starting point for regression coverage.

**Isn't:** A production CI test suite. The LLM is non-deterministic. Auto-generated stories need human review.

**Biggest upgrade path:** GPU for Ollama or Groq API drops response times from 60–200s to 2–5s — making this genuinely CI-pipeline ready.

---

*Stack: Playwright + Python + Ollama (llama3.2) + Allure. Fully local — no data leaves the machine.*
