# agents/ai_agent_worker.py
#
# IMPROVEMENTS:
#   1. TC generation moved to ONCE PER PAGE (not once per step)
#      Before: 5 steps × 1 TC call = 5 LLM calls/page
#      After:  1 TC call/page regardless of step count
#   2. Bug detection is now SIGNAL-GATED
#      Before: always calls LLM even on clean pages
#      After:  only calls LLM if console_errors, failed_requests, or js_errors exist
#   3. Autonomy-aware: respects AUTONOMY_LEVEL flag
#      Level 1 → no AI calls (signal detection only)
#      Level 2 → AI nav + TC + signal-gated bug detection
#      Level 3 → everything
#   4. Inlined StateMemory and ExplorationTracker (they were 3-line wrappers)
#   5. Cleaner Allure attachment strategy (only attach what matters)

import allure
import os
from playwright.sync_api import Page
from config import CFG

from ai.bug_detector import detect_bug, collect_page_signals
from ai.test_generator import generate_test_cases
from browser.dom_extractor import extract_page_info
from browser.screenshot import capture_bug_screenshot, capture_step_screenshot
from reporting.bug_reporter import save_bug_report, generate_bug_report
from reporting.test_reporter import log_test
from brain.decision_engine import decide_next_action
from brain.action_executor import execute_action

# Load autonomy config once (at module level)
try:
    from core.autonomy import AUTONOMY
    _has_autonomy = True
except ImportError:
    _has_autonomy = False

    class _FallbackAutonomy:
        ai_navigation       = True
        ai_tc_generation    = True
        ai_bug_detection    = True
        visual_bug_detection = False
    AUTONOMY = _FallbackAutonomy()


def _safe_attach_screenshot(ss_path, name):
    if ss_path and isinstance(ss_path, str) and os.path.exists(ss_path):
        try:
            with open(ss_path, "rb") as f:
                allure.attach(f.read(), name=name,
                              attachment_type=allure.attachment_type.PNG)
        except Exception:
            pass


def _has_signals(console_errors, failed_requests, js_errors) -> bool:
    """Return True if any real error signals are present."""
    return bool(console_errors or failed_requests or js_errors)


