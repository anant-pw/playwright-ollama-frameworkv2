# tests/test_agent_results.py
#
# REDESIGNED: Clean, flat, intuitive Allure report
# ─────────────────────────────────────────────────
# OLD problems:
#   - Dashboard showed no agent info
#   - Had to dig 3+ levels deep to see bugs/TCs
#   - Confusing nesting of steps inside steps
#   - No clear visual hierarchy
#
# NEW design:
#   - ONE test per agent = one row in Allure dashboard
#   - Title shows everything at a glance: Agent | URL | Bugs | TCs | Time
#   - Top-level steps: Summary → Bugs → Test Cases (flat, not nested)
#   - Each bug = its own clear step with screenshot immediately visible
#   - PASS = no bugs, FAIL = bugs found (correct, intentional)

import pytest
import allure
import glob
import json
import os
import base64
from run_agents import _shared


def _get_run_id():
    try:
        from run_context import RUN_ID
        return RUN_ID
    except Exception:
        return None


def _load_bugs_for_agent(run_id: str, agent_id: str) -> list:
    from config import CFG
    bug_dir = os.path.join(CFG.bug_reports_dir, run_id)
    if not os.path.isdir(bug_dir):
        return []

    all_bugs = []
    my_bugs  = []

    for f in sorted(glob.glob(os.path.join(bug_dir, "bug_*.json"))):
        try:
            data = json.load(open(f, encoding="utf-8"))
            data["_file"] = f
            all_bugs.append(data)
            bug_agent = data.get("agent_id", "") or \
                        data.get("additional_info", {}).get("agent_id", "")
            if bug_agent == agent_id:
                my_bugs.append(data)
        except Exception:
            pass

    # Fallback: no agent tags → give all bugs to first agent
    if not any(b.get("agent_id") for b in all_bugs) and all_bugs:
        results = _shared.all()
        idx     = next((i for i, r in enumerate(results)
                        if r["agent_id"] == agent_id), 0)
        n       = max(len(results), 1)
        chunk   = max(len(all_bugs) // n, 1)
        return all_bugs[idx * chunk:(idx + 1) * chunk]

    return my_bugs


def _load_tcs_for_agent(run_id: str, url: str) -> list:
    tc_file = os.path.join("generated_test_cases", run_id, "test_cases.xlsx")
    if not os.path.exists(tc_file):
        return []
    try:
        import pandas as pd
        df     = pd.read_excel(tc_file)
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        mask   = df["URL"].astype(str).str.contains(domain, na=False)
        return df[mask].to_dict("records")
    except Exception:
        return []


def pytest_generate_tests(metafunc):
    if "agent_result" in metafunc.fixturenames:
        from config import CFG
        params, ids = [], []
        for i, url in enumerate(CFG.target_urls):
            agent_id = f"Agent-{i+1}"
            params.append({"agent_id": agent_id, "url": url, "index": i + 1})
            domain = url.replace("https://","").replace("http://","").split("/")[0]
            ids.append(f"{agent_id} → {domain}")
        metafunc.parametrize("agent_result", params, ids=ids)


# ── Main test — one per agent ─────────────────────────────────────────────────

@allure.feature("🤖 Agent Run Results")
def test_agent_result(agent_result):
    agent_id = agent_result["agent_id"]
    url      = agent_result["url"]
    run_id   = _get_run_id()

    # Load data
    results    = _shared.all()
    agent_data = next((r for r in results if r["agent_id"] == agent_id), None)
    bugs_list  = _load_bugs_for_agent(run_id, agent_id) if run_id else []
    tcs_list   = _load_tcs_for_agent(run_id, url) if run_id else []

    # ── Dynamic title — visible directly on Allure dashboard ─────────────────
    duration = agent_data.get("duration", 0) if agent_data else 0
    status   = agent_data.get("status", "UNKNOWN") if agent_data else "UNKNOWN"
    bug_icon = "🐛" if bugs_list else "✅"

    allure.dynamic.title(
        f"{agent_id} | {url.replace('https://','').replace('http://','').rstrip('/')} "
        f"| {bug_icon} {len(bugs_list)} bugs | 🧪 {len(tcs_list)} TCs "
        f"| ⏱ {duration:.0f}s"
    )
    allure.dynamic.story(f"Run {run_id}")
    allure.dynamic.description(
        f"**URL:** {url}  \n"
        f"**Run ID:** {run_id}  \n"
        f"**Status:** {'✅ PASS' if status == 'PASS' else '❌ FAIL'}  \n"
        f"**Duration:** {duration:.0f}s ({duration/60:.1f} min)  \n"
        f"**Bugs found:** {len(bugs_list)}  \n"
        f"**TCs generated:** {len(tcs_list)}  \n"
    )
    allure.dynamic.severity(
        allure.severity_level.CRITICAL if bugs_list
        else allure.severity_level.NORMAL
    )

    # ── STEP 1: Run Summary (always first, always visible) ───────────────────
    with allure.step(f"📊 Run Summary — {agent_id}"):
        pages = agent_data.get("pages", "?") if agent_data else "?"
        allure.attach(
            f"Agent ID  : {agent_id}\n"
            f"URL       : {url}\n"
            f"Status    : {'✅ PASS' if status == 'PASS' else '❌ FAIL'}\n"
            f"Duration  : {duration:.0f}s ({duration/60:.1f} min)\n"
            f"Bugs Found: {len(bugs_list)}\n"
            f"TCs Built : {len(tcs_list)}\n"
            f"Run ID    : {run_id}\n",
            name="Agent Summary",
            attachment_type=allure.attachment_type.TEXT,
        )

    # ── STEP 2: Bugs (flat list — no deep nesting) ───────────────────────────
    bug_step_label = (
        f"🐛 Bugs Found: {len(bugs_list)}"
        if bugs_list else
        "✅ No Bugs Found"
    )
    with allure.step(bug_step_label):
        if not bugs_list:
            allure.attach(
                "No bugs detected on this URL during the run.",
                name="Result",
                attachment_type=allure.attachment_type.TEXT,
            )
        else:
            # Quick summary table first
            rows = ["#    Severity    Title", "─" * 60]
            for i, bug in enumerate(bugs_list, 1):
                sev   = bug.get("severity", "Medium")
                title = bug.get("title", "Unknown")[:45]
                rows.append(f"{i:<5}{sev:<12}{title}")
            allure.attach(
                "\n".join(rows),
                name="Bug Summary Table",
                attachment_type=allure.attachment_type.TEXT,
            )

            # Each bug as its own flat step
            for i, bug in enumerate(bugs_list, 1):
                sev   = bug.get("severity", "Medium")
                title = bug.get("title", "Unknown")
                desc  = bug.get("description", "")
                info  = bug.get("additional_info", {})
                src   = info.get("detection_source", bug.get("source", "text"))
                burl  = info.get("url", url)
                ts    = bug.get("timestamp", "")

                sev_icon = {"critical": "🔴", "high": "🟠",
                            "medium": "🟡", "low": "🟢"}.get(
                    sev.lower(), "⚪")

                with allure.step(f"{sev_icon} Bug {i}: [{sev}] {title}"):
                    allure.attach(
                        f"Title      : {title}\n"
                        f"Severity   : {sev}\n"
                        f"Detected by: {src}\n"
                        f"URL        : {burl}\n"
                        f"Time       : {ts}\n\n"
                        f"Description:\n{desc}",
                        name=f"Bug {i} Details",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    # Screenshot immediately under the bug — no extra clicking
                    ss = bug.get("screenshot")
                    if ss:
                        abs_ss = os.path.abspath(ss)
                        if os.path.exists(abs_ss):
                            with open(abs_ss, "rb") as f:
                                allure.attach(
                                    f.read(),
                                    name=f"📸 Bug {i} Screenshot",
                                    attachment_type=allure.attachment_type.PNG,
                                )

    # ── STEP 3: Test Cases (grouped by page) ─────────────────────────────────
    # TCs loaded directly from Excel — reliable even if agent counter showed 0
    tc_step_label = f"🧪 Test Cases Generated: {len(tcs_list)}"
    with allure.step(tc_step_label):
        if not tcs_list:
            allure.attach(
                "No test cases found in Excel for this URL.\n"
                "Possible cause: Ollama timed out during TC generation.",
                name="Result",
                attachment_type=allure.attachment_type.TEXT,
            )
        else:
            # Excel download first — most useful thing, put it at the top
            try:
                tc_file = os.path.join("generated_test_cases", run_id,
                                       "test_cases.xlsx")
                if os.path.exists(tc_file):
                    with open(tc_file, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    allure.attach(
                        f'<!DOCTYPE html><html><body style="font-family:sans-serif;'
                        f'padding:20px">'
                        f'<h3>{agent_id} — {len(tcs_list)} Test Cases | Run: {run_id}</h3>'
                        f'<a href="data:application/vnd.openxmlformats-officedocument'
                        f'.spreadsheetml.sheet;base64,{b64}" '
                        f'download="test_cases_{run_id}.xlsx" '
                        f'style="display:inline-block;padding:12px 24px;'
                        f'background:#0052cc;color:white;border-radius:6px;'
                        f'text-decoration:none;font-weight:600;font-size:15px">'
                        f'⬇ Download All {len(tcs_list)} TCs (Excel)'
                        f'</a></body></html>',
                        name="⬇ Download TCs (Excel)",
                        attachment_type=allure.attachment_type.HTML,
                    )
            except Exception:
                pass

            # Group by page URL — one readable block per page
            from collections import defaultdict
            by_page = defaultdict(list)
            for tc in tcs_list:
                by_page[str(tc.get("URL", url))].append(tc)

            for page_url, page_tcs in by_page.items():
                page_label = (page_url.replace("https://", "")
                                      .replace("http://", "")
                                      .rstrip("/"))
                with allure.step(f"📄 {page_label} — {len(page_tcs)} TCs"):
                    lines = []
                    for j, tc in enumerate(page_tcs, 1):
                        lines += [
                            f"{'─' * 50}",
                            f"TC {j:02d}: {tc.get('Title', '')}",
                            f"  Steps   : {tc.get('Steps', '')}",
                            f"  Expected: {tc.get('ExpectedResult', '')}",
                            "",
                        ]
                    allure.attach(
                        "\n".join(lines),
                        name=f"TCs — {page_label}",
                        attachment_type=allure.attachment_type.TEXT,
                    )

    # ── pytest.fail() MUST be LAST — after ALL steps are written to Allure ───
    # Anything after fail() is skipped. Bugs + TCs steps must complete first.
    if agent_data and agent_data.get("status") == "FAIL":
        pytest.fail(
            f"{agent_id} agent crashed: {agent_data.get('error', 'unknown error')}")

    if bugs_list:
        severities = [b.get("severity", "Medium").lower() for b in bugs_list]
        top = ("critical" if "critical" in severities else
               "high"     if "high"     in severities else
               "medium"   if "medium"   in severities else "low")
        allure.dynamic.severity({
            "critical": allure.severity_level.CRITICAL,
            "high":     allure.severity_level.CRITICAL,
            "medium":   allure.severity_level.NORMAL,
            "low":      allure.severity_level.MINOR,
        }.get(top, allure.severity_level.NORMAL))
        pytest.fail(
            f"{agent_id} found {len(bugs_list)} bug(s) on {url}:\n" +
            "\n".join(
                f"  [{b.get('severity', '?').upper()}] {b.get('title', '?')}"
                for b in bugs_list
            )
        )
