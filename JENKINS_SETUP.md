# Jenkins Setup Guide — AI QA Framework v2

## Prerequisites

Before starting, confirm:
- [ ] Jenkins installed and running (`http://localhost:8080` or your server)
- [ ] Python 3.10+ installed on the Jenkins machine
- [ ] Git installed
- [ ] Ollama running as a service (`ollama serve`)
- [ ] `llama3.2:latest` pulled: `ollama pull llama3.2`
- [ ] Project in a Git repo

---

## Step 1 — Install Jenkins plugins

**Jenkins → Manage Jenkins → Plugins → Available plugins**

Install these:

| Plugin | Why |
|--------|-----|
| **Allure Jenkins Plugin** | Publishes Allure HTML report on each build |
| **Pipeline** | Enables Jenkinsfile pipeline jobs |
| **Git** | Clones your repo |
| **Workspace Cleanup** | Cleans temp files after build |
| **Timestamper** | Adds timestamps to console output |

Restart Jenkins after installing.

---

## Step 2 — Configure Allure plugin

**Jenkins → Manage Jenkins → Tools → Allure Commandline**

1. Click **Add Allure Commandline**
2. Name: `allure`
3. Tick **Install automatically**
4. Version: latest (2.27.0+)
5. Save

---

## Step 3 — Create the Pipeline job

1. Jenkins home → **New Item**
2. Name: `AI-QA-Framework`
3. Select **Pipeline** → OK
4. Job config:
   - **Build Triggers** → Poll SCM: `H 9 * * 1-5` (9am Mon–Fri)
   - **Pipeline** → Definition: **Pipeline script from SCM**
   - SCM: **Git** → your repo URL
   - Branch: `*/main`
   - Script Path: `Jenkinsfile`
5. Save

---

## Step 4 — Configure Ollama as a Windows Service

Jenkins runs in the background — Ollama must start automatically.

```cmd
# Download NSSM from https://nssm.cc/download
# Then run as Administrator:

nssm install OllamaService "C:\Users\YOUR_USER\AppData\Local\Programs\Ollama\ollama.exe"
nssm set OllamaService AppParameters "serve"
nssm set OllamaService Start SERVICE_AUTO_START
nssm start OllamaService

# Verify:
curl http://localhost:11434/api/tags
```

---

## Step 5 — Run Jenkins under your user account

Jenkins runs as SYSTEM by default — it can't access your Python venv.

1. Open **Services** (`services.msc`)
2. Find **Jenkins** → Properties → Log On tab
3. Switch to **This account** → enter your Windows username + password
4. Restart Jenkins

---

## Step 6 — First build

1. Job → **Build with Parameters**
2. Recommended first run settings:

| Parameter | Value |
|-----------|-------|
| TARGET_URLS | `https://www.saucedemo.com` |
| AUTONOMY_LEVEL | `2` |
| MAX_STEPS | `3` |
| MAX_CRAWL_PAGES | `3` |
| PARALLEL_AGENTS | `1` |
| OLLAMA_MODEL | `llama3.2:latest` |
| API_TESTING | ✅ checked |
| STORY_ENABLED | unchecked |

3. Click **Build**
4. Click build number → **Console Output** to watch live

---

## Step 7 — View Allure report

After build completes:
- Build page → **Allure Report** link
- Or: `http://YOUR_JENKINS/job/AI-QA-Framework/lastBuild/allure`

Report shows:
- **Overview** — pass/fail summary, bug count, TC count
- **🤖 Agent Run Results** — per-agent: bugs found, TCs generated, duration
- **🔌 API Test Results** — per-agent: API endpoints tested, security issues
- **🐛 Bugs Detected** — each bug as its own card with screenshot
- **🧪 AI Generated Test Cases** — all TCs with Excel download
- **🔄 Regression Stories** — auto-generated story execution results (if enabled)
- **Categories** — bugs grouped by severity (🔴 Critical → 🟢 Low)
- **Environment** — URL, model, autonomy level, browser used

---

## Jenkins Build Parameters Reference

