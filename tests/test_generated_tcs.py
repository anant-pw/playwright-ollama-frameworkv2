# tests/test_generated_tcs.py
#
# REDESIGNED: Clean, readable TC report — grouped by page, flat steps
# ─────────────────────────────────────────────────────────────────────
# OLD: Every TC nested 3 levels deep — had to expand URL → page → TC → details
# NEW: One test = all TCs. Flat steps per page. One attachment per page = readable.
#      PASS when TCs exist. Excel download always visible at the top.

import pytest
import allure
import os
import base64
from collections import defaultdict


def _get_run_id() -> str:
    try:
        from run_context import RUN_ID
        return RUN_ID
    except Exception:
        return None


def _load_tcs(run_id: str) -> list:
    tc_file = os.path.join("generated_test_cases", run_id, "test_cases.xlsx")
    if not os.path.exists(tc_file):
        return []
    try:
        import pandas as pd
        df = pd.read_excel(tc_file).drop_duplicates(subset="TestID", keep="last")
        tcs = df.to_dict("records")
        print(f"[TC] Loaded {len(tcs)} TCs from run {run_id}")
        return tcs
    except Exception as e:
        print(f"[TC] Load error: {e}")
        return []


def _load_most_recent_tcs():
    base = "generated_test_cases"
    if not os.path.isdir(base):
        return None, []
    for folder in sorted(os.listdir(base), reverse=True):
        if os.path.isdir(os.path.join(base, folder)):
            tcs = _load_tcs(folder)
            if tcs:
                return folder, tcs
    return None, []


def pytest_generate_tests(metafunc):
    if "tc_row" in metafunc.fixturenames:
        metafunc.parametrize("tc_row", ["__runtime__"], ids=["test-cases"])


@allure.feature("🧪 AI Generated Test Cases")
def test_generated_tc(tc_row):
    """All generated TCs for this run — grouped by page, flat and readable."""

    run_id = _get_run_id()
    tcs    = _load_tcs(run_id) if run_id else []

    if not tcs:
        run_id, tcs = _load_most_recent_tcs()

    if not tcs:
        pytest.skip("No TCs generated yet.")

    # Group by page URL
    by_page = defaultdict(list)
    for tc in tcs:
        by_page[str(tc.get("URL", "unknown"))].append(tc)

    # ── Dashboard title ───────────────────────────────────────────────────────
    allure.dynamic.title(
        f"🧪 {len(tcs)} Test Cases Generated across {len(by_page)} page(s)"
    )
    allure.dynamic.story(f"Run {run_id}")
    allure.dynamic.severity(allure.severity_level.NORMAL)
    allure.dynamic.description(
        f"**Run ID:** {run_id}  \n"
        f"**Total TCs:** {len(tcs)}  \n"
        f"**Pages covered:** {len(by_page)}  \n\n" +
        "\n".join(
            f"- {url.replace('https://','').replace('http://','')}: "
            f"**{len(ptcs)} TCs**"
            for url, ptcs in by_page.items()
        )
    )
    allure.dynamic.tag(f"tcs:{len(tcs)}")
    allure.dynamic.tag(f"pages:{len(by_page)}")

    # ── Excel download — at the top so it's always easy to find ──────────────
    with allure.step(f"⬇ Download All {len(tcs)} TCs as Excel"):
        try:
            tc_file = os.path.join("generated_test_cases", run_id, "test_cases.xlsx")
            if os.path.exists(tc_file):
                with open(tc_file, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                allure.attach(
                    f'<!DOCTYPE html><html><body style="font-family:sans-serif;padding:20px">'
                    f'<h3>Run {run_id} — {len(tcs)} AI-Generated Test Cases</h3>'
                    f'<p style="color:#555">Generated across {len(by_page)} page(s)</p>'
                    f'<a href="data:application/vnd.openxmlformats-officedocument'
                    f'.spreadsheetml.sheet;base64,{b64}" '
                    f'download="test_cases_{run_id}.xlsx" '
                    f'style="display:inline-block;padding:12px 24px;background:#0052cc;'
                    f'color:white;border-radius:6px;text-decoration:none;font-weight:600;'
                    f'font-size:16px">'
                    f'⬇ Download test_cases_{run_id}.xlsx</a>'
                    f'</body></html>',
                    name="⬇ Download Excel",
                    attachment_type=allure.attachment_type.HTML,
                )
        except Exception:
            pass

    # ── One step per page — flat, readable ───────────────────────────────────
    for page_url, page_tcs in by_page.items():
        page_label = (page_url.replace("https://", "").replace("http://", "")
                               .rstrip("/"))
        with allure.step(f"📄 {page_label} — {len(page_tcs)} TCs"):
            # All TCs for this page in one clean text block
            lines = []
            for i, tc in enumerate(page_tcs, 1):
                lines += [
                    f"{'─' * 55}",
                    f"TC {i:02d}  {tc.get('TestID', '')}",
                    f"Title    : {tc.get('Title', '')}",
                    f"Steps    : {tc.get('Steps', '')}",
                    f"Expected : {tc.get('ExpectedResult', '')}",
                    "",
                ]
            allure.attach(
                "\n".join(lines),
                name=f"TCs — {page_label}",
                attachment_type=allure.attachment_type.TEXT,
            )

    assert len(tcs) > 0, "No TCs were generated"
