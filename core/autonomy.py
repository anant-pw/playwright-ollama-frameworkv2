# core/autonomy.py
#
# Autonomy Level Controller
# ──────────────────────────
# Controls which AI features are active based on AUTONOMY_LEVEL flag.
#
# Level 1 — Manual (safe, deterministic)
#   - Runs pre-written stories from stories/ directory only
#   - No AI calls during execution
#   - Signal-based bug detection only (no LLM)
#   - Use when: validating known regression, CI/CD pipeline, Ollama down
#
# Level 2 — Semi-Auto (balanced, recommended for pilot)
#   - Crawls pages and generates TCs via AI
#   - Bug detection: AI fires only when signals are present
#   - AI decisions for navigation
#   - Use when: exploring new features, daily smoke testing
#
# Level 3 — Full Auto (most powerful, highest resource usage)
#   - Everything in Level 2
#   - Visual bug detection via llava (if available)
#   - Auto story generation from TCs
#   - AI URL ranking (in addition to score-based)
#   - Use when: initial site exploration, full regression runs

import os
from dataclasses import dataclass


@dataclass
class AutonomyConfig:
    level: int = 2

    # Level 1+ features (always available)
    run_manual_stories: bool = True
    signal_bug_detection: bool = True

    # Level 2+ features (semi-auto)
    ai_navigation: bool = True
    ai_tc_generation: bool = True
    ai_bug_detection: bool = True   # fires only when signals present
    smart_crawl: bool = True

    # Level 3+ features (full auto)
    visual_bug_detection: bool = False
    auto_story_generation: bool = False
    ai_url_ranking: bool = False    # ai_rank_pages(); off by default


def load_autonomy() -> AutonomyConfig:
    """Load autonomy level from environment and return configured AutonomyConfig."""
    level = int(os.environ.get("AUTONOMY_LEVEL", "2"))
    level = max(1, min(3, level))  # clamp to 1-3

    cfg = AutonomyConfig(level=level)

    if level == 1:
        cfg.ai_navigation       = False
        cfg.ai_tc_generation    = False
        cfg.ai_bug_detection    = False
        cfg.visual_bug_detection = False
        cfg.auto_story_generation = False
        cfg.ai_url_ranking      = False

    elif level == 2:
        cfg.ai_navigation       = True
        cfg.ai_tc_generation    = True
        cfg.ai_bug_detection    = True
        cfg.visual_bug_detection = False
        cfg.auto_story_generation = False
        cfg.ai_url_ranking      = False

    elif level == 3:
        cfg.ai_navigation        = True
        cfg.ai_tc_generation     = True
        cfg.ai_bug_detection     = True
        cfg.visual_bug_detection = True
        cfg.auto_story_generation = os.environ.get(
            "STORY_ENABLED", "false").lower() in ("1", "true", "yes")
        cfg.ai_url_ranking       = True

    return cfg


# Global singleton — loaded once at import time
AUTONOMY = load_autonomy()


def print_autonomy_plan():
    """Print a clear description of what will run at the current level."""
    cfg = AUTONOMY
    mode_names = {1: "MANUAL (Level 1)", 2: "SEMI-AUTO (Level 2)", 3: "FULL AUTO (Level 3)"}
    mode = mode_names.get(cfg.level, f"Level {cfg.level}")

    lines = [
        "=" * 55,
        f"  AUTONOMY MODE: {mode}",
        "=" * 55,
        f"  Manual stories:        {'ON' if cfg.run_manual_stories else 'OFF'}",
        f"  Signal bug detection:  ON (always)",
        f"  AI navigation:         {'ON' if cfg.ai_navigation else 'OFF'}",
        f"  AI TC generation:      {'ON' if cfg.ai_tc_generation else 'OFF'}",
        f"  AI bug detection:      {'ON (signal-gated)' if cfg.ai_bug_detection else 'OFF'}",
        f"  Visual detection:      {'ON (llava)' if cfg.visual_bug_detection else 'OFF'}",
        f"  Auto story generation: {'ON' if cfg.auto_story_generation else 'OFF'}",
        f"  AI URL ranking:        {'ON' if cfg.ai_url_ranking else 'OFF'}",
        "=" * 55,
    ]
    print("\n".join(lines))
