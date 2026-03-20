# conftest.py
#
# REDESIGNED: Cleaner Allure categories + environment panel
# ─────────────────────────────────────────────────────────
# Categories renamed to match what QA engineers actually look for
# Environment panel simplified — no duplicate keys

import pytest
import allure
import subprocess
import os
import platform
import json
from config import CFG


@pytest.fixture(scope="session")
def browser_type_launch_args():
    return CFG.browser_launch_kwargs()


@pytest.fixture(scope="session")
def browser_context_args():
    return CFG.browser_context_kwargs()


@pytest.fixture
def page(browser):
    context = browser.new_context(**CFG.browser_context_kwargs())
    pg      = context.new_page()
    yield pg
    try:
        allure.attach(pg.url, name="Final URL",
                      attachment_type=allure.attachment_type.TEXT)
    except Exception:
        pass
    context.close()


def pytest_sessionstart(session):
    from run_context import RUN_ID, BUG_RUN_DIR, TC_RUN_FILE, SCREENSHOT_RUN_DIR
    results_dir = _ensure_results_dir()
    _write_environment(results_dir, RUN_ID)
    _write_executor(results_dir)
    _write_categories(results_dir)


def _ensure_results_dir():
    d = CFG.allure_results_dir
    if not os.path.isabs(d):
        d = os.path.join(os.getcwd(), d)
    os.makedirs(d, exist_ok=True)
    return d


def _write_environment(results_dir, run_id):
    """Write clean, non-duplicated environment properties for Allure dashboard."""
    try:
        import platform as _p

        # Get autonomy level label
        level = os.environ.get("AUTONOMY_LEVEL", "2")
        level_labels = {"1": "Manual", "2": "Semi-Auto", "3": "Full Auto"}
        level_label  = level_labels.get(level, f"Level {level}")

        lines = [
            f"Run.ID={run_id}",
            f"Target.URL(s)={', '.join(CFG.target_urls)}",
            f"Autonomy.Level={level} ({level_label})",
            f"Parallel.Agents={os.environ.get('PARALLEL_AGENTS', '1')}",
            f"Max.Pages.Per.URL={os.environ.get('MAX_CRAWL_PAGES', '3')}",
            f"Max.Steps.Per.Page={CFG.max_steps}",
            f"Browser={CFG.browser} (headless={CFG.headless})",
            f"Stealth.Mode={'ON' if getattr(CFG,'stealth_mode',False) else 'OFF'}",
            f"Ollama.Model={CFG.ollama_model}",
            f"Login.Configured={'Yes' if CFG.login_email else 'No'}",
            f"Story.Generation={'ON' if os.environ.get('STORY_ENABLED','false').lower() in ('1','true','yes') else 'OFF'}",
            f"Python={_p.python_version()}",
            f"OS={_p.system()} {_p.release()}",
        ]
        path = os.path.join(results_dir, "environment.properties")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[ALLURE] environment.properties written")
    except Exception as e:
        print(f"[ALLURE] environment.properties error: {e}")


def _write_executor(results_dir):
    try:
        build_url    = os.environ.get("BUILD_URL", "")
        build_number = os.environ.get("BUILD_NUMBER", "local")
        job_name     = os.environ.get("JOB_NAME", "AI-QA-Framework")
        jenkins_url  = os.environ.get("JENKINS_URL", "")
        executor = {
            "name":       job_name,
            "type":       "jenkins" if jenkins_url else "local",
            "url":        jenkins_url or "http://localhost",
            "buildOrder": int(build_number) if build_number.isdigit() else 1,
            "buildName":  f"#{build_number}",
            "buildUrl":   build_url or "",
            "reportUrl":  f"{build_url}allure" if build_url else "",
            "reportName": "AI QA Report",
        }
        with open(os.path.join(results_dir, "executor.json"), "w") as f:
            json.dump(executor, f, indent=2)
    except Exception as e:
        print(f"[ALLURE] executor.json error: {e}")


