# api/api_tester.py
#
# API Testing Module
# ───────────────────
# Captures all XHR/fetch/API calls made during browser crawl,
# then directly tests each unique endpoint with requests.
#
# How it works:
#   1. Playwright's network listener captures every request made
#      while the browser navigates (XHR, fetch, API calls)
#   2. After crawl completes, unique API endpoints are extracted
#   3. Each endpoint is tested directly:
#      - Status code validation
#      - Response time check against budget
#      - Security headers check
#      - Auth header detection (flags missing auth on sensitive endpoints)
#   4. Findings saved as bug reports + attached to Allure
#
# Integration: called from agent_controller.py after crawl completes
# No new dependencies — uses requests (already in requirements.txt)
#
# Config (add to config.env):
#   API_TESTING=true          # enable/disable (default: true)
#   API_TIMEOUT_MS=3000       # response time budget in ms (default: 3000)
#   API_TEST_AUTH=true        # test authenticated endpoints (default: true)

import allure
import json
import os
import time
import requests
from urllib.parse import urlparse
from datetime import datetime


# ── Endpoint capture ──────────────────────────────────────────────────────────

class APICapture:
    """
    Attaches to a Playwright context and records all API/XHR requests.
    Call attach(context) right after context creation.
    Call get_endpoints() after crawl to get unique API endpoints.
    """

    def __init__(self):
        self._requests  = []
        self._responses = {}   # url → {status, headers, time_ms}

    def attach(self, context, page=None):
        """Hook into Playwright context to capture all network traffic."""
        context.on("request",  self._on_request)
        context.on("response", self._on_response)

    def _on_request(self, request):
        """Capture every outgoing request."""
        resource_type = request.resource_type
        # Only capture API/data requests — skip assets
        if resource_type in ("xhr", "fetch", "websocket", "other"):
            self._requests.append({
                "url":     request.url,
                "method":  request.method,
                "type":    resource_type,
                "headers": dict(request.headers),
            })

    def _on_response(self, response):
        """Capture response metadata."""
        try:
            self._responses[response.url] = {
                "status":  response.status,
                "headers": dict(response.headers),
            }
        except Exception:
            pass

    def get_endpoints(self, base_domain: str = None) -> list:
        """
        Return unique API endpoints discovered during crawl.
        Filters to same-domain endpoints only if base_domain given.
        Returns list of dicts: {url, method, headers, status, type}
        """
        seen     = set()
        endpoints = []

        for req in self._requests:
            url = req["url"]

            # Deduplicate by URL + method
            key = f"{req['method']}:{url}"
            if key in seen:
                continue
            seen.add(key)

            # Filter to same domain if requested
            if base_domain:
                try:
                    if base_domain not in urlparse(url).netloc:
                        continue
                except Exception:
                    continue

            # Skip non-API resources
            if _is_asset_url(url):
                continue

            endpoint = {
                "url":     url,
                "method":  req["method"],
                "type":    req["type"],
                "headers": req["headers"],
                "status":  self._responses.get(url, {}).get("status"),
                "resp_headers": self._responses.get(url, {}).get("headers", {}),
            }
            endpoints.append(endpoint)

        print(f"[API] Captured {len(endpoints)} unique API endpoints")
        return endpoints


def _is_asset_url(url: str) -> bool:
    """Return True if URL is a static asset (not an API call)."""
    asset_exts = (
        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map",
        ".webp", ".avif", ".pdf", ".zip",
    )
    asset_paths = ("/static/", "/assets/", "/images/", "/fonts/",
                   "/cdn-", "/_next/static/", "/webpack/")
    url_lower = url.lower().split("?")[0]

    if any(url_lower.endswith(ext) for ext in asset_exts):
        return True
    if any(path in url_lower for path in asset_paths):
        return True
    return False


# ── API testing ───────────────────────────────────────────────────────────────

_SECURITY_HEADERS = [
    "x-frame-options",
    "x-content-type-options",
    "content-security-policy",
    "strict-transport-security",
    "x-xss-protection",
]

