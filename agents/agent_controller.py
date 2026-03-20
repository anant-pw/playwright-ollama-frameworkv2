# agents/agent_controller.py
#
# FIXED:
#   - Removed self-import bug (was calling `from agents.agent_controller import ...`
#     INSIDE this file — run_agent_with_crawling is defined here, not imported)
#   - Removed dead `start_agents()` function (never called by pytest)
#   - Removed duplicate _run_parallel/_run_sequential (these live in run_agents.py)
#   - Kept: run_agent_with_crawling() — the core single-agent crawl loop
#   - Added: autonomy-aware crawl (respects AUTONOMY_LEVEL)

import allure
import os
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from config import CFG
from reporting.test_reporter import log_test


def run_agent_with_crawling(playwright_or_pw, entry_url: str,
                             agent_id: str) -> tuple:
    """
    Runs a single agent with smart multi-page crawling.
    Works both with pytest's playwright fixture AND with sync_playwright().
    Returns (total_bugs, total_tcs).
    """
    from browser.stealth import apply_stealth, post_navigation_pause, \
        pre_interaction_pause
    from browser.login_handler import login_if_needed
    from browser.screenshot import capture_step_screenshot
    from brain.smart_crawler import SmartCrawler
    from agents.ai_agent_worker import run_agent_on_page

    # Load autonomy (lightweight import)
    try:
        from core.autonomy import AUTONOMY
        smart_crawl = AUTONOMY.smart_crawl
    except ImportError:
        smart_crawl = True

    max_pages = int(os.environ.get("MAX_CRAWL_PAGES", "5"))
    max_depth = int(os.environ.get("MAX_CRAWL_DEPTH", "3"))

    total_bugs = 0
    total_tcs  = 0
    page_num   = 0

    launcher = getattr(playwright_or_pw, CFG.browser)
    browser  = launcher.launch(**CFG.browser_launch_kwargs())
    context  = browser.new_context(**CFG.browser_context_kwargs())

    if CFG.stealth_mode:
        apply_stealth(context)
        print(f"[STEALTH] {agent_id}: patches injected")

    console_errors  = []
    failed_requests = []
    context.on("console",  lambda msg: console_errors.append(msg.text)
               if msg.type == "error" else None)
    context.on("requestfailed", lambda req: failed_requests.append(
               f"{req.method} {req.url} - {req.failure}"))

    # API capture — hooks into context to record all XHR/fetch calls
    api_capture = None
    api_enabled = os.environ.get("API_TESTING", "true").lower() in ("1","true","yes")
    if api_enabled:
        try:
            from api.api_tester import APICapture
            api_capture = APICapture()
            api_capture.attach(context)
            print(f"[API] Network capture active for {agent_id}")
        except ImportError:
            print(f"[API] api_tester not found — skipping API tests")

    page = context.new_page()

    try:
        print(f"\n[{agent_id}] Starting: {entry_url}")
        loaded = _safe_goto(page, entry_url, CFG.page_timeout)
        if not loaded:
            return 0, 0

        if CFG.stealth_mode:
            post_navigation_pause()

        actual_entry = entry_url
        if CFG.stealth_mode:
            pre_interaction_pause()

        login_result = login_if_needed(page)
        if login_result.get("success"):
            actual_entry = page.url
            print(f"[{agent_id}] Logged in → {actual_entry}")
            console_errors.clear()
            failed_requests.clear()
            ss = capture_step_screenshot(page, f"{agent_id}_after_login")
            if ss and os.path.exists(ss):
                with open(ss, "rb") as f:
                    allure.attach(f.read(), name=f"{agent_id}: After Login",
                                  attachment_type=allure.attachment_type.PNG)
        elif login_result.get("skipped"):
            actual_entry = page.url
            print(f"[{agent_id}] Login skipped: {login_result.get('skip_reason')}")

        # Init crawler
        crawler = SmartCrawler(
            entry_url      = actual_entry,
            original_entry = entry_url,
            max_pages      = max_pages,
            max_depth      = max_depth,
        ) if smart_crawl else None

        pages_to_process = [(actual_entry, 0, True)]

        while pages_to_process:
            next_url, depth, already_loaded = pages_to_process.pop(0)
            page_num += 1
            print(f"[{agent_id}] Page {page_num}/{max_pages}: {next_url[:50]}")

            with allure.step(f"[{agent_id}] Page {page_num}: {next_url[:50]}"):
                if not already_loaded:
                    loaded = _safe_goto(page, next_url, CFG.page_timeout)
                    if not loaded:
                        if crawler:
                            crawler.visited.add(next_url)
                        continue
                    if CFG.stealth_mode:
                        post_navigation_pause()

                page_title = ""
                try:
                    page_title = page.title()
                except Exception:
                    pass
                actual_url = page.url

                allure.attach(
                    f"Agent: {agent_id}\nURL: {actual_url}\n"
                    f"Title: {page_title}\nPage: {page_num}/{max_pages}",
                    name=f"{agent_id}: Page {page_num} Info",
                    attachment_type=allure.attachment_type.TEXT,
                )

                page_bugs, page_tcs = run_agent_on_page(
                    page=page, url=actual_url,
                    agent_id=f"{agent_id}-p{page_num}",
                    console_errors=console_errors,
                    failed_requests=failed_requests,
                    max_steps=CFG.max_steps,
                )

                total_bugs += page_bugs
                total_tcs  += page_tcs
                print(f"[{agent_id}] Page {page_num}: "
                      f"{page_bugs} bugs, {page_tcs} TCs")

                if crawler:
                    with allure.step("Discover links"):
                        added = crawler.add_links(page, actual_url, depth)
                        if added:
                            allure.attach(
                                f"New pages queued: {added}\n"
                                f"Queue remaining:  {len(crawler.queue)}",
                                name="Crawl Progress",
                                attachment_type=allure.attachment_type.TEXT,
                            )

                    crawler.mark_visited(next_url, depth,
                                         title=page_title,
                                         bugs_found=page_bugs,
                                         tcs_generated=page_tcs)
                    console_errors.clear()
                    failed_requests.clear()

                    if page_num >= max_pages:
                        break

                    # Queue next page from crawler
                    result = crawler.next_url()
                    if result[0] is not None:
                        pages_to_process.append((result[0], result[1], False))
                else:
                    break  # No crawler → only process entry page

        if crawler:
            crawler.attach_crawl_map()

        # ── API Testing — runs after crawl, uses captured endpoints ──────
        if api_capture:
            try:
                from api.api_tester import run_api_tests
                base_domain = urlparse(entry_url).netloc
                endpoints   = api_capture.get_endpoints(base_domain=base_domain)
                if endpoints:
                    api_bugs, _ = run_api_tests(
                        endpoints  = endpoints,
                        agent_id   = agent_id,
                        base_url   = entry_url,
                    )
                    total_bugs += api_bugs
                else:
                    print(f"[API] No same-domain API endpoints captured for {agent_id}")
            except Exception as e:
                print(f"[API] API testing failed: {e}")

        log_test(agent_id, entry_url, "Exploratory Testing", "PASS")

    except Exception as e:
        print(f"[{agent_id}] Error: {e}")
        import traceback
        traceback.print_exc()
        log_test(agent_id, entry_url, "Exploratory Testing", "FAIL")
        raise
    finally:
        try:
            page.close()
            context.close()
            browser.close()
        except Exception:
            pass

    print(f"[{agent_id}] Complete: {page_num} pages, "
          f"{total_bugs} bugs, {total_tcs} TCs")
    return total_bugs, total_tcs


def _safe_goto(page, url: str, timeout: int) -> bool:
    """Navigate to URL with graceful retry fallback."""
    from playwright.sync_api import TimeoutError as PWTimeout
    for wait_until, t in [
        ("domcontentloaded", timeout),
        ("commit",           timeout),
        ("domcontentloaded", timeout * 2),
    ]:
        try:
            page.goto(url, wait_until=wait_until, timeout=t)
            print(f"[NAV] Loaded {url} (wait={wait_until})")
            return True
        except PWTimeout:
            print(f"[WARN] Timeout with wait={wait_until}, retrying...")
        except Exception as e:
            print(f"[WARN] Navigation error: {e}")
            break
    return False
