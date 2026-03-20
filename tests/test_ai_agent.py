# tests/test_ai_agent.py
#
# PHASE 2A: Better Allure Reports
# ────────────────────────────────
# Added: smart login, safe navigation, richer step annotations

import allure
import pytest
import os
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from ai.ai_client import ask_ai
from ai.parser import parse_ai_action
from browser.dom_extractor import extract_page_info
from browser.validator import validate_target
from browser.screenshot import capture_step_screenshot
from browser.login_handler import login_if_needed
from config import CFG


def _safe_goto(page, url):
    for wait_until, timeout in [
        ("domcontentloaded", CFG.page_timeout),
        ("commit",           CFG.page_timeout),
    ]:
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            continue
        except Exception:
            break
    return False


def _safe_attach_screenshot(ss_path, name):
    if ss_path and os.path.exists(ss_path):
        try:
            with open(ss_path, "rb") as f:
                allure.attach(f.read(), name=name,
                              attachment_type=allure.attachment_type.PNG)
        except Exception:
            pass


@allure.feature("AI Agent")
@allure.story("Basic page exploration")
@allure.severity(allure.severity_level.NORMAL)
@allure.title("AI Agent — autonomous page exploration")
def test_ai_agent(page):
    """AI agent explores the target URL for up to 5 steps."""

    with allure.step("Navigate to target URL"):
        loaded = _safe_goto(page, CFG.target_urls[0])
        allure.attach(
            f"URL: {CFG.target_urls[0]}\nLoaded: {loaded}\nCurrent: {page.url}",
            name="Navigation",
            attachment_type=allure.attachment_type.TEXT,
        )

    with allure.step("Smart Login Check"):
        login_result = login_if_needed(page)
        if login_result.get("attempted"):
            status = "SUCCESS" if login_result["success"] else "FAILED"
            ss = capture_step_screenshot(page, "agent_after_login")
            _safe_attach_screenshot(ss, f"After Login ({status})")

    history = []

    for step in range(5):
        with allure.step(f"Exploration step {step + 1}"):
            page_text, buttons, links, inputs = extract_page_info(page)

            allure.attach(
                f"URL: {page.url}\n"
                f"Buttons: {buttons[:5]}\n"
                f"Links: {links[:5]}\n"
                f"Inputs: {inputs[:5]}",
                name=f"Step {step+1} — Page State",
                attachment_type=allure.attachment_type.TEXT,
            )

            with allure.step("Ask AI for next action"):
                ai_output = ask_ai(page_text, buttons, links, inputs, history)
                allure.attach(ai_output, name="AI Decision",
                              attachment_type=allure.attachment_type.TEXT)

            action, target = parse_ai_action(ai_output)
            history.append(f"{action} -> {target}")

            if action == "click" and target:
                with allure.step(f"Click: {target}"):
                    if validate_target(page, target):
                        page.click(f"text={target}")
                    else:
                        allure.attach(f"Target '{target}' not found, skipping.",
                                      name="Skip Reason",
                                      attachment_type=allure.attachment_type.TEXT)
            elif action == "type":
                with allure.step("Type into input"):
                    page.fill("input:visible", "testdata")
            elif action == "stop" or action is None:
                with allure.step("Agent chose to stop"):
                    break

    assert page.title() is not None, "Page became unresponsive"
