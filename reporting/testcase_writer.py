# reporting/testcase_writer.py
#
# IMPROVED: Added phi3/mistral output format support
# ────────────────────────────────────────────────────
# phi3 tends to return TCs in these formats that the old parser missed:
#
# Format A — Numbered list with bold titles (phi3 default):
#   1. **Verify login with valid credentials**
#      Steps: Navigate to login, enter valid email/password, click Sign In
#      Expected: User redirected to dashboard
#
# Format B — Markdown headers:
#   ### TC1: Login with valid credentials
#   **Steps:** Enter valid credentials
#   **Expected:** Redirected to dashboard
#
# Format C — Colon-separated (no pipes):
#   1. Login with valid credentials
#      Steps: Enter credentials and click Sign In
#      Expected Result: Dashboard is shown
#
# These are now all handled before falling through to pipe-based parsing.

import pandas as pd
import os
import re
import json
import allure
import base64
from datetime import datetime
from run_context import RUN_ID, TC_RUN_FILE, TC_RUN_DIR


def _parse_tc_lines(ai_output: str, url: str) -> list:
    rows    = []
    base_ts = int(datetime.now().timestamp())

    # ── 1. JSON format ────────────────────────────────────────────────────────
    try:
        clean = ai_output.strip()
        if clean.startswith("[") or '"title"' in clean.lower():
            if "```" in clean:
                clean = clean.split("```")[1].lstrip("json").strip()
            data = json.loads(clean)
            if isinstance(data, list):
                for i, item in enumerate(data):
                    if isinstance(item, dict):
                        title    = item.get("title", item.get("Title", "")).strip()
                        steps    = item.get("steps", item.get("Steps", "")).strip()
                        expected = item.get("expected", item.get("ExpectedResult",
                                   item.get("expected_result", ""))).strip()
                        if title and steps:
                            rows.append(_make_row(base_ts, i, title,
                                                  steps, expected, url))
                if rows:
                    return rows
    except Exception:
        pass

    lines = ai_output.strip().split("\n")

    # ── 1b. phi3 Format A — Numbered bold title + Steps/Expected lines ────────
    # Pattern:
    #   1. **Title here**
    #      Steps: ...
    #      Expected: ...
    phi3_rows = []
    current_phi = {}
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # New TC: starts with number + bold or plain title
        num_match = re.match(
            r"^\d+[\.\)]\s*\*{0,2}(.+?)\*{0,2}\s*$", s)
        if num_match and not any(
                kw in s.lower() for kw in ["steps:", "expected:", "result:"]):
            if current_phi.get("title") and current_phi.get("steps"):
                phi3_rows.append(_make_row(
                    base_ts, len(phi3_rows),
                    current_phi["title"], current_phi["steps"],
                    current_phi.get("expected", ""), url))
            current_phi = {"title": num_match.group(1).strip(),
                           "steps": "", "expected": ""}
            continue
        # Steps line
        sm = re.match(r"^\*{0,2}steps?[:\-]\*{0,2}\s*(.+)", s, re.IGNORECASE)
        if sm and current_phi.get("title"):
            current_phi["steps"] = sm.group(1).strip()
            continue
        # Expected line
        em = re.match(
            r"^\*{0,2}(?:expected|expected result|result)[:\-]\*{0,2}\s*(.+)",
            s, re.IGNORECASE)
        if em and current_phi.get("title"):
            current_phi["expected"] = em.group(1).strip()
            continue

    if current_phi.get("title") and current_phi.get("steps"):
        phi3_rows.append(_make_row(
            base_ts, len(phi3_rows),
            current_phi["title"], current_phi["steps"],
            current_phi.get("expected", ""), url))

    if phi3_rows:
        return phi3_rows

    # ── 1c. phi3 Format B — Markdown headers (### TC1: Title) ─────────────────
    md_rows = []
    current_md = {}
    for line in lines:
        s = line.strip()
        if not s:
            continue
        hdr = re.match(r"^#{1,4}\s*(?:TC\d+[:\-]?\s*)?(.+)$", s, re.IGNORECASE)
        if hdr and not any(
                kw in s.lower() for kw in ["steps", "expected", "test case"]):
            if current_md.get("title") and current_md.get("steps"):
                md_rows.append(_make_row(
                    base_ts, len(md_rows),
                    current_md["title"], current_md["steps"],
                    current_md.get("expected", ""), url))
            current_md = {"title": hdr.group(1).strip(),
                          "steps": "", "expected": ""}
            continue
        sm = re.match(r"^\*{0,2}steps?[:\-]\*{0,2}\s*(.+)", s, re.IGNORECASE)
        if sm and current_md.get("title"):
            current_md["steps"] = sm.group(1).strip()
            continue
        em = re.match(
            r"^\*{0,2}(?:expected|result)[:\-]\*{0,2}\s*(.+)",
            s, re.IGNORECASE)
        if em and current_md.get("title"):
            current_md["expected"] = em.group(1).strip()
            continue

    if current_md.get("title") and current_md.get("steps"):
        md_rows.append(_make_row(
            base_ts, len(md_rows),
            current_md["title"], current_md["steps"],
            current_md.get("expected", ""), url))

    if md_rows:
        return md_rows

    # ── 2. Numbered pipe format (most common for llama3) ─────────────────────
    numbered_pipe_rows = []
    for line in lines:
        s = line.strip()
        m = re.match(r"^\d+[\.\)]\s*\|\s*(.+)", s)
        if not m:
            continue
        parts = [p.strip() for p in m.group(1).split("|") if p.strip()]
        if len(parts) >= 2:
            title    = parts[0]
            steps    = parts[1] if len(parts) > 1 else ""
            expected = parts[2] if len(parts) > 2 else ""
            if title and steps:
                numbered_pipe_rows.append(
                    _make_row(base_ts, len(numbered_pipe_rows),
                              title, steps, expected, url))
    if numbered_pipe_rows:
        return numbered_pipe_rows

    # ── 3. Vertical table ─────────────────────────────────────────────────────
    vert_rows = []
    current   = {}
    tc_index  = 0

    for line in lines:
        s = line.strip()
        if not s:
            continue
        plain = re.match(r"^(?:Test Case\s*\d+[:\-]\s*)(.+)$", s, re.IGNORECASE)
        bold  = re.match(r"^\*{1,2}(?:Test Case\s*\d+[:\-]?\s*)?(.+?)\*{1,2}$",
                         s, re.IGNORECASE)
        if plain or bold:
            if current.get("title") and current.get("steps"):
                vert_rows.append(_make_row(base_ts, tc_index,
                    current["title"], current["steps"],
                    current.get("expected", ""), url))
                tc_index += 1
            current = {"title": (plain or bold).group(1).strip(),
                       "steps": "", "expected": ""}
            continue
        if s.startswith("|") and s.endswith("|") and current is not None:
            parts = [p.strip() for p in s.split("|") if p.strip()]
            if len(parts) >= 2:
                key = parts[0].lower()
                val = " ".join(parts[1:]).strip()
                if "title" in key:
                    current["title"] = val
                elif "step" in key:
                    current["steps"] = val
                elif "expected" in key or "result" in key:
                    current["expected"] = val

    if current.get("title") and current.get("steps"):
        vert_rows.append(_make_row(base_ts, tc_index,
            current["title"], current["steps"],
            current.get("expected", ""), url))

    if vert_rows:
        return vert_rows

    # ── 4. Simple pipe ────────────────────────────────────────────────────────
    pipe_rows = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith(("-", "=", "#", "*")):
            continue
        if re.match(r"(?i)title\s*\|", s):
            continue
        parts = [p.strip() for p in s.split("|")]
        if len(parts) >= 3 and len(parts[0]) >= 5:
            title    = re.sub(r"^\d+[\.\)]\s*", "", parts[0]).strip()
            steps    = parts[1].strip()
            expected = parts[2].strip()
            if title and steps and expected:
                pipe_rows.append(_make_row(base_ts, i, title,
                                           steps, expected, url))
    if pipe_rows:
        return pipe_rows

    # ── 5. Numbered structured ────────────────────────────────────────────────
    current_title = current_steps = current_expected = ""
    tc_index = 0
    for line in lines:
        s = line.strip()
        if not s:
            if current_title and current_steps:
                rows.append(_make_row(base_ts, tc_index,
                    current_title, current_steps, current_expected, url))
                tc_index += 1
                current_title = current_steps = current_expected = ""
            continue
        num = re.match(r"^(?:\d+[\.\):]|TC\d+:?)\s*(.+)", s, re.IGNORECASE)
        if num:
            if current_title and current_steps:
                rows.append(_make_row(base_ts, tc_index,
                    current_title, current_steps, current_expected, url))
                tc_index += 1
            current_title    = num.group(1).strip()
            current_steps    = ""
            current_expected = ""
            continue
        sm = re.match(r"^(?:steps?|action|how)[:\-]\s*(.+)", s, re.IGNORECASE)
        if sm:
            current_steps = sm.group(1).strip()
            continue
        em = re.match(r"^(?:expected|result|outcome)[:\-]\s*(.+)", s, re.IGNORECASE)
        if em:
            current_expected = em.group(1).strip()
            continue
        if current_title and not current_steps and len(s) > 10:
            current_steps = s
        elif current_title and current_steps and not current_expected and len(s) > 5:
            current_expected = s

    if current_title and current_steps:
        rows.append(_make_row(base_ts, tc_index,
            current_title, current_steps, current_expected, url))

    return rows


