# run_context.py
#
# Single source of truth for the current run's timestamp and paths.
# Imported by testcase_writer, bug_reporter, and screenshot — so every
# artifact from one run lands in the same timestamped location.
#
# RUN_ID is set ONCE when this module is first imported (at session start).
# All subsequent imports get the same value — no drift between files.

import os
import datetime
from config import CFG
import logging
import sys

# e.g. "20260316_171950"
RUN_ID = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# ── Per-run directories ───────────────────────────────────────────────────────
# bug_reports/20260316_171950/
BUG_RUN_DIR = os.path.join(CFG.bug_reports_dir, RUN_ID)

# screenshots/20260316_171950/
SCREENSHOT_RUN_DIR = os.path.join(CFG.screenshots_dir, RUN_ID)

# generated_test_cases/20260316_171950/test_cases.xlsx
TC_RUN_DIR  = os.path.join("generated_test_cases", RUN_ID)
TC_RUN_FILE = os.path.join(TC_RUN_DIR, "test_cases.xlsx")

# Create directories immediately
os.makedirs(BUG_RUN_DIR,       exist_ok=True)
os.makedirs(SCREENSHOT_RUN_DIR, exist_ok=True)
os.makedirs(TC_RUN_DIR,        exist_ok=True)

print(f"[RUN] ID: {RUN_ID}")
print(f"[RUN] TCs       → {TC_RUN_FILE}")
print(f"[RUN] Bugs      → {BUG_RUN_DIR}/")
print(f"[RUN] Screenshots → {SCREENSHOT_RUN_DIR}/")

# Per-run log file — captures all print() output
LOG_RUN_FILE = os.path.join(BUG_RUN_DIR, f"run_{RUN_ID}.log")

class _Tee:
    """Writes to both console and log file simultaneously."""
    def __init__(self, *targets):
        self.targets = targets
    def write(self, msg):
        for t in self.targets:
            try:
                t.write(msg)
                t.flush()
            except Exception:
                pass
    def flush(self):
        for t in self.targets:
            try: t.flush()
            except Exception: pass
    def isatty(self):
        return False

_log_file_handle = open(LOG_RUN_FILE, "w", encoding="utf-8", buffering=1)
sys.stdout = _Tee(sys.__stdout__, _log_file_handle)
sys.stderr = _Tee(sys.__stderr__, _log_file_handle)

print(f"[RUN] Log      → {LOG_RUN_FILE}")