# run_agents.py
#
# PHASE 4: Auto story generation + improved Allure agent dashboard
# ─────────────────────────────────────────────────────────────────
# NEW: After exploration, Ollama auto-generates regression stories
# NEW: Allure overview now shows correct agent count + per-agent stats

import allure
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import Playwright, sync_playwright
from reporting.test_reporter import init_report, close_report
from config import CFG


class _SharedResults:
    def __init__(self):
        self._lock    = threading.Lock()
        self._results = []

    def add(self, result: dict):
        with self._lock:
            self._results.append(result)

    def all(self) -> list:
        with self._lock:
            return list(self._results)


_shared = _SharedResults()


@allure.feature("AI Autonomous Website Testing")
@allure.story("Full agent run")
@allure.severity(allure.severity_level.CRITICAL)
def test_run_ai_agents(playwright: Playwright):
    """
    Orchestrates all parallel agents and attaches rich summary to Allure.
    Each agent gets its own Allure test via test_agent_results.py.
    """
    init_report()
    try:
        urls         = CFG.target_urls
        max_parallel = int(os.environ.get("PARALLEL_AGENTS", "1"))
        max_parallel = max(1, min(max_parallel, len(urls)))
        story_enabled  = os.environ.get("STORY_ENABLED", "false").lower() \
                       in ("1","true","yes")

        allure.dynamic.title(
            f"AI Agent Run — {len(urls)} URL(s) "
            f"({'parallel' if max_parallel > 1 else 'sequential'})"
        )

        allure.attach(
            f"URLs:            {len(urls)}\n"
            f"Mode:            {'PARALLEL' if max_parallel > 1 else 'SEQUENTIAL'}\n"
            f"Parallel agents: {max_parallel}\n"
            f"Max pages/URL:   {os.environ.get('MAX_CRAWL_PAGES','5')}\n"
            f"Max steps/page:  {CFG.max_steps}\n"
            f"Stealth:         {getattr(CFG,'stealth_mode',False)}\n"
            f"Story gen:       {'ON' if story_enabled else 'OFF'}\n"
            f"URLs:\n" + "\n".join(f"  {i+1}. {u}" for i,u in enumerate(urls)),
            name="Run Configuration",
            attachment_type=allure.attachment_type.TEXT,
        )
        allure.attach(CFG.summary(), name="Active Configuration",
                      attachment_type=allure.attachment_type.TEXT)

        run_start = time.time()

        if max_parallel == 1:
            for i, url in enumerate(urls):
                _run_agent_sequential(playwright, url, f"Agent-{i+1}")
        else:
            _run_agents_parallel(urls, max_parallel)

        total_duration = time.time() - run_start
        results        = _shared.all()

        # ── Phase 4: Auto-generate stories from TCs ───────────────────────
        if story_enabled:
            from run_context import RUN_ID
            with allure.step("🤖 Auto-generating regression stories"):
                from agents.story_generator import generate_stories_from_tcs
                story_files = []
                for r in results:
                    path = generate_stories_from_tcs(
                        RUN_ID, r["url"], r["agent_id"])
                    if path:
                        story_files.append(path)
                allure.attach(
                    f"Stories generated: {len(story_files)}\n" +
                    "\n".join(f"  → {p}" for p in story_files),
                    name="Auto-Generated Story Files",
                    attachment_type=allure.attachment_type.TEXT,
                )

        _attach_run_summary(results, total_duration, max_parallel)

    finally:
        close_report()


def _run_agent_sequential(playwright, url, agent_id):
    from agents.agent_controller import run_agent_with_crawling
    start = time.time()
    bugs, tcs, status, error = 0, 0, "PASS", None
    try:
        bugs, tcs = run_agent_with_crawling(playwright, url, agent_id)
    except Exception as e:
        status = "FAIL"
        error  = str(e)
    finally:
        _shared.add({
            "agent_id": agent_id, "url": url,
            "bugs": bugs, "tcs": tcs,
            "status": status, "duration": time.time()-start,
            "error": error,
        })


def _run_agents_parallel(urls, max_parallel):
    print(f"\n[PARALLEL] Starting {len(urls)} agents ({max_parallel} at a time)...")

    def _worker(url, agent_id):
        start = time.time()
        print(f"[PARALLEL] {agent_id} started: {url}")
        bugs, tcs, status, error = 0, 0, "PASS", None
        try:
            with sync_playwright() as pw:
                from agents.agent_controller import run_agent_with_crawling
                bugs, tcs = run_agent_with_crawling(pw, url, agent_id)
        except Exception as e:
            status = "FAIL"
            error  = str(e)
            import traceback; traceback.print_exc()
        finally:
            duration = time.time() - start
            print(f"[PARALLEL] {agent_id} done in {duration:.0f}s: "
                  f"{bugs} bugs, {tcs} TCs")
        return {"agent_id": agent_id, "url": url, "bugs": bugs,
                "tcs": tcs, "status": status,
                "duration": time.time()-start, "error": error}

    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {
            executor.submit(_worker, url, f"Agent-{i+1}"): url
            for i, url in enumerate(urls)
        }
        for future in as_completed(futures):
            _shared.add(future.result())


def _attach_run_summary(results: list, total_duration: float,
                         max_parallel: int):
    """Attach a rich agent summary table — clearly shows all agents."""
    if not results:
        return

    total_bugs = sum(r["bugs"] for r in results)
    total_tcs  = sum(r["tcs"]  for r in results)
    passed     = sum(1 for r in results if r["status"] == "PASS")
    failed     = sum(1 for r in results if r["status"] == "FAIL")

    # ── Rich summary table ────────────────────────────────────────────────────
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║                PARALLEL AGENT RUN SUMMARY                   ║",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  Agents Run     : {len(results)} ({passed} ✅ passed, {failed} ❌ failed)".ljust(63) + "║",
        f"║  Total Duration : {total_duration:.0f}s ({total_duration/60:.1f} min)".ljust(63) + "║",
        f"║  Total Bugs     : {total_bugs}".ljust(63) + "║",
        f"║  Total TCs      : {total_tcs}".ljust(63) + "║",
        f"║  Mode           : {'PARALLEL x'+str(max_parallel) if max_parallel>1 else 'SEQUENTIAL'}".ljust(63) + "║",
        "╠══════════════════════════════════════════════════════════════╣",
        "║  Agent       URL                          Bugs  TCs  Time   ║",
        "╠══════════════════════════════════════════════════════════════╣",
    ]

    for r in sorted(results, key=lambda x: x["agent_id"]):
        icon     = "✅" if r["status"] == "PASS" else "❌"
        url_short = r["url"].replace("https://","")[:35]
        mins      = f"{r['duration']/60:.1f}m"
        lines.append(
            f"║  {icon} {r['agent_id']:<10} {url_short:<35} "
            f"{r['bugs']:>4}  {r['tcs']:>3}  {mins:>5} ║"
        )

    lines += [
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  TOTAL                                        "
        f"{total_bugs:>4}  {total_tcs:>3}         ║",
        "╚══════════════════════════════════════════════════════════════╝",
    ]

    allure.attach(
        "\n".join(lines),
        name=f"Agent Summary ({len(results)} agents)",
        attachment_type=allure.attachment_type.TEXT,
    )

    # ── Per-agent step in Allure (so it appears in the steps tree) ───────────
    for r in sorted(results, key=lambda x: x["agent_id"]):
        icon = "✅" if r["status"] == "PASS" else "❌"
        with allure.step(
            f"{icon} {r['agent_id']}: {r['url'][:45]} "
            f"| {r['bugs']} bugs | {r['tcs']} TCs "
            f"| {r['duration']/60:.1f}min"
        ):
            allure.attach(
                f"Agent:    {r['agent_id']}\n"
                f"URL:      {r['url']}\n"
                f"Status:   {r['status']}\n"
                f"Duration: {r['duration']:.0f}s ({r['duration']/60:.1f} min)\n"
                f"Bugs:     {r['bugs']}\n"
                f"TCs:      {r['tcs']}"
                + (f"\nError:    {r['error']}" if r.get("error") else ""),
                name=f"{r['agent_id']} Result",
                attachment_type=allure.attachment_type.TEXT,
            )
