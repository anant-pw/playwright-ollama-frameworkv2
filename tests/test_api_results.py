# tests/test_api_results.py
#
# Dedicated Allure card for API testing results.
# Shows as its own test row on the Allure dashboard:
#   🔌 API Results — Agent-1 | 1 endpoint | 1 bug
#
# Loads API results from the JSON file saved by api_tester.py
# after each run. One test per agent — mirrors test_agent_results.py pattern.
#
# PASS = all endpoints clean
# FAIL = any API bugs found (intentional — shows RED in Allure)

import pytest
import allure
import glob
import json
import os
from run_agents import _shared


def _get_run_id() -> str:
    try:
        from run_context import RUN_ID
        return RUN_ID
    except Exception:
        return None


def _load_api_bugs_for_agent(run_id: str, agent_id: str) -> list:
    """Load API bugs (source='api') for this agent from bug_reports."""
    from config import CFG
    bug_dir = os.path.join(CFG.bug_reports_dir, run_id)
    if not os.path.isdir(bug_dir):
        return []
    bugs = []
    for f in sorted(glob.glob(os.path.join(bug_dir, "bug_*.json"))):
        try:
            data = json.load(open(f, encoding="utf-8"))
            # Only API-detected bugs
            source = data.get("source", "") or \
                     data.get("additional_info", {}).get("detection_source", "")
            bug_agent = data.get("agent_id", "") or \
                        data.get("additional_info", {}).get("agent_id", "")
            if source == "api" and bug_agent == agent_id:
                data["_file"] = f
                bugs.append(data)
        except Exception:
            pass
    return bugs


def _load_api_summary_for_agent(run_id: str, agent_id: str) -> dict:
    """Load API test summary JSON if saved."""
    try:
        from config import CFG
        path = os.path.join(CFG.bug_reports_dir, run_id,
                            f"api_summary_{agent_id}.json")
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))
    except Exception:
        pass
    return {}


def pytest_generate_tests(metafunc):
    if "api_agent" not in metafunc.fixturenames:
        return

    # Only generate if API testing was enabled
    api_enabled = os.environ.get("API_TESTING", "true").lower() \
                  in ("1", "true", "yes")
    if not api_enabled:
        metafunc.parametrize("api_agent", [], ids=[])
        return

    from config import CFG
    params, ids = [], []
    for i, url in enumerate(CFG.target_urls):
        agent_id = f"Agent-{i+1}"
        params.append({"agent_id": agent_id, "url": url, "index": i+1})
        domain = url.replace("https://","").replace("http://","").split("/")[0]
        ids.append(f"{agent_id} → {domain}")
    metafunc.parametrize("api_agent", params, ids=ids)


@allure.feature("🔌 API Test Results")
def test_api_results(api_agent):
    """
    Dedicated Allure card for API testing.
    PASS = no API bugs. FAIL = API bugs found.
    """
    agent_id = api_agent["agent_id"]
    url      = api_agent["url"]
    run_id   = _get_run_id()

    # Load API bugs for this agent
    api_bugs = _load_api_bugs_for_agent(run_id, agent_id) if run_id else []
    summary  = _load_api_summary_for_agent(run_id, agent_id) if run_id else {}

    # Get endpoint count from shared results if available
    results     = _shared.all()
    agent_data  = next((r for r in results if r["agent_id"] == agent_id), None)
    duration    = agent_data.get("duration", 0) if agent_data else 0

    endpoint_count = summary.get("endpoints_tested", len(api_bugs) or 0)
    bug_icon       = "🐛" if api_bugs else "✅"

    # ── Dashboard title ───────────────────────────────────────────────────────
    allure.dynamic.title(
        f"{agent_id} | API | {bug_icon} {len(api_bugs)} bug(s) "
        f"| {endpoint_count} endpoint(s) tested"
    )
    allure.dynamic.story(f"Run {run_id}")
    allure.dynamic.severity(
        allure.severity_level.NORMAL if not api_bugs else
        allure.severity_level.CRITICAL
        if any(b.get("severity","").lower() in ("critical","high")
               for b in api_bugs)
        else allure.severity_level.MINOR
    )
    allure.dynamic.tag("api-testing")
    allure.dynamic.tag(f"run:{run_id}")
    allure.dynamic.description(
        f"**Agent:** {agent_id}  \n"
        f"**URL:** {url}  \n"
        f"**Run ID:** {run_id}  \n"
        f"**Endpoints tested:** {endpoint_count}  \n"
        f"**API bugs found:** {len(api_bugs)}  \n"
    )

    # ── STEP 1: Summary ───────────────────────────────────────────────────────
    with allure.step(f"📊 API Test Summary — {agent_id}"):
        allure.attach(
            f"Agent          : {agent_id}\n"
            f"Site           : {url}\n"
            f"Endpoints found: {endpoint_count}\n"
            f"Bugs detected  : {len(api_bugs)}\n"
            f"Run ID         : {run_id}\n\n"
            f"Checks performed:\n"
            f"  ✓ HTTP status codes (5xx = Critical, 401/403 = flagged)\n"
            f"  ✓ Response time vs {os.environ.get('API_TIMEOUT_MS','3000')}ms budget\n"
            f"  ✓ Security headers (X-Frame-Options, CSP, HSTS etc)\n"
            f"  ✓ Sensitive endpoints without authentication\n",
            name="API Summary",
            attachment_type=allure.attachment_type.TEXT,
        )

    # ── STEP 2: Endpoints tested (from summary if available) ─────────────────
    endpoints_list = summary.get("endpoints", [])
    if endpoints_list:
        with allure.step(f"🌐 Endpoints Tested: {len(endpoints_list)}"):
            lines = [f"{'Method':<8} {'Status':<6} {'Time':>8}  URL", "─" * 70]
            for ep in endpoints_list:
                method  = ep.get("method", "GET")
                status  = str(ep.get("status", "?"))
                time_ms = f"{ep.get('time_ms','?')}ms" if ep.get("time_ms") else "?"
                epurl   = ep.get("url", "")[:55]
                bug_tag = " ← BUG" if ep.get("has_bugs") else ""
                lines.append(f"{method:<8} {status:<6} {time_ms:>8}  {epurl}{bug_tag}")
            allure.attach(
                "\n".join(lines),
                name="Endpoints Tested",
                attachment_type=allure.attachment_type.TEXT,
            )
    elif not api_bugs:
        with allure.step("🌐 Endpoints Tested"):
            allure.attach(
                "No API endpoints were captured during this run.\n\n"
                "This is normal for sites that don't make XHR/fetch calls\n"
                "during the pages visited (e.g. static sites).\n\n"
                "To see more API activity, increase MAX_CRAWL_PAGES or\n"
                "visit pages with dynamic content (login, checkout, search).",
                name="No Endpoints",
                attachment_type=allure.attachment_type.TEXT,
            )

    # ── STEP 3: API Bugs (flat, with details) ─────────────────────────────────
    bug_label = f"🐛 API Bugs: {len(api_bugs)}" if api_bugs else "✅ No API Bugs"
    with allure.step(bug_label):
        if not api_bugs:
            allure.attach(
                "No API bugs detected on this run.\n"
                "All tested endpoints returned acceptable status codes,\n"
                "response times, and security headers.",
                name="Clean",
                attachment_type=allure.attachment_type.TEXT,
            )
        else:
            # Summary table
            rows = ["#    Severity    Category          Title", "─" * 70]
            for i, bug in enumerate(api_bugs, 1):
                sev  = bug.get("severity", "Low")
                cat  = bug.get("additional_info", {}).get("category", "api")[:16]
                title = bug.get("title", "")[:40]
                rows.append(f"{i:<5}{sev:<12}{cat:<18}{title}")
            allure.attach(
                "\n".join(rows),
                name="API Bug Summary",
                attachment_type=allure.attachment_type.TEXT,
            )

            # Each bug as its own step
            for i, bug in enumerate(api_bugs, 1):
                sev   = bug.get("severity", "Low")
                title = bug.get("title", "Unknown")
                desc  = bug.get("description", "")
                info  = bug.get("additional_info", {})
                cat   = info.get("category", "api")
                ts    = bug.get("timestamp", "")

                sev_icon = {"critical": "🔴", "high": "🟠",
                            "medium":   "🟡", "low":  "🟢"}.get(
                    sev.lower(), "⚪")

                with allure.step(f"{sev_icon} API Bug {i}: [{sev}] {title}"):
                    allure.attach(
                        f"Title    : {title}\n"
                        f"Severity : {sev}\n"
                        f"Category : {cat}\n"
                        f"Time     : {ts}\n\n"
                        f"Description:\n{desc}",
                        name=f"API Bug {i} Details",
                        attachment_type=allure.attachment_type.TEXT,
                    )

    # ── Intentional fail when API bugs found ──────────────────────────────────
    if api_bugs:
        severities = [b.get("severity", "Low").lower() for b in api_bugs]
        top = ("critical" if "critical" in severities else
               "high"     if "high"     in severities else
               "medium"   if "medium"   in severities else "low")
        allure.dynamic.severity({
            "critical": allure.severity_level.CRITICAL,
            "high":     allure.severity_level.CRITICAL,
            "medium":   allure.severity_level.NORMAL,
            "low":      allure.severity_level.MINOR,
        }.get(top, allure.severity_level.MINOR))

        pytest.fail(
            f"API testing found {len(api_bugs)} bug(s) on {url}:\n" +
            "\n".join(
                f"  [{b.get('severity','?').upper()}] {b.get('title','?')}"
                for b in api_bugs
            )
        )