def _make_row(base_ts, index, title, steps, expected, url):
    return {
        "RunID":          RUN_ID,
        "TestID":         f"TC_{base_ts}_{index:03d}",
        "Title":          title,
        "Steps":          steps,
        "ExpectedResult": expected or "Test completes without errors",
        "URL":            url,
        "CreatedBy":      "AI-Agent",
        "CreatedAt":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Status":         "Generated",
    }


def save_test_cases(ai_output: str, url: str) -> list:
    rows = _parse_tc_lines(ai_output, url)

    if not rows:
        try:
            allure.attach(
                f"Raw AI output (could not parse TCs):\n\n{ai_output}",
                name="TC Parse Failed - Raw Output",
                attachment_type=allure.attachment_type.TEXT,
            )
        except Exception:
            pass
        print(f"[TC] 0 test case(s) generated for web page")
        return []

    tc_file = TC_RUN_FILE
    df_new  = pd.DataFrame(rows)

    if os.path.exists(tc_file):
        df_existing = pd.read_excel(tc_file)
        df_all      = pd.concat([df_existing, df_new], ignore_index=True)
        # FIX: Deduplicate by Title+URL (not TestID) to keep TCs from different pages
        df_all = df_all.drop_duplicates(subset=["Title", "URL"], keep="last")
    else:
        df_all = df_new

    df_all.to_excel(tc_file, index=False)
    print(f"[TC] {len(rows)} TC(s) saved -> {tc_file}  (run {RUN_ID})")

    try:
        csv_lines = ["TestID,Title,Steps,ExpectedResult,URL"]
        for tc in rows:
            def esc(v): return f'"{v}"' if "," in str(v) else str(v)
            csv_lines.append(
                f"{esc(tc['TestID'])},{esc(tc['Title'])},{esc(tc['Steps'])},"
                f"{esc(tc['ExpectedResult'])},{esc(tc['URL'])}"
            )
        allure.attach(
            "\n".join(csv_lines),
            name=f"Test Cases - {len(rows)} TCs (run {RUN_ID})",
            attachment_type=allure.attachment_type.CSV,
        )

        if os.path.exists(tc_file):
            with open(tc_file, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            allure.attach(
                f"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:20px">
<h3>Run: {RUN_ID}</h3>
<p style="color:#555">{len(df_all)} total test case(s) across all pages</p>
<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}"
   download="test_cases_{RUN_ID}.xlsx"
   style="display:inline-block;padding:10px 20px;background:#0052cc;color:white;
          border-radius:6px;text-decoration:none;font-weight:600">
  ⬇ Download test_cases_{RUN_ID}.xlsx
</a></body></html>""",
                name=f"test_cases_{RUN_ID}.xlsx (download)",
                attachment_type=allure.attachment_type.HTML,
            )
    except Exception as e:
        print(f"[WARN] Allure TC attach failed: {e}")

    return rows