def _write_categories(results_dir):
    """
    Clean category definitions — maps to what QA engineers care about.
    Categories appear in Allure's 'Categories' tab for quick filtering.
    """
    categories = [
        # Bug severity categories — for filtering by impact
        {
            "name": "🔴 Critical Bugs",
            "messageRegex": ".*\\[CRITICAL\\].*",
            "matchedStatuses": ["failed"],
        },
        {
            "name": "🟠 High Severity Bugs",
            "messageRegex": ".*\\[HIGH\\].*",
            "matchedStatuses": ["failed"],
        },
        {
            "name": "🟡 Medium Severity Bugs",
            "messageRegex": ".*\\[MEDIUM\\].*",
            "matchedStatuses": ["failed"],
        },
        {
            "name": "🟢 Low Severity Bugs",
            "messageRegex": ".*\\[LOW\\].*",
            "matchedStatuses": ["failed"],
        },
        # Infrastructure issues — not real bugs, need fixing
        {
            "name": "⚙️ Framework / Infrastructure Issues",
            "matchedStatuses": ["broken"],
        },
        # Skipped — nothing ran
        {
            "name": "⏭ Skipped (No Data)",
            "matchedStatuses": ["skipped"],
        },
    ]
    try:
        with open(os.path.join(results_dir, "categories.json"), "w") as f:
            json.dump(categories, f, indent=2)
        print(f"[ALLURE] categories.json written ({len(categories)} categories)")
    except Exception as e:
        print(f"[ALLURE] categories.json error: {e}")


def pytest_sessionfinish(session, exitstatus):
    from run_context import RUN_ID
    print(f"\n{'─' * 60}")
    print(f"[RUN] Completed: {RUN_ID}")
    _generate_allure_report()
    _generate_bug_report(RUN_ID)
    _generate_tc_viewer(RUN_ID)
    print("─" * 60)


def _generate_allure_report():
    results_dir = os.path.abspath(CFG.allure_results_dir)
    report_dir  = os.path.abspath(CFG.allure_report_dir)
    if not os.path.exists(results_dir):
        return
    result_files = [f for f in os.listdir(results_dir) if f.endswith(".json")]
    if not result_files:
        print("[ALLURE] No results — skipping.")
        return
    print(f"[ALLURE] {len(result_files)} result(s). Generating report...")
    try:
        gen = subprocess.run(
            ["allure", "generate", results_dir, "--clean", "-o", report_dir],
            capture_output=True, text=True, timeout=60,
        )
        if gen.returncode == 0:
            index = os.path.join(report_dir, "index.html")
            print(f"[ALLURE] Report → {index}")
            _open(index)
            return
        print(f"[ALLURE] generate failed: {gen.stderr.strip()}")
    except FileNotFoundError:
        print("[ALLURE] allure CLI not found.")
        print("[ALLURE] Install: scoop install allure  OR  https://allurereport.org/docs/install/")
    except subprocess.TimeoutExpired:
        print("[ALLURE] generate timed out.")
    # Fallback to serve
    try:
        subprocess.Popen(["allure", "serve", results_dir])
    except FileNotFoundError:
        print(f"[ALLURE] Run manually: allure serve {results_dir}")


def _generate_bug_report(run_id):
    try:
        import glob
        bug_dir = os.path.join(CFG.bug_reports_dir, run_id)
        if not os.path.isdir(bug_dir) or \
           not glob.glob(os.path.join(bug_dir, "bug_*.json")):
            print(f"[BUG REPORT] No bugs in run {run_id}.")
            return
        from reporting.bug_report_viewer import generate_html_report, open_report
        path = generate_html_report(run_id)
        if path:
            open_report(path)
    except Exception as e:
        print(f"[BUG REPORT] Error: {e}")


def _generate_tc_viewer(run_id):
    try:
        from reporting.tc_viewer import generate_html_viewer, open_viewer
        path = generate_html_viewer(run_id)
        if path:
            open_viewer(path)
    except Exception as e:
        print(f"[TC VIEWER] Error: {e}")


def _open(path):
    try:
        s = platform.system()
        if s == "Windows":    os.startfile(path)
        elif s == "Darwin":   subprocess.Popen(["open", path])
        else:                 subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
