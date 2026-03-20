# tests/test_bugs.py
#
# REDESIGNED: One Allure test per bug — each bug is its own row on the dashboard
# ────────────────────────────────────────────────────────────────────────────────
# OLD: All bugs crammed into one test with deep nested steps
# NEW: Each bug = its own pytest test = its own Allure card
#      Title visible on dashboard: [CRITICAL] 404 Error in Cart Page
#      Screenshot visible immediately — no digging

import pytest
import allure
import glob
import json
import os

_SEVERITY_MAP = {
    "critical": allure.severity_level.CRITICAL,
    "high":     allure.severity_level.CRITICAL,
    "medium":   allure.severity_level.NORMAL,
    "low":      allure.severity_level.MINOR,
}

_SEV_ICON = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
}


def _get_run_id() -> str:
    try:
        from run_context import RUN_ID
        return RUN_ID
    except Exception:
        return None


def _load_bugs(run_id: str) -> list:
    from config import CFG
    bug_dir = os.path.join(CFG.bug_reports_dir, run_id)
    if not os.path.isdir(bug_dir):
        return []
    bugs = []
    for f in sorted(glob.glob(os.path.join(bug_dir, "bug_*.json"))):
        try:
            data = json.load(open(f, encoding="utf-8"))
            data["_file"] = f
            bugs.append(data)
        except Exception:
            pass
    return bugs


def _load_most_recent_bugs():
    from config import CFG
    base = CFG.bug_reports_dir
    if not os.path.isdir(base):
        return None, []
    for folder in sorted(os.listdir(base), reverse=True):
        if os.path.isdir(os.path.join(base, folder)):
            bugs = _load_bugs(folder)
            if bugs:
                return folder, bugs
    return None, []


def pytest_generate_tests(metafunc):
    """
    Generate one test per bug from CURRENT RUN ONLY.
    Never fall back to previous runs — if this run has no bugs, show PASS.
    """
    if "bug_data" not in metafunc.fixturenames:
        return

    run_id = _get_run_id()
    bugs   = _load_bugs(run_id) if run_id else []

    # ── DO NOT fall back to previous runs ─────────────────────────────────────
    # Old code did: if not bugs: run_id, bugs = _load_most_recent_bugs()
    # This caused bugs from yesterday to appear in today's clean run.
    # If current run has no bugs → show one green "no bugs" card. That's correct.

    if not bugs:
        metafunc.parametrize("bug_data", [None], ids=["no-bugs-this-run"])
        return

    ids = []
    for i, bug in enumerate(bugs, 1):
        sev   = bug.get("severity", "Medium").upper()
        title = bug.get("title", "Unknown")[:40].replace(" ", "-")
        ids.append(f"Bug{i}-{sev}-{title}")

    metafunc.parametrize("bug_data", bugs, ids=ids)


@allure.feature("🐛 Bugs Detected")
def test_bug(bug_data):
    """One test per bug. RED = bug found (intentional). Click to see details + screenshot."""

    # No bugs case
    if bug_data is None:
        allure.dynamic.title("✅ No Bugs Detected")
        allure.dynamic.severity(allure.severity_level.NORMAL)
        allure.dynamic.description("The AI agent found no bugs during this run.")
        return  # PASS — no bugs is good

    run_id = bug_data.get("run_id", _get_run_id() or "unknown")
    title  = bug_data.get("title", "Unnamed Bug")
    sev    = bug_data.get("severity", "Medium")
    desc   = bug_data.get("description", "")
    ts     = bug_data.get("timestamp", "")
    ss     = bug_data.get("screenshot", None)
    info   = bug_data.get("additional_info", {})
    src    = info.get("detection_source", bug_data.get("source", "text"))
    burl   = info.get("url", "")
    agent  = bug_data.get("agent_id", info.get("agent_id", ""))
    cat    = info.get("category", "")
    cerrs  = info.get("console_errors", [])
    freqs  = info.get("failed_requests", [])

    sev_icon = _SEV_ICON.get(sev.lower(), "⚪")

    # ── Dashboard title — readable without clicking ───────────────────────────
    allure.dynamic.title(f"{sev_icon} [{sev.upper()}] {title}")
    allure.dynamic.story(f"Run {run_id}")
    allure.dynamic.severity(_SEVERITY_MAP.get(sev.lower(), allure.severity_level.NORMAL))
    allure.dynamic.tag(f"severity:{sev.lower()}")
    if cat:
        allure.dynamic.tag(f"category:{cat}")
    if agent:
        allure.dynamic.tag(f"agent:{agent}")
    allure.dynamic.description(
        f"**Severity:** {sev}  \n"
        f"**Detected by:** {src}  \n"
        f"**URL:** {burl}  \n"
        f"**Agent:** {agent}  \n"
        f"**Time:** {ts}  \n\n"
        f"**Description:**  \n{desc}"
    )

    # ── STEP 1: Bug Details ───────────────────────────────────────────────────
    with allure.step(f"{sev_icon} Bug Details — {title}"):
        allure.attach(
            f"Title      : {title}\n"
            f"Severity   : {sev}\n"
            f"Category   : {cat}\n"
            f"Detected by: {src}\n"
            f"Agent      : {agent}\n"
            f"URL        : {burl}\n"
            f"Time       : {ts}\n\n"
            f"Description:\n{desc}",
            name="Bug Details",
            attachment_type=allure.attachment_type.TEXT,
        )

    # ── STEP 2: Screenshot (most useful — shown prominently) ─────────────────
    with allure.step("📸 Screenshot at time of detection"):
        if ss:
            abs_ss = os.path.abspath(ss)
            if os.path.exists(abs_ss):
                with open(abs_ss, "rb") as f:
                    allure.attach(
                        f.read(),
                        name="Bug Screenshot",
                        attachment_type=allure.attachment_type.PNG,
                    )
            else:
                allure.attach(
                    f"Screenshot not found: {abs_ss}",
                    name="Screenshot Missing",
                    attachment_type=allure.attachment_type.TEXT,
                )
        else:
            allure.attach(
                "No screenshot captured for this bug.",
                name="No Screenshot",
                attachment_type=allure.attachment_type.TEXT,
            )

    # ── STEP 3: Error Signals (only if present) ───────────────────────────────
    if cerrs or freqs:
        with allure.step("📡 Error Signals That Triggered Detection"):
            if cerrs:
                allure.attach(
                    "\n".join(cerrs),
                    name="Console Errors",
                    attachment_type=allure.attachment_type.TEXT,
                )
            if freqs:
                allure.attach(
                    "\n".join(freqs),
                    name="Failed Network Requests",
                    attachment_type=allure.attachment_type.TEXT,
                )

    # ── Fail so this shows RED in Allure (bugs should be RED) ────────────────
    pytest.fail(f"[{sev.upper()}] {title}\n{desc[:200]}")