_SENSITIVE_PATTERNS = [
    "user", "account", "profile", "admin", "auth", "token",
    "password", "secret", "private", "dashboard", "payment",
]


def test_endpoint(endpoint: dict, auth_headers: dict = None,
                  timeout_ms: int = 3000) -> dict:
    """
    Test a single API endpoint directly.
    Returns a result dict with findings.
    """
    url     = endpoint["url"]
    method  = endpoint["method"]
    timeout = timeout_ms / 1000  # convert to seconds

    result = {
        "url":            url,
        "method":         method,
        "status":         None,
        "time_ms":        None,
        "bugs":           [],
        "passed":         False,
        "error":          None,
        "resp_headers":   {},
    }

    # Build headers — use captured request headers + auth if available
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; QA-API-Tester/1.0)",
        "Accept":     "application/json, text/plain, */*",
    }
    if auth_headers:
        headers.update(auth_headers)
    # Forward original auth headers if present
    original_headers = endpoint.get("headers", {})
    for h in ("authorization", "cookie", "x-auth-token", "x-api-key"):
        if h in original_headers:
            headers[h] = original_headers[h]

    # Execute request
    try:
        start = time.time()
        resp  = requests.request(
            method  = method,
            url     = url,
            headers = headers,
            timeout = timeout,
            allow_redirects = True,
            verify  = False,  # match browser's ignore_https_errors
        )
        elapsed_ms = round((time.time() - start) * 1000)

        result["status"]       = resp.status_code
        result["time_ms"]      = elapsed_ms
        result["resp_headers"] = dict(resp.headers)
        result["passed"]       = True

        # ── Check 1: Status code ──────────────────────────────────────────
        if resp.status_code >= 500:
            result["bugs"].append({
                "severity": "Critical",
                "category": "api_server_error",
                "title":    f"API server error: {method} {_short_url(url)} → {resp.status_code}",
                "description": (
                    f"Endpoint returned HTTP {resp.status_code} (server error).\n"
                    f"URL: {url}\nMethod: {method}\n"
                    f"This indicates a backend failure that users may encounter."
                ),
            })
        elif resp.status_code == 401:
            result["bugs"].append({
                "severity": "High",
                "category": "auth_issue",
                "title":    f"Unauthenticated access rejected: {_short_url(url)}",
                "description": (
                    f"Endpoint returned 401 Unauthorized.\n"
                    f"URL: {url}\nThis is expected behaviour — "
                    f"confirmed authentication is required."
                ),
            })
        elif resp.status_code == 403:
            result["bugs"].append({
                "severity": "Medium",
                "category": "auth_issue",
                "title":    f"Forbidden: {method} {_short_url(url)} → 403",
                "description": (
                    f"Endpoint returned 403 Forbidden.\n"
                    f"URL: {url}\nVerify this is intentional access control."
                ),
            })
        elif resp.status_code == 404:
            # Only flag 404 on endpoints that were previously working
            prev_status = endpoint.get("status")
            if prev_status and prev_status != 404:
                result["bugs"].append({
                    "severity": "High",
                    "category": "navigation_error",
                    "title":    f"API endpoint disappeared: {_short_url(url)}",
                    "description": (
                        f"Endpoint previously returned {prev_status} during browser "
                        f"session but now returns 404.\nURL: {url}"
                    ),
                })

        # ── Check 2: Response time ────────────────────────────────────────
        if elapsed_ms > timeout_ms:
            result["bugs"].append({
                "severity": "Medium",
                "category": "performance",
                "title":    f"Slow API response: {_short_url(url)} took {elapsed_ms}ms",
                "description": (
                    f"API endpoint exceeded {timeout_ms}ms budget.\n"
                    f"Actual: {elapsed_ms}ms | URL: {url}\n"
                    f"Slow APIs directly impact user experience."
                ),
            })

        # ── Check 3: Security headers (only on HTML/API responses) ────────
        if resp.status_code < 400:
            content_type = resp.headers.get("content-type", "").lower()
            is_api       = "json" in content_type or "xml" in content_type
            is_html      = "html" in content_type

            if is_html:
                missing_headers = [
                    h for h in _SECURITY_HEADERS
                    if h not in {k.lower() for k in resp.headers}
                ]
                if missing_headers:
                    result["bugs"].append({
                        "severity": "Low",
                        "category": "security",
                        "title":    f"Missing security headers: {_short_url(url)}",
                        "description": (
                            f"Response missing security headers:\n"
                            f"{chr(10).join('  - ' + h for h in missing_headers)}\n"
                            f"URL: {url}"
                        ),
                    })

            # ── Check 4: Sensitive endpoint without auth ──────────────────
            if is_api and resp.status_code == 200:
                url_lower = url.lower()
                is_sensitive = any(p in url_lower for p in _SENSITIVE_PATTERNS)
                has_auth     = any(
                    h in {k.lower() for k in headers}
                    for h in ("authorization", "cookie", "x-auth-token")
                )
                if is_sensitive and not has_auth:
                    result["bugs"].append({
                        "severity": "High",
                        "category": "auth_issue",
                        "title":    f"Sensitive endpoint accessible without auth: {_short_url(url)}",
                        "description": (
                            f"Endpoint matching sensitive pattern returned 200 OK "
                            f"without any authentication headers.\n"
                            f"URL: {url}\n"
                            f"Verify this endpoint is intentionally public."
                        ),
                    })

    except requests.exceptions.Timeout:
        result["error"] = f"Request timed out after {timeout_ms}ms"
        result["bugs"].append({
            "severity": "High",
            "category": "performance",
            "title":    f"API timeout: {_short_url(url)}",
            "description": (
                f"Direct API request timed out after {timeout_ms}ms.\n"
                f"URL: {url}\nMethod: {method}"
            ),
        })
    except requests.exceptions.ConnectionError as e:
        result["error"] = f"Connection failed: {str(e)[:100]}"
    except Exception as e:
        result["error"] = str(e)[:150]

    return result


def run_api_tests(endpoints: list, agent_id: str,
                  base_url: str = "") -> tuple:
    """
    Run API tests on all captured endpoints.
    Returns (api_bugs_count, results_list).
    Called from agent_controller after crawl completes.
    """
    if not endpoints:
        print(f"[API] No endpoints to test for {agent_id}")
        return 0, []

    # Check config
    api_enabled = os.environ.get("API_TESTING", "true").lower() in ("1", "true", "yes")
    if not api_enabled:
        print(f"[API] API testing disabled (API_TESTING=false)")
        return 0, []

    timeout_ms = int(os.environ.get("API_TIMEOUT_MS", "3000"))

    print(f"\n[API] Testing {len(endpoints)} endpoints for {agent_id}...")

    results    = []
    all_bugs   = []
    total_bugs = 0

    with allure.step(f"🔌 API Testing — {len(endpoints)} endpoints"):
        allure.attach(
            "\n".join(f"{e['method']:6} {e['url']}" for e in endpoints[:20]),
            name=f"Endpoints Discovered ({len(endpoints)})",
            attachment_type=allure.attachment_type.TEXT,
        )

        for i, endpoint in enumerate(endpoints, 1):
            url    = endpoint["url"]
            method = endpoint["method"]
            print(f"[API] {i}/{len(endpoints)} {method} {url[:60]}")

            result = test_endpoint(endpoint, timeout_ms=timeout_ms)
            results.append(result)

            if result["bugs"]:
                total_bugs += len(result["bugs"])
                all_bugs.extend(result["bugs"])
                for bug in result["bugs"]:
                    print(f"[API] 🐛 {bug['severity']}: {bug['title']}")

        # ── Summary attachment ─────────────────────────────────────────────
        passed  = sum(1 for r in results if r["passed"])
        failed  = sum(1 for r in results if r["error"])
        slow    = sum(1 for r in results
                      if r["time_ms"] and r["time_ms"] > timeout_ms)
        errors  = [r for r in results if r.get("status", 0) and
                   r["status"] >= 400]

        summary_lines = [
            f"API Test Summary — {agent_id}",
            "=" * 50,
            f"Endpoints tested : {len(endpoints)}",
            f"Successful       : {passed}",
            f"Connection errors: {failed}",
            f"Slow (>{timeout_ms}ms)  : {slow}",
            f"4xx/5xx responses: {len(errors)}",
            f"Bugs found       : {total_bugs}",
            "",
            "Results:",
            "-" * 50,
        ]
        for r in results:
            status_str = str(r["status"]) if r["status"] else "ERR"
            time_str   = f"{r['time_ms']}ms" if r["time_ms"] else "timeout"
            bug_str    = f" ← {len(r['bugs'])} bug(s)" if r["bugs"] else ""
            summary_lines.append(
                f"  {r['method']:6} {status_str:4} {time_str:8} "
                f"{r['url'][:50]}{bug_str}"
            )

        allure.attach(
            "\n".join(summary_lines),
            name=f"API Test Summary ({len(endpoints)} endpoints)",
            attachment_type=allure.attachment_type.TEXT,
        )

        # ── Bug details ────────────────────────────────────────────────────
        if all_bugs:
            bug_lines = [f"API Bugs Found: {len(all_bugs)}", "=" * 50, ""]
            for i, bug in enumerate(all_bugs, 1):
                bug_lines += [
                    f"Bug {i}: [{bug['severity']}] {bug['title']}",
                    f"  Category: {bug['category']}",
                    f"  {bug['description'][:200]}",
                    "",
                ]
            allure.attach(
                "\n".join(bug_lines),
                name=f"API Bugs ({len(all_bugs)} found)",
                attachment_type=allure.attachment_type.TEXT,
            )

    # Save API bugs to bug_reports dir alongside browser bugs
    _save_api_bugs(all_bugs, agent_id, base_url)

    # Save summary JSON for test_api_results.py to read
    _save_api_summary(results, all_bugs, agent_id)

    print(f"[API] Complete: {len(endpoints)} tested, "
          f"{total_bugs} bugs found")
    return total_bugs, results


