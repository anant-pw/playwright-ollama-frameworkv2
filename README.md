# 🤖 AI Autonomous QA Framework

A self-driving QA system that crawls websites, generates test cases, detects bugs, and produces Allure reports — powered by Playwright, Python, and a local Ollama LLM.

---

## 📋 Table of Contents

- [What It Does](#what-it-does)
- [Quick Start](#quick-start)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Framework](#running-the-framework)
- [Autonomy Levels](#autonomy-levels)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Output & Reports](#output--reports)
- [Parallel Agents](#parallel-agents)
- [Login Support](#login-support)
- [Writing Manual Stories](#writing-manual-stories)
- [Jenkins / CI Integration](#jenkins--ci-integration)
- [Troubleshooting](#troubleshooting)
- [Performance Tips (16GB RAM)](#performance-tips-16gb-ram)
- [FAQ](#faq)

---

## What It Does

| Capability | Description |
|-----------|-------------|
| 🕷️ **Smart Crawling** | Automatically discovers and prioritises pages (login, checkout, forms first) |
| 🧪 **TC Generation** | Uses AI to generate 5 specific test cases per page based on actual UI elements |
| 🐛 **Bug Detection** | Detects bugs from console errors, failed requests, DOM signals, and screenshots |
| 🔐 **Auto Login** | Detects login forms and logs in automatically using configured credentials |
| 👁️ **Visual Detection** | Optional llava vision model catches layout breaks and broken images |
| 🔧 **Self-Healing** | Actions automatically retry with 5 fallback strategies if elements move |
| 📊 **Allure Reports** | Rich HTML reports with screenshots, bug details, and TC download |
| 🔄 **Regression Stories** | Optional: AI generates YAML regression stories from discovered TCs |
| ⚙️ **Autonomy Levels** | Choose between manual, semi-auto, or full-auto modes |
| 🚀 **Parallel Agents** | Test multiple URLs simultaneously |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Start Ollama (must be running before tests)
ollama serve
ollama pull llama3:latest

# 3. Set your target URL
# Edit config.env → TARGET_URLS=https://your-site.com

# 4. Run
python run_smart.py
```

That's it. Reports open automatically when the run completes.

---

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | 3.11 recommended |
| Playwright | latest | `pip install playwright` |
| Ollama | latest | https://ollama.com |
| Allure CLI | latest | For HTML reports (optional but recommended) |
| RAM | 8GB min | 16GB recommended |
| OS | Windows / macOS / Linux | All supported |

---

## Installation

### 1. Clone and install Python dependencies

```bash
git clone <your-repo>
cd ai_tester_project

pip install -r requirements.txt
playwright install chromium
```

### 2. Install and start Ollama

```bash
# Install Ollama from https://ollama.com
# Then pull a model:
ollama pull llama3:latest        # 4.7GB — best quality
# OR for 16GB RAM machines (lighter):
ollama pull llama3.2             # 1.4GB — faster, good quality
```

Verify Ollama is running:
```bash
ollama list        # should show your model
curl http://localhost:11434/api/tags   # should return JSON
```

### 3. Install Allure CLI (for HTML reports)

```bash
# macOS
brew install allure

# Windows (via Scoop)
scoop install allure

# Linux
sudo apt-get install allure
# or download from https://allurereport.org/docs/install/
```

### 4. Configure your target site

Edit `config.env`:
```ini
TARGET_URLS=https://your-site.com
LOGIN_EMAIL=your@email.com      # leave blank if no login needed
LOGIN_PASSWORD=yourpassword
```

---

## Configuration

All settings live in `config.env`. No code changes needed.

### Essential Settings

```ini
# The site(s) to test. Comma-separate for multiple:
TARGET_URLS=https://www.saucedemo.com,https://your-other-site.com

# AI control level (see Autonomy Levels section)
AUTONOMY_LEVEL=2

# Ollama model — run 'ollama list' to see what you have
OLLAMA_MODEL=llama3:latest
```

### Browser Settings

```ini
HEADLESS=true          # false = see the browser while it runs (good for debugging)
BROWSER=chromium       # chromium | firefox | webkit
MAX_STEPS=3            # actions per page (3-5 is good for pilot)
PAGE_TIMEOUT=60000     # ms to wait for page load
STEALTH_MODE=true      # mimic real user browser (recommended)
```

### Crawl Settings

```ini
PARALLEL_AGENTS=1      # how many URLs tested at once
MAX_CRAWL_PAGES=3      # max pages to test per URL
MAX_CRAWL_DEPTH=2      # how deep to follow links
```

### Login Settings

```ini
LOGIN_EMAIL=standard_user      # email or username
LOGIN_PASSWORD=secret_sauce    # password
# LOGIN_URL is optional — framework auto-detects login pages
```

### Performance Settings

```ini
CACHE_ENABLED=true     # cache LLM responses (huge speed boost on repeat runs)
CACHE_TTL_HOURS=24     # how long to keep cached responses
LOG_LEVEL=INFO         # QUIET | INFO | DEBUG
```

### Full `config.env` Reference

| Key | Default | Description |
|-----|---------|-------------|
| `TARGET_URLS` | `https://example.com` | Comma-separated URLs to test |
| `AUTONOMY_LEVEL` | `2` | 1=manual, 2=semi-auto, 3=full-auto |
| `HEADLESS` | `true` | Run browser headlessly |
| `BROWSER` | `chromium` | Browser engine |
| `MAX_STEPS` | `3` | AI actions per page |
| `MAX_CRAWL_PAGES` | `3` | Pages per URL |
| `MAX_CRAWL_DEPTH` | `2` | Link follow depth |
| `PARALLEL_AGENTS` | `1` | Concurrent URL workers |
| `STEALTH_MODE` | `true` | Anti-bot detection evasion |
| `LOGIN_EMAIL` | *(empty)* | Login username/email |
| `LOGIN_PASSWORD` | *(empty)* | Login password |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `llama3:latest` | LLM model name |
| `OLLAMA_READ_TIMEOUT` | `300` | Seconds to wait for LLM response |
| `CACHE_ENABLED` | `true` | Enable LLM response caching |
| `CACHE_TTL_HOURS` | `24` | Cache entry lifetime |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `STORY_ENABLED` | `false` | Auto-generate regression stories |
| `ALLURE_RESULTS_DIR` | `allure-results` | Allure raw results path |
| `ALLURE_REPORT_DIR` | `allure-report` | Generated report path |
| `BUG_REPORTS_DIR` | `bug_reports` | JSON bug reports path |
| `SCREENSHOTS_DIR` | `screenshots` | Screenshots path |

---

## Running the Framework

### Recommended: `run_smart.py` (new entry point)

```bash
# Pre-flight check only (no tests — verify everything is ready)
python run_smart.py --check

# Run with default settings from config.env
python run_smart.py

# Override autonomy level
python run_smart.py --level 1    # manual mode
python run_smart.py --level 2    # semi-auto (recommended)
python run_smart.py --level 3    # full auto

# Override target URL without editing config.env
python run_smart.py --urls https://your-site.com

# Override other settings
python run_smart.py --agents 2 --pages 5 --steps 4

# Clear LLM cache then run fresh
python run_smart.py --clear-cache

# Don't auto-open report after run
python run_smart.py --no-report
```

### Legacy: `run.py` (original entry point — still works)

```bash
python run.py
```

### Direct pytest (advanced)

```bash
pytest run_agents.py -v -s --alluredir allure-results
allure serve allure-results
```

---

## Autonomy Levels

The framework has 3 operating modes controlled by `AUTONOMY_LEVEL` in `config.env` or `--level` flag:

### Level 1 — Manual
```ini
AUTONOMY_LEVEL=1
```
- ✅ Runs pre-written stories from `stories/` directory
- ✅ Signal-based bug detection (console errors, failed requests)
- ❌ No AI calls — deterministic, fast, no Ollama needed
- **Use when:** Running known regression, CI/CD pipeline, Ollama unavailable

### Level 2 — Semi-Auto *(Recommended for pilot)*
```ini
AUTONOMY_LEVEL=2
```
- ✅ Everything in Level 1
- ✅ AI-powered navigation decisions
- ✅ AI test case generation (once per page)
- ✅ AI bug detection — but **only fires when signals exist** (console errors / failed requests / DOM errors)
- ❌ No visual detection, no auto story generation
- **Use when:** Daily smoke testing, exploring new features, standard QA runs

### Level 3 — Full Auto
```ini
AUTONOMY_LEVEL=3
```
- ✅ Everything in Level 2
- ✅ Visual bug detection via llava (if installed)
- ✅ AI URL ranking for smarter page prioritisation
- ✅ Auto story generation from discovered TCs (if `STORY_ENABLED=true`)
- **Use when:** Initial site exploration, full regression discovery, maximum coverage

---

## Project Structure

```
ai_tester_project/
│
├── 📄 run_smart.py              ← Main entry point (use this)
├── 📄 run.py                    ← Legacy entry point
├── 📄 run_agents.py             ← pytest test file (orchestrator)
├── 📄 config.py                 ← Config loader (reads config.env)
├── 📄 config.env                ← ⚙️  All settings live here
├── 📄 conftest.py               ← pytest hooks + Allure setup
├── 📄 run_context.py            ← Run ID + per-run directory paths
├── 📄 pytest.ini                ← pytest configuration
├── 📄 requirements.txt          ← Python dependencies
│
├── 📁 core/                     ← Framework infrastructure
│   ├── autonomy.py              ← Level 1/2/3 feature flag controller
│   └── cache.py                 ← LLM response cache (file-backed, TTL)
│
├── 📁 agents/                   ← Agent orchestration
│   ├── agent_controller.py      ← Multi-page crawl loop per URL
│   ├── ai_agent_worker.py       ← Per-page: TC gen + bug detect + actions
│   ├── story_generator.py       ← Auto-generates regression stories from TCs
│   └── story_runner.py          ← Executes YAML stories as regression tests
│
├── 📁 ai/                       ← AI/LLM layer
│   ├── ollama_client.py         ← Thread-safe Ollama API client
│   ├── bug_detector.py          ← Bug detection (text + visual)
│   └── test_generator.py        ← Test case generation
│
├── 📁 brain/                    ← Decision making
│   ├── decision_engine.py       ← AI decides next action
│   ├── action_executor.py       ← Executes actions with self-healing
│   └── smart_crawler.py         ← URL discovery + scoring + queue
│
├── 📁 browser/                  ← Browser control
│   ├── login_handler.py         ← Auto-detects and fills login forms
│   ├── dom_extractor.py         ← Extracts buttons, links, inputs, text
│   ├── screenshot.py            ← Captures step + bug screenshots
│   └── stealth.py               ← Anti-bot browser fingerprint patches
│
├── 📁 reporting/                ← Output generation
│   ├── bug_reporter.py          ← Saves JSON bug reports
│   ├── bug_report_viewer.py     ← Generates HTML bug report
│   ├── testcase_writer.py       ← Parses AI output → saves Excel TCs
│   ├── test_reporter.py         ← Allure test logging
│   └── tc_viewer.py             ← Generates HTML TC viewer
│
├── 📁 tests/                    ← pytest test files
│   ├── test_agent_results.py    ← Per-agent result assertions
│   ├── test_bugs.py             ← Bug report assertions
│   ├── test_generated_tcs.py    ← TC quality assertions
│   ├── test_ai_exploratory.py   ← Exploratory test assertions
│   └── test_user_stories.py     ← Manual story execution tests
│
├── 📁 stories/                  ← Manual + auto-generated stories
│   └── auto/                    ← Auto-generated stories (STORY_ENABLED=true)
│
└── 📁 [Generated on run]
    ├── allure-results/          ← Raw Allure test results
    ├── allure-report/           ← Generated HTML report
    ├── bug_reports/<run_id>/    ← JSON bug files per run
    ├── screenshots/<run_id>/    ← PNG screenshots per run
    ├── generated_test_cases/    ← Excel TC files per run
    └── .llm_cache/              ← LLM response cache files
```

---

## How It Works

### The Core Loop

```
For each URL:
  1. Open browser (with stealth patches)
  2. Navigate to URL
  3. Auto-login if credentials set + login page detected
  4. For each page (up to MAX_CRAWL_PAGES):
       a. Extract DOM (buttons, links, inputs, text)
       b. Take screenshot
       c. [ONCE] Generate 5 test cases via AI → save to Excel
       d. Check browser signals (console errors, failed requests)
       e. [IF signals] Detect bug via AI → save bug report
       f. For each step (up to MAX_STEPS):
            - AI decides: click_button / click_link / fill_input / scroll / stop
            - Execute with self-healing (5 fallback strategies)
            - If new errors after action → detect bug
       g. Discover links → score + queue next pages
  5. Generate Allure report + open automatically
```

### Self-Healing Actions

When the AI decides to `click_button:Sign In`, the executor tries 5 strategies:
1. Exact role match: `get_by_role("button", name="Sign In", exact=True)`
2. Partial role match: `get_by_role("button", name="Sign In", exact=False)`
3. Text contains: `locator("button:visible", has_text="Sign In")`
4. Case-insensitive: `locator("button:visible >> text=/Sign In/i")`
5. Fallback: first visible button

Every healing attempt is logged in Allure showing which strategies succeeded/failed.

### Bug Detection Flow

```
collect_page_signals()  ← console errors, failed requests, DOM error elements
       ↓
  any signals?
    NO  → skip LLM (page is clean)           ← saves ~60s per clean page
    YES → detect_bug() via LLM
            ↓
       llava available?
         YES → visual analysis first (catches layout bugs)
         NO  → text + signal analysis
                 ↓
            LLM unavailable?
               → signal_fallback() (pure rule-based, no AI)
```

---

## Output & Reports

After each run, 4 types of output are generated:

### 1. Allure Report (`allure-report/index.html`)
Rich HTML report with:
- Pass/fail status per agent and URL
- Step-by-step exploration timeline
- Screenshots at each step
- Bug details with severity classification
- TC download link (Excel)
- Crawl map showing pages visited

### 2. Bug Reports (`bug_reports/<run_id>/`)
One JSON file per bug found:
```json
{
  "run_id": "20260320_143022",
  "agent_id": "Agent-1",
  "title": "Console errors detected on checkout page",
  "severity": "High",
  "category": "console_error",
  "description": "...",
  "screenshot": "screenshots/20260320_143022/bug_step2.png"
}
```

### 3. Test Cases (`generated_test_cases/<run_id>/test_cases.xlsx`)
Excel file with columns: `TestID | Title | Steps | ExpectedResult | URL | CreatedAt`

### 4. HTML Bug Viewer + TC Viewer
Auto-opens after run:
- `bug_reports/<run_id>/report.html` — searchable bug list
- `generated_test_cases/<run_id>/viewer.html` — filterable TC table

---

## Parallel Agents

Test multiple URLs simultaneously:

```ini
# config.env
TARGET_URLS=https://site1.com,https://site2.com,https://site3.com
PARALLEL_AGENTS=2      # test 2 URLs at the same time
```

**Memory guide:**

| Agents | RAM needed | Notes |
|--------|-----------|-------|
| 1 | ~2.2 GB | Recommended for pilot |
| 2 | ~3.0 GB | Safe on 16GB |
| 3 | ~3.8 GB | Test carefully on 16GB |
| 4+ | ~5+ GB | Only on 32GB+ machines |

> **Note:** Ollama processes requests sequentially even with parallel agents — the parallelism is in browser automation, not LLM inference.

---

## Login Support

The framework auto-detects login pages and logs in using configured credentials.

```ini
LOGIN_EMAIL=your@email.com
LOGIN_PASSWORD=yourpassword
```

**Supported login patterns:**
- Standard email + password forms
- Username + password forms
- Multi-step login (email first → then password)
- Sites with cookie consent banners (auto-dismissed)
- Custom input IDs and names (20+ selector strategies)

**Not supported (auto-skipped with a warning):**
- SSO / OAuth / Google login
- CAPTCHA-protected login
- Two-factor authentication (2FA)

---

## Writing Manual Stories

For Level 1 (manual) mode, create YAML story files in `stories/`:

```yaml
# stories/my_login_test.yaml
site: https://your-site.com
stories:
  - name: "Successful login"
    description: "User logs in with valid credentials"
    priority: high
    steps:
      - action: navigate
        url: https://your-site.com/login
      - action: fill
        field: email
        value: test@example.com
      - action: fill
        field: password
        value: TestPass123
      - action: click
        text: Sign In
      - action: assert_url_contains
        value: dashboard
        message: Should redirect to dashboard after login

  - name: "Login with wrong password"
    description: "Error shown for invalid credentials"
    priority: high
    steps:
      - action: navigate
        url: https://your-site.com/login
      - action: fill
        field: email
        value: test@example.com
      - action: fill
        field: password
        value: wrongpassword
      - action: click
        text: Sign In
      - action: assert_text_present
        text: Invalid credentials
        message: Error message should appear
```

**Available actions:**

| Action | Required fields | Description |
|--------|----------------|-------------|
| `navigate` | `url` | Go to a URL |
| `fill` | `field`, `value` | Fill an input field |
| `click` | `text` | Click a button or link |
| `assert_text_present` | `text` | Assert text exists on page |
| `assert_url_contains` | `value` | Assert URL contains string |
| `assert_element` | `selector` | Assert CSS selector exists |
| `wait` | `ms` | Wait N milliseconds |
| `screenshot` | `label` (optional) | Take a screenshot |
| `scroll` | `amount` (optional) | Scroll down N pixels |
| `login` | `username`, `password` | Use smart login handler |

---

## Jenkins / CI Integration

A `Jenkinsfile` is included. Key environment variables to set in Jenkins:

```groovy
environment {
    TARGET_URLS     = "https://your-site.com"
    AUTONOMY_LEVEL  = "2"
    PARALLEL_AGENTS = "1"
    MAX_CRAWL_PAGES = "3"
    HEADLESS        = "true"
    OLLAMA_HOST     = "http://ollama-server:11434"
    LOGIN_EMAIL     = credentials('qa-login-email')
    LOGIN_PASSWORD  = credentials('qa-login-password')
}
```

For detailed Jenkins setup, see `JENKINS_SETUP.md`.

---

## Troubleshooting

### Ollama not responding
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Pull the model configured in config.env
ollama pull llama3:latest
```

### Tests time out or hang
```ini
# Reduce scope in config.env:
MAX_CRAWL_PAGES=2
MAX_STEPS=2
OLLAMA_READ_TIMEOUT=400   # increase if model is slow
```

### Browser launches but pages don't load
```ini
# Try disabling stealth mode
STEALTH_MODE=false
# Try headed mode to see what's happening
HEADLESS=false
```

### Login not detected
```ini
# Make sure credentials are set
LOGIN_EMAIL=yourusername
LOGIN_PASSWORD=yourpassword
# Check logs — look for [LOGIN] lines
LOG_LEVEL=DEBUG
```

### Allure report doesn't open
```bash
# Check allure is installed
allure --version

# Serve results manually
allure serve allure-results
```

### "No module named pyyaml"
```bash
pip install pyyaml
```

### LLM responses are slow (>5 min per call)
```ini
# Switch to a lighter model
OLLAMA_MODEL=llama3.2    # 1.4GB vs 4.7GB for llama3
# Or phi3:mini which is very fast
OLLAMA_MODEL=phi3:mini
```

### High memory usage
```ini
PARALLEL_AGENTS=1     # run sequentially
HEADLESS=true         # saves ~200MB
MAX_CRAWL_PAGES=2     # fewer pages open at once
```

### Run the pre-flight check
```bash
python run_smart.py --check
```
This will tell you exactly what's wrong before wasting a full run.

---

## Performance Tips (16GB RAM)

```ini
# Optimal config.env for 16GB machines:
OLLAMA_MODEL=llama3.2      # 1.4GB (vs 4.7GB for llama3)
PARALLEL_AGENTS=1          # sequential is safer for pilot
HEADLESS=true              # saves ~200MB
MAX_CRAWL_PAGES=3          # enough for good coverage
MAX_STEPS=3                # enough for exploration
CACHE_ENABLED=true         # huge win on repeat runs — same page = instant
STORY_ENABLED=false        # disable until core loop validated
AUTONOMY_LEVEL=2           # no visual detection (saves llava memory)
```

**Expected run time** at these settings:
- 1 URL, 3 pages, 3 steps ≈ **8–12 minutes**
- 2 URLs sequential ≈ **16–24 minutes**
- 2 URLs parallel (PARALLEL_AGENTS=2) ≈ **10–14 minutes**

---

## FAQ

**Q: Does it work on sites behind VPN?**
A: Yes, as long as the machine running the framework has VPN access. The browser uses the system's network.

**Q: Will it break my site by clicking random things?**
A: It avoids logout links, external URLs, and destructive patterns. For safety, test on a staging environment first.

**Q: Can I use GPT-4 or Claude instead of Ollama?**
A: Not out of the box — the framework calls the Ollama API directly. You'd need to modify `ai/ollama_client.py` to call a different API. This is intentional — keeping LLMs local avoids sending your site's content to external services.

**Q: What if Ollama is down mid-run?**
A: The framework degrades gracefully — signal-based bug detection continues, TC generation uses templates, navigation stops (agent says "stop"). The run completes without crashing.

**Q: How do I test the same site daily in CI?**
A: Set `AUTONOMY_LEVEL=1` + write stories for your critical paths. Level 1 needs no Ollama — fast, deterministic, CI-safe.

**Q: The AI generates bad/generic test cases. How do I improve them?**
A: Try a larger model (`llama3` instead of `llama3.2`), increase `MAX_STEPS` so the agent sees more of the page, or check that `LOG_LEVEL=DEBUG` to see exactly what page content is being sent to the LLM.

**Q: Can I add my own bug detection rules?**
A: Yes — in `ai/bug_detector.py`, the `_signal_fallback()` function is pure Python with no AI. Add your own patterns there. It runs even when Ollama is unavailable.

---

## Pilot Readiness Checklist

Run through this before declaring the framework ready for your team:

- [ ] `python run_smart.py --check` passes with no fatal errors
- [ ] `python run_smart.py --level 2` completes without crashing
- [ ] Allure report opens automatically after run
- [ ] `bug_reports/` contains at least one structured JSON file
- [ ] `generated_test_cases/` contains an Excel file with test cases
- [ ] Run time for 1 URL, 3 pages, 3 steps is under 15 minutes
- [ ] `python run_smart.py --level 1` runs stories cleanly (no AI calls in logs)
- [ ] At least one real QA engineer has reviewed the generated TCs for quality

---

*Built with Playwright + Python + Ollama. Designed for QA engineers, not AI researchers.*
