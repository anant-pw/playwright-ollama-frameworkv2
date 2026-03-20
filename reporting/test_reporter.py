# reporting/test_reporter.py
#
# PHASE 2A: Richer test reporting with timing and agent summary

import allure
import datetime
import json
import time

_session_start = None
_test_log = []


def init_report():
    global _session_start, _test_log
    _session_start = time.time()
    _test_log = []
    allure.attach(
        f"Suite started at {datetime.datetime.now().isoformat()}",
        name="Suite Start Time",
        attachment_type=allure.attachment_type.TEXT,
    )
    print("[REPORT] Report initialized")


def close_report():
    elapsed = round(time.time() - _session_start, 1) if _session_start else 0
    allure.attach(
        f"Suite finished at {datetime.datetime.now().isoformat()}\n"
        f"Total duration: {elapsed}s",
        name="Suite End Time",
        attachment_type=allure.attachment_type.TEXT,
    )
    print("[REPORT] Report closed")


def log_test(agent_id: str, url: str, test_type: str, status: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "agent":     agent_id,
        "url":       url,
        "type":      test_type,
        "status":    status,
        "timestamp": timestamp,
    }
    _test_log.append(entry)

    icon = "✅" if status == "PASS" else "❌"
    allure.attach(
        json.dumps(entry, indent=2),
        name=f"Test Result — {agent_id} {icon} [{status}]",
        attachment_type=allure.attachment_type.JSON,
    )

    # Attach a readable summary table
    allure.attach(
        f"Agent:     {agent_id}\n"
        f"URL:       {url}\n"
        f"Type:      {test_type}\n"
        f"Status:    {icon} {status}\n"
        f"Timestamp: {timestamp}",
        name=f"Agent Result: {icon} {status}",
        attachment_type=allure.attachment_type.TEXT,
    )
    print(f"[REPORT] {timestamp} | Agent {agent_id} | {url} | {test_type} | {status}")
