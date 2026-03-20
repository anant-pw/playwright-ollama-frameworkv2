# reporting/bug_reporter.py
#
# FIX: Bug reports now save agent_id AND url at save time
# This allows per-agent filtering in test_agent_results.py

import json
import os
import datetime
import threading
import allure
from run_context import RUN_ID, BUG_RUN_DIR

_bug_counter = 0
_counter_lock = threading.Lock()


def save_bug_report(bug_data: dict, filename: str = None) -> str:
    global _bug_counter
    with _counter_lock:
        _bug_counter += 1
        count = _bug_counter

    if not filename:
        filename = f"bug_{count:03d}.json"

    path = os.path.join(BUG_RUN_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bug_data, f, indent=4)

    print(f"[BUG] Saved: {path}")
    return path


def generate_bug_report(bug_input, page_text: str = "",
                        allure_attach: bool = True,
                        agent_id: str = "") -> dict:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(bug_input, str):
        bug_data = {
            "title":       "AI-Detected Bug",
            "description": bug_input,
            "steps":       [],
            "severity":    "Medium",
            "screenshot":  None,
            "additional_info": {
                "page_text_snippet": page_text[:500],
                "agent_id":          agent_id,
            },
        }
    else:
        bug_data = dict(bug_input)
        # Ensure additional_info exists and has agent_id
        if "additional_info" not in bug_data:
            bug_data["additional_info"] = {}
        if agent_id:
            bug_data["additional_info"]["agent_id"] = agent_id

    report = {
        "run_id":             RUN_ID,
        "agent_id":           bug_data.get("additional_info", {}).get(
                                  "agent_id", agent_id or ""),
        "timestamp":          ts,
        "title":              bug_data.get("title",       "Unnamed Bug"),
        "description":        bug_data.get("description", ""),
        "steps_to_reproduce": bug_data.get("steps",       []),
        "severity":           bug_data.get("severity",    "Medium"),
        "screenshot":         bug_data.get("screenshot",  None),
        "source":             bug_data.get("source",      ""),
        "additional_info":    bug_data.get("additional_info", {}),
    }

    if allure_attach:
        try:
            allure.attach(
                json.dumps(report, indent=4),
                name=f"Bug Report — {report['title']}",
                attachment_type=allure.attachment_type.JSON,
            )
            ss = report.get("screenshot")
            if ss:
                abs_ss = os.path.abspath(ss)
                if os.path.exists(abs_ss):
                    with open(abs_ss, "rb") as f:
                        allure.attach(f.read(), name="Bug Screenshot",
                                      attachment_type=allure.attachment_type.PNG)
        except Exception as e:
            print(f"[WARN] Allure attach failed: {e}")

    return report