def run_agent_on_page(page: Page, url: str, agent_id: str,
                      console_errors=None, failed_requests=None,
                      max_steps=None) -> tuple:
    """
    Run the AI agent loop on a single page.
    Returns (bugs_found, tcs_generated).
    """
    console_errors  = console_errors  or []
    failed_requests = failed_requests or []
    max_steps       = max_steps       or CFG.max_steps

    # Strip page suffix: "Agent-1-p2" → "Agent-1"
    base_agent_id = agent_id.split("-p")[0] if "-p" in agent_id else agent_id

    # Inlined StateMemory + ExplorationTracker (no need for separate modules)
    action_history    = []   # replaces StateMemory
    exploration_steps = []   # replaces ExplorationTracker

    bugs_found    = 0
    tcs_generated = 0

    # ── STEP 0: Extract DOM and Screenshot (once, before the step loop) ──────
    current_url = page.url
    page_title  = ""
    try:
        page_title = page.title()
    except Exception:
        pass

    page_text, buttons, links, inputs = _safe_extract(page)

    ss_path = capture_step_screenshot(page, f"page_start")
    _safe_attach_screenshot(ss_path, f"Page Screenshot: {page_title[:30]}")

    # ── STEP 1: TC Generation — ONCE PER PAGE ─────────────────────────────────
    if AUTONOMY.ai_tc_generation:
        with allure.step("Generate test cases (once per page)"):
            try:
                # generate_test_cases() returns raw AI string
                # save_test_cases() (called inside) returns the saved rows list
                # We call save_test_cases directly to get the count reliably
                from ai.ollama_client import generate, OllamaUnavailableError
                from reporting.testcase_writer import save_test_cases
                from ai.test_generator import _guess_page_type, _fallback_tcs

                # Build prompt elements
                elements_summary = []
                if inputs:
                    elements_summary.append(f"Input fields: {inputs[:10]}")
                if buttons:
                    elements_summary.append(
                        f"Buttons: {[b for b in buttons[:10] if b.strip()]}")
                if links:
                    elements_summary.append(
                        f"Links: {[l for l in links[:8] if l.strip()]}")

                page_type = _guess_page_type(current_url, page_text,
                                              buttons, inputs)
                prompt = (
                    f"You are a senior QA engineer writing test cases for a {page_type}.\n"
                    f"URL: {current_url}\nPage title: {page_title or 'unknown'}\n\n"
                    f"ACTUAL PAGE ELEMENTS:\n"
                    f"{chr(10).join(elements_summary) if elements_summary else 'No elements detected'}\n\n"
                    f"PAGE CONTENT SAMPLE:\n{page_text[:1500]}\n\n"
                    f"Write exactly 5 test cases specific to THIS page.\n"
                    f"Return ONLY lines: Title | Steps | Expected Result"
                )

                try:
                    ai_output = generate(prompt)
                    if not ai_output:
                        raise ValueError("Empty response")
                except (OllamaUnavailableError, ValueError) as e:
                    print(f"[WARN] TC generation fallback ({e})")
                    ai_output = _fallback_tcs(current_url, page_type,
                                               inputs, buttons)

                saved_rows = save_test_cases(ai_output, current_url)
                tcs_generated += len(saved_rows)
                print(f"[TC] {len(saved_rows)} TCs generated for {page_type}")

            except Exception as e:
                print(f"[WARN] TC generation failed: {e}")
    else:
        print(f"[AUTONOMY L{AUTONOMY.level if _has_autonomy else '?'}] TC generation disabled")

    # ── STEP 2: Initial Bug Detection — SIGNAL-GATED ──────────────────────────
    with allure.step("Bug detection (signal-gated)"):
        try:
            page_signals = collect_page_signals(page)
            page_signals["console_errors"]  = list(console_errors)
            page_signals["failed_requests"] = list(failed_requests)
            js_errors = page_signals.get("js_errors", [])

            signals_present = _has_signals(
                console_errors, failed_requests, js_errors)

            if not signals_present:
                print(f"[BUG] No signals — skipping LLM bug detection for {current_url[:50]}")
                bug = {"found": False}
            elif AUTONOMY.ai_bug_detection:
                bug = detect_bug(
                    page_text, page_signals=page_signals,
                    screenshot_path=ss_path)
            else:
                # Level 1: signal-only detection without LLM
                bug = _signal_only_bug(console_errors, failed_requests, js_errors)

        except Exception as e:
            print(f"[WARN] Bug detection error: {e}")
            bug = {"found": False}

        if bug.get("found"):
            bugs_found += 1
            _handle_bug_found(page, bug, agent_id=base_agent_id,
                               step_num=0, url=current_url,
                               page_title=page_title,
                               console_errors=console_errors,
                               failed_requests=failed_requests)

    console_errors.clear()
    failed_requests.clear()

    # ── STEP LOOP ─────────────────────────────────────────────────────────────
    for step_num in range(1, max_steps + 1):
        with allure.step(f"Step {step_num}/{max_steps}"):

            current_url = page.url
            try:
                page_title = page.title()
            except Exception:
                pass

            # Re-extract DOM (page may have changed)
            page_text, buttons, links, inputs = _safe_extract(page)

            # Screenshot only in DEBUG or if needed for bug
            ss_path = capture_step_screenshot(page, f"step_{step_num}")

            # ── AI Decision ──────────────────────────────────────────────────
            with allure.step("AI decision"):
                if AUTONOMY.ai_navigation:
                    try:
                        decision = decide_next_action(
                            page_text, buttons, links, inputs,
                            action_history[-5:],
                            page_title=page_title,
                            current_url=current_url,
                        )
                    except Exception as e:
                        print(f"[WARN] AI decision failed: {e}")
                        decision = "stop"
                else:
                    decision = "stop"  # Level 1: no AI nav

                allure.attach(decision, name="AI Decision",
                              attachment_type=allure.attachment_type.TEXT)

            # ── Execute Action ────────────────────────────────────────────────
            with allure.step(f"Execute: {decision}"):
                if CFG.stealth_mode:
                    try:
                        from browser.stealth import pre_interaction_pause
                        pre_interaction_pause()
                    except ImportError:
                        pass

                try:
                    action_result = execute_action(page, decision)
                except Exception as e:
                    print(f"[WARN] Action failed: {e}")
                    action_result = f"error: {e}"

                action_history.append(f"Step {step_num}: {action_result}")
                exploration_steps.append(f"{step_num}. {action_result} → {page.url}")

                allure.attach(action_result, name="Action Result",
                              attachment_type=allure.attachment_type.TEXT)

            # ── Post-action Bug Check (signal-gated) ─────────────────────────
            if console_errors or failed_requests:
                with allure.step("Post-action bug check"):
                    try:
                        page_signals = collect_page_signals(page)
                        page_signals["console_errors"]  = list(console_errors)
                        page_signals["failed_requests"] = list(failed_requests)
                        js_errors = page_signals.get("js_errors", [])

                        if AUTONOMY.ai_bug_detection:
                            bug = detect_bug(page_text, page_signals=page_signals,
                                             screenshot_path=ss_path)
                        else:
                            bug = _signal_only_bug(
                                console_errors, failed_requests, js_errors)

                        if bug.get("found"):
                            bugs_found += 1
                            _handle_bug_found(
                                page, bug, agent_id=base_agent_id,
                                step_num=step_num, url=current_url,
                                page_title=page_title,
                                console_errors=console_errors,
                                failed_requests=failed_requests)
                    except Exception as e:
                        print(f"[WARN] Post-action bug check failed: {e}")

            console_errors.clear()
            failed_requests.clear()

            if "stop" in action_result.lower() or decision == "stop":
                break

    # Attach exploration timeline
    if exploration_steps:
        allure.attach(
            "\n".join(exploration_steps),
            name="AI Exploration Timeline",
            attachment_type=allure.attachment_type.TEXT,
        )

    return bugs_found, tcs_generated