All parameters map directly to `config.env` settings.
CLI overrides take effect immediately — no file editing needed.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TARGET_URLS` | saucedemo.com | Comma-separated URLs, no spaces |
| `AUTONOMY_LEVEL` | `2` | 1=Manual, 2=Semi-Auto, 3=Full Auto |
| `BROWSER` | `chromium` | chromium / firefox / webkit |
| `MAX_STEPS` | `3` | AI actions per page |
| `MAX_CRAWL_PAGES` | `3` | Pages per URL |
| `MAX_CRAWL_DEPTH` | `2` | Link follow depth |
| `PARALLEL_AGENTS` | `1` | URLs tested simultaneously |
| `OLLAMA_MODEL` | `llama3.2:latest` | Must match `ollama list` output |
| `STEALTH_MODE` | `true` | Bypass bot detection (keep true) |
| `LOGIN_EMAIL` | *(empty)* | Leave blank if no login needed |
| `LOGIN_PASSWORD` | *(empty)* | Stored as Jenkins secret |
| `STORY_ENABLED` | `false` | Auto-generate regression stories |
| `API_TESTING` | `true` | Test captured API endpoints |
| `API_TIMEOUT_MS` | `3000` | API response budget in ms |
| `SELF_HEALING` | `true` | true=exploratory, false=strict |
| `CACHE_ENABLED` | `true` | Cache LLM responses 24h |

---

## Autonomy Level Guide for CI

| Level | Use case | LLM calls | Run time |
|-------|----------|-----------|----------|
| `1` — Manual | Daily regression on stable sites | 0 (no AI) | Fast (~2 min) |
| `2` — Semi-Auto | Daily smoke + exploration | ~35 per URL | Medium (~6–10 min) |
| `3` — Full Auto | Weekly full exploration | ~60+ per URL | Slow (~15–20 min) |

**Recommended CI schedule:**
```
Daily (9am):    AUTONOMY_LEVEL=2, MAX_STEPS=3, MAX_CRAWL_PAGES=3
Weekly (Mon):   AUTONOMY_LEVEL=3, MAX_STEPS=5, MAX_CRAWL_PAGES=5, STORY_ENABLED=true
```

---

## Understanding Build Results

A **FAILED** build does not mean the framework crashed.
It usually means the agent found bugs — which is the point.

| Build result | Meaning |
|-------------|---------|
| ✅ PASSED | No bugs detected, all TCs generated, API clean |
| ❌ FAILED | Bugs were found (check Allure — this is correct behaviour) |
| ⚠️ UNSTABLE | Partial failures — some agents passed, some failed |
| 💥 ERROR | Framework crash — check console output |

---

## Memory Guide for Parallel Agents

| `PARALLEL_AGENTS` | RAM needed | Notes |
|------------------|-----------|-------|
| 1 | ~2.2 GB | Safe on any machine |
| 2 | ~3.0 GB | Safe on 16GB |
| 3 | ~3.8 GB | Test carefully on 16GB |
| 4+ | ~5+ GB | 32GB+ recommended |

Jenkins agent should have `# of executors = 1` — Ollama is single-threaded,
so multiple concurrent builds don't help and will cause timeouts.

---

## Troubleshooting

**`venv not found` / pip errors**
→ Add Python to PATH for the Jenkins user account

**`playwright not found` / browser launch fails**
→ Run in Jenkins build step:
```bat
call venv\Scripts\activate.bat && playwright install chromium
```

**`Ollama unavailable` in build**
→ Check service: `sc query OllamaService`
→ Test: `curl http://localhost:11434/api/tags`

**`Model 'llama3.2' not found`**
→ Run: `ollama pull llama3.2` then restart OllamaService

**Allure report empty**
→ `allure-results/` must contain `.json` files
→ Check Archive Artifacts stage for the directory

**Build result always FAILED even on clean sites**
→ Check if API testing is flagging security header bugs
→ Set `API_TESTING=false` to isolate

**SSL warnings flooding console**
→ Already suppressed with `-W ignore::urllib3.exceptions.InsecureRequestWarning`
→ If still showing, add `PYTHONWARNINGS=ignore` to environment block

**Config prints twice in console output**
→ Remove last line of `config.py`: `print("\n" + CFG.summary() + "\n")`
→ The framework now prints config once in `run_smart.py`
