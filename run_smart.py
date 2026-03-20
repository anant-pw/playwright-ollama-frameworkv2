#!/usr/bin/env python3
# run_smart.py
#
# Clean single entry point for the AI QA Framework.
# Replaces the need to remember pytest flags.
#
# Usage:
#   python run_smart.py                        # Run with settings from config.env
#   python run_smart.py --level 1              # Manual mode (stories only)
#   python run_smart.py --level 2              # Semi-auto (default)
#   python run_smart.py --level 3              # Full auto
#   python run_smart.py --urls https://site.com
#   python run_smart.py --check                # Pre-flight only (no tests)
#   python run_smart.py --clear-cache          # Clear LLM cache then run

import argparse
import os
import subprocess
import sys
import time
import platform
import shutil
import requests

# ── Force project root on path so 'config' is always importable ──────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _parse_args():
    p = argparse.ArgumentParser(
        description="AI QA Framework — Smart Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Autonomy Levels:
  1  Manual    — runs pre-written stories only, no AI calls
  2  Semi-Auto — AI navigation + TC gen + signal-gated bug detection (DEFAULT)
  3  Full Auto — everything including visual detection + story generation
        """
    )
    p.add_argument("--level",       type=int, choices=[1, 2, 3],
                   help="Autonomy level (overrides config.env AUTONOMY_LEVEL)")
    p.add_argument("--urls",        type=str,
                   help="Comma-separated target URLs (overrides config.env TARGET_URLS)")
    p.add_argument("--agents",      type=int,
                   help="Number of parallel agents (overrides PARALLEL_AGENTS)")
    p.add_argument("--pages",       type=int,
                   help="Max pages per URL (overrides MAX_CRAWL_PAGES)")
    p.add_argument("--steps",       type=int,
                   help="Max steps per page (overrides MAX_STEPS)")
    p.add_argument("--model",       type=str,
                   help="Ollama model name (overrides OLLAMA_MODEL)")
    p.add_argument("--check",       action="store_true",
                   help="Pre-flight check only — don't run tests")
    p.add_argument("--clear-cache", action="store_true",
                   help="Clear LLM response cache before running")
    p.add_argument("--no-report",   action="store_true",
                   help="Skip auto-opening Allure report after run")
    return p.parse_args()


def _set_env(key: str, value):
    """Override an env variable (affects config.py which reads os.environ)."""
    if value is not None:
        os.environ[key] = str(value)
        print(f"[CONFIG] {key}={value} (override)")


def preflight_check() -> list:
    """
    Check that all required services and configs are ready.
    Returns list of warning strings (empty = all good).
    """
    from config import CFG

    warnings = []
    print("\n[PREFLIGHT] Running pre-flight checks...")

    # ── 1. Ollama health ──────────────────────────────────────────────────────
    try:
        r = requests.get(f"{CFG.ollama_host}/api/tags", timeout=5)
        models = [m.get("name", "") for m in r.json().get("models", [])]
        if models:
            print(f"[PREFLIGHT] ✅ Ollama OK — models: {models}")

            # FIX: match model with or without :latest/:tag suffix
            # e.g. config says 'llama3.2' but ollama list shows 'llama3.2:latest'
            model_name = CFG.ollama_model
            model_base = model_name.split(":")[0]
            model_found = any(
                m == model_name or m.startswith(f"{model_base}:")
                for m in models
            )
            if not model_found:
                warnings.append(
                    f"⚠️  Model '{model_name}' not found. "
                    f"Available: {models[:3]}. "
                    f"Run: ollama pull {model_name}"
                )
            else:
                print(f"[PREFLIGHT] ✅ Model ready: {model_name}")
        else:
            warnings.append(
                f"⚠️  Ollama running but no models loaded. "
                f"Run: ollama pull {CFG.ollama_model}"
            )
    except Exception as e:
        warnings.append(
            f"⚠️  Ollama unreachable at {CFG.ollama_host}: {e}\n"
            f"   AI features will be disabled."
        )
        os.environ.setdefault("AUTONOMY_LEVEL", "1")

    # ── 2. URL reachability — WARN ONLY, NEVER abort ──────────────────────────
    # Raw HTTP checks WILL fail for Cloudflare / SSL / bot-protected sites.
    # This is completely normal. Playwright uses a full stealth browser and
    # bypasses these protections. We print info only — never block the run.
    for url in CFG.target_urls:
        reachable = False
        for method, kwargs in [
            ("HEAD", {"timeout": 8,  "allow_redirects": True}),
            ("GET",  {"timeout": 12, "allow_redirects": True, "stream": True}),
        ]:
            try:
                resp = requests.request(
                    method, url,
                    headers={
                        "User-Agent": CFG.user_agent,
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                    **kwargs
                )
                if resp.status_code < 500:
                    print(f"[PREFLIGHT] ✅ URL reachable: {url} ({resp.status_code})")
                    reachable = True
                    break
            except Exception:
                continue

        if not reachable:
            # Info only — Playwright stealth will handle Cloudflare/SSL sites
            print(f"[PREFLIGHT] ℹ️  Raw HTTP check could not reach: {url}")
            print(f"[PREFLIGHT]    This is normal for Cloudflare / SSL-protected sites.")
            print(f"[PREFLIGHT]    Playwright browser with stealth will handle it fine.")

    # ── 3. Allure CLI installed ───────────────────────────────────────────────
    if not shutil.which("allure"):
        warnings.append(
            "⚠️  'allure' CLI not found. Report will not auto-open.\n"
            "   Install: scoop install allure  "
            "OR  https://allurereport.org/docs/install/"
        )

    # ── 4. Login credentials check ────────────────────────────────────────────
    if CFG.login_email and not CFG.login_password:
        warnings.append("⚠️  LOGIN_EMAIL set but LOGIN_PASSWORD missing")

    # ── 5. Cache stats ────────────────────────────────────────────────────────
    try:
        from core.cache import LLMCache
        stats = LLMCache().stats()
        if stats["valid"] > 0:
            print(f"[PREFLIGHT] 📦 Cache: {stats['valid']} valid entries "
                  f"({stats['ttl_hours']}h TTL)")
    except ImportError:
        pass

    if warnings:
        print("\n[PREFLIGHT] Warnings:")
        for w in warnings:
            print(f"  {w}")
        print()
    else:
        print("[PREFLIGHT] ✅ All checks passed\n")

    return warnings


def run_tests(no_report: bool = False) -> int:
    """Run the test suite and return exit code."""
    from config import CFG

    results_dir = CFG.allure_results_dir

    # Clean old results before new run
    if os.path.exists(results_dir):
        shutil.rmtree(results_dir)
    os.makedirs(results_dir, exist_ok=True)

    cmd = [
        "pytest",
        "--alluredir", results_dir,
        "--clean-alluredir",
        "-v", "-s",
        "-W", "ignore::urllib3.exceptions.InsecureRequestWarning",
        "run_agents.py",
        "tests/test_agent_results.py",
        "tests/test_api_results.py",
        "tests/test_bugs.py",
        "tests/test_generated_tcs.py",
        "tests/test_user_stories.py",
    ]

    print(f"\n[RUN] {' '.join(cmd)}\n")
    return subprocess.run(cmd).returncode


def open_report(results_dir: str, report_dir: str):
    """Generate and open Allure report."""
    if not shutil.which("allure"):
        print(f"\n[REPORT] allure CLI not installed.")
        print(f"[REPORT] Install: scoop install allure")
        print(f"[REPORT] Or serve manually: allure serve {results_dir}")

        # Open the HTML viewers that don't need Allure CLI
        import glob
        bug_htmls = glob.glob(
            os.path.join("bug_reports", "**", "*.html"), recursive=True)
        tc_htmls  = glob.glob(
            os.path.join("generated_test_cases", "**", "*.html"), recursive=True)
        for path in sorted(bug_htmls)[-1:] + sorted(tc_htmls)[-1:]:
            abs_path = os.path.abspath(path)
            print(f"[REPORT] Opening: {abs_path}")
            try:
                s = platform.system()
                if s == "Windows":    os.startfile(abs_path)
                elif s == "Darwin":   subprocess.Popen(["open", abs_path])
                else:                 subprocess.Popen(["xdg-open", abs_path])
            except Exception:
                pass
        return

    try:
        gen = subprocess.run(
            ["allure", "generate", results_dir, "--clean", "-o", report_dir],
            capture_output=True, text=True,
        )
        if gen.returncode == 0:
            index = os.path.abspath(os.path.join(report_dir, "index.html"))
            print(f"\n[REPORT] → {index}")
            s = platform.system()
            if s == "Windows":    os.startfile(index)
            elif s == "Darwin":   subprocess.Popen(["open", index])
            else:                 subprocess.Popen(["xdg-open", index])
        else:
            print(f"[REPORT] Generate failed: {gen.stderr.strip()}")
            subprocess.Popen(["allure", "serve", results_dir])
    except Exception as e:
        print(f"[REPORT] Error: {e}")
        print(f"[REPORT] Run manually: allure serve {results_dir}")


def main():
    args = _parse_args()

    # Apply CLI overrides to environment BEFORE config.py is imported
    _set_env("AUTONOMY_LEVEL",  args.level)
    _set_env("TARGET_URLS",     args.urls)
    _set_env("PARALLEL_AGENTS", args.agents)
    _set_env("MAX_CRAWL_PAGES", args.pages)
    _set_env("MAX_STEPS",       args.steps)
    _set_env("OLLAMA_MODEL",    args.model)

    # Now safe to import config (reads os.environ)
    from config import CFG
    from core.autonomy import AUTONOMY, print_autonomy_plan

    # Print ONCE here — config.py module-level print has been removed
    print("\n" + CFG.summary() + "\n")
    print_autonomy_plan()

    # Clear LLM cache if requested
    if args.clear_cache:
        try:
            from core.cache import LLMCache
            n = LLMCache().invalidate()
            print(f"[CACHE] Cleared {n} cached entries")
        except ImportError:
            pass

    # Pre-flight checks
    warnings = preflight_check()

    if args.check:
        print("\n[CHECK] Pre-flight complete. Remove --check flag to run tests.")
        return 0

    # ── Abort logic ───────────────────────────────────────────────────────────
    # URL failures are NEVER fatal — Playwright handles Cloudflare/SSL sites.
    # Only degrade if Ollama is completely unreachable AND we need it.
    ollama_down = any(
        "Ollama unreachable" in w or "Ollama running but no models" in w
        for w in warnings
    )
    if ollama_down and AUTONOMY.level >= 2:
        print("\n[WARN] Ollama unavailable — downgrading to AUTONOMY_LEVEL=1.")
        print("[WARN] Signal-based detection only. No AI calls will be made.")
        os.environ["AUTONOMY_LEVEL"] = "1"
        from core.autonomy import load_autonomy
        import core.autonomy as _aut
        _aut.AUTONOMY = load_autonomy()
        print_autonomy_plan()

    # Run tests
    start   = time.time()
    code    = run_tests(no_report=args.no_report)
    elapsed = time.time() - start

    print(f"\n[DONE] Run completed in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"[DONE] Exit code: {code} ({'PASS' if code == 0 else 'FAIL'})")

    if not args.no_report:
        open_report(CFG.allure_results_dir, CFG.allure_report_dir)

    return code


if __name__ == "__main__":
    sys.exit(main())