def _safe_extract(page):
    """Extract DOM info with safe fallback."""
    try:
        return extract_page_info(page)
    except Exception as e:
        print(f"[WARN] DOM extraction failed: {e}")
        return "", [], [], []


def _signal_only_bug(console_errors, failed_requests, js_errors) -> dict:
    """Signal-based bug detection without LLM (Level 1 fallback)."""
    if console_errors:
        return {
            "found": True, "severity": "High",
            "category": "console_error",
            "title": "Console errors detected",
            "description": f"Console errors: {console_errors[:3]}",
            "source": "signals",
        }
    if failed_requests:
        return {
            "found": True, "severity": "High",
            "category": "navigation_error",
            "title": "Network requests failed",
            "description": f"Failed requests: {failed_requests[:3]}",
            "source": "signals",
        }
    if js_errors:
        return {
            "found": True, "severity": "Medium",
            "category": "console_error",
            "title": "Visible error messages",
            "description": f"Error elements: {js_errors[:3]}",
            "source": "signals",
        }
    return {"found": False}


def _handle_bug_found(page, bug, agent_id, step_num, url, page_title,
                      console_errors, failed_requests):
    """Unified bug reporting — attach to Allure and save to disk."""
    source = bug.get("source", "text")
    with allure.step(f"Bug [{bug['severity']}] ({source}): {bug['title']}"):
        bug_ss  = capture_bug_screenshot(page, label=f"bug_step{step_num}")
        bug_data = {
            "title":       bug["title"],
            "description": bug["description"],
            "severity":    bug["severity"],
            "steps":       [],
            "screenshot":  bug_ss,
            "source":      source,
            "additional_info": {
                "category":         bug.get("category"),
                "detection_source": source,
                "url":              url,
                "page_title":       page_title,
                "console_errors":   console_errors[:5],
                "failed_requests":  failed_requests[:5],
                "agent_id":         agent_id,
            }
        }
        bug_report = generate_bug_report(
            bug_data, allure_attach=True, agent_id=agent_id)
        save_bug_report(bug_report)
        _safe_attach_screenshot(bug_ss, f"Bug Screenshot - Step {step_num}")