def _save_api_summary(results: list, bugs: list, agent_id: str):
    """Save API test summary JSON for test_api_results.py to read."""
    try:
        from run_context import RUN_ID, BUG_RUN_DIR
        bug_urls = {b.get("title", "") for b in bugs}
        summary = {
            "agent_id":        agent_id,
            "run_id":          RUN_ID,
            "endpoints_tested": len(results),
            "bugs_found":      len(bugs),
            "endpoints": [
                {
                    "url":      r["url"],
                    "method":   r["method"],
                    "status":   r.get("status"),
                    "time_ms":  r.get("time_ms"),
                    "error":    r.get("error"),
                    "has_bugs": bool(r.get("bugs")),
                }
                for r in results
            ],
        }
        path = os.path.join(BUG_RUN_DIR, f"api_summary_{agent_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            import json
            json.dump(summary, f, indent=2)
        print(f"[API] Summary saved → {path}")
    except Exception as e:
        print(f"[API] Could not save summary: {e}")


def _save_api_bugs(bugs: list, agent_id: str, base_url: str):
    """Save API bugs to the standard bug_reports directory."""
    if not bugs:
        return
    try:
        from reporting.bug_reporter import save_bug_report, generate_bug_report
        for bug in bugs:
            bug_data = {
                "title":       bug["title"],
                "description": bug["description"],
                "severity":    bug["severity"],
                "steps":       [],
                "screenshot":  None,
                "source":      "api",
                "additional_info": {
                    "category":         bug["category"],
                    "detection_source": "api_tester",
                    "url":              base_url,
                    "agent_id":         agent_id,
                },
            }
            report = generate_bug_report(bug_data, allure_attach=True,
                                          agent_id=agent_id)
            save_bug_report(report)
    except Exception as e:
        print(f"[API] Could not save bug reports: {e}")


def _short_url(url: str) -> str:
    """Shorten URL for display in titles."""
    try:
        p = urlparse(url)
        return f"{p.path[:50]}" if p.path else url[:50]
    except Exception:
        return url[:50]
