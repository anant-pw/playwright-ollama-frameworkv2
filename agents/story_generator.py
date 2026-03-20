# agents/story_generator.py
#
# PHASE 4: Auto-generate regression stories from TCs found by the agent.
# Ollama reads the TCs it generated and writes a YAML story file.
# Next run executes those stories as regression tests — fully autonomous.

import os
import re
import yaml
import allure
from datetime import datetime
from ai.ollama_client import generate, OllamaUnavailableError
from run_context import RUN_ID


def generate_stories_from_tcs(run_id: str, url: str,
                               agent_id: str = "") -> str | None:
    """
    Read TCs generated for this URL and ask Ollama to write
    executable story steps from them.
    Returns path to saved YAML file, or None if nothing generated.
    """
    # Load TCs for this URL
    tc_file = os.path.join("generated_test_cases", run_id, "test_cases.xlsx")
    if not os.path.exists(tc_file):
        print(f"[STORY-GEN] No TC file found for run {run_id}")
        return None

    try:
        import pandas as pd
        df      = pd.read_excel(tc_file)
        domain  = url.replace("https://","").replace("http://","").split("/")[0]
        mask    = df["URL"].astype(str).str.contains(domain, na=False)
        tcs     = df[mask].to_dict("records")
    except Exception as e:
        print(f"[STORY-GEN] Could not load TCs: {e}")
        return None

    if not tcs:
        print(f"[STORY-GEN] No TCs found for {url}")
        return None

    # Build TC summary for Ollama
    tc_summary = "\n".join(
        f"{i+1}. Title: {tc.get('Title','')}\n"
        f"   Steps: {tc.get('Steps','')}\n"
        f"   Expected: {tc.get('ExpectedResult','')}"
        for i, tc in enumerate(tcs[:10])  # max 10 TCs
    )

    prompt = f"""You are a QA automation engineer. Convert these test cases into executable story steps.

URL: {url}
Test Cases Found:
{tc_summary}

Write 2-3 executable stories in this EXACT YAML format (no extra text):

stories:
  - name: "Story title here"
    description: "What this story tests"
    priority: high
    steps:
      - action: navigate
        url: {url}
      - action: fill
        field: username
        value: test_user
      - action: click
        text: Login
      - action: assert_url_contains
        value: dashboard
        message: Should redirect to dashboard

Available actions ONLY: navigate, fill, click, assert_text_present, assert_url_contains, wait, screenshot, scroll

Rules:
- Use ONLY the actions listed above
- field values must match real form field names (username, password, email etc)
- click text must be exact button/link text visible on page
- Keep stories short (3-6 steps each)
- Focus on the most important user flows from the test cases

Respond with ONLY valid YAML, no explanation, no markdown code blocks.
"""

    print(f"[STORY-GEN] Asking Ollama to generate stories for {url}...")
    try:
        response = generate(prompt)
        if not response or len(response.strip()) < 50:
            print(f"[STORY-GEN] Empty response from Ollama")
            return None
    except OllamaUnavailableError as e:
        print(f"[STORY-GEN] Ollama unavailable: {e}")
        return None

    # Clean response — remove markdown if present
    clean = response.strip()
    if "```" in clean:
        clean = re.sub(r"```[a-z]*\n?", "", clean).strip()

    # Parse and validate YAML
    try:
        data = yaml.safe_load(clean)
        if not isinstance(data, dict) or "stories" not in data:
            print(f"[STORY-GEN] Invalid YAML structure from Ollama")
            return None
        stories = data.get("stories", [])
        if not stories:
            print(f"[STORY-GEN] No stories in Ollama response")
            return None
    except yaml.YAMLError as e:
        print(f"[STORY-GEN] YAML parse error: {e}")
        # Try to salvage partial content
        return None

    # Add metadata
    output = {
        "site":      url,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id":    run_id,
        "agent_id":  agent_id,
        "auto":      True,
        "stories":   stories,
    }

    # Save to stories/auto/ directory
    os.makedirs("stories/auto", exist_ok=True)
    domain_safe = re.sub(r"[^\w]", "_", domain)
    fname       = f"auto_{domain_safe}_{run_id}.yaml"
    fpath       = os.path.join("stories", "auto", fname)

    with open(fpath, "w", encoding="utf-8") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True)

    print(f"[STORY-GEN] Saved {len(stories)} stories → {fpath}")

    # Attach to Allure
    try:
        allure.attach(
            yaml.dump(output, default_flow_style=False),
            name=f"Auto-Generated Stories: {domain}",
            attachment_type=allure.attachment_type.TEXT,
        )
    except Exception:
        pass

    return fpath
