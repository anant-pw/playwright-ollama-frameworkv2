# brain/smart_crawler.py
#
# FIXED:
#   - ai_rank_pages() is now OFF by default
#     Before: called Ollama just to sort URLs that score_url() already scores
#     After:  score_url() sorting is used by default (deterministic, fast)
#     Enable AI ranking: AUTONOMY_LEVEL=3 or set use_ai_ranking=True
#   - Accepted original_entry fix (unchanged)
#   - Login URL exclusion fix (unchanged)

import re
import allure
from urllib.parse import urljoin, urlparse
from ai.ollama_client import generate, OllamaUnavailableError


_HIGH_VALUE_PATTERNS = [
    (10, r"login|signin|sign-in|sign_in"),
    (10, r"register|signup|sign-up|create.account"),
    (9,  r"checkout|payment|billing|cart|basket"),
    (9,  r"password|forgot|reset"),
    (8,  r"profile|account|settings|preferences"),
    (8,  r"dashboard|overview|home"),
    (7,  r"order|purchase|confirm"),
    (6,  r"product|item|detail|view|inventory"),
    (5,  r"search|results|find"),
    (4,  r"list|catalog|category|browse"),
    (2,  r"about|contact|help|faq"),
    (1,  r"blog|news|article"),
]

_SKIP_PATTERNS = [
    r"\.(pdf|zip|png|jpg|jpeg|gif|svg|ico|css|js|woff|ttf)$",
    r"mailto:|tel:|javascript:|^#$",
    r"/cdn-|/static/|/assets/|/images/|/fonts/",
    r"logout|signout|sign-out",
    r"facebook\.com|twitter\.com|linkedin\.com|instagram\.com",
    r"google\.com|apple\.com|microsoft\.com",
]

_SPA_ROUTE_PATTERNS = [
    "/inventory", "/cart", "/checkout-step-one", "/checkout-step-two",
    "/checkout-complete", "/about", "/contact", "/profile",
    "/settings", "/dashboard", "/products", "/orders",
]


def score_url(url: str, base_domain: str, login_urls: set = None) -> int:
    """Score URL — returns -1 to skip, 0-10 for priority."""
    url_lower = url.lower()

    if login_urls and url in login_urls:
        return -1

    try:
        parsed = urlparse(url)
        if parsed.netloc and base_domain not in parsed.netloc:
            return -1
    except Exception:
        return -1

    for pattern in _SKIP_PATTERNS:
        if re.search(pattern, url_lower):
            return -1

    for score, pattern in _HIGH_VALUE_PATTERNS:
        if re.search(pattern, url_lower):
            return score

    return 3


def extract_crawlable_links(page, base_url: str,
                             login_urls: set = None) -> list:
    """Extract all crawlable links — handles <a href>, SPAs, and JS routing."""
    base_domain = urlparse(base_url).netloc
    base_origin = f"{urlparse(base_url).scheme}://{base_domain}"
    links       = []
    seen        = set()
    login_urls  = login_urls or set()

    # Method 1: Standard <a href>
    try:
        hrefs = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({
                    href: a.href,
                    text: (a.innerText||'').trim().replace(/\\s+/g,' ').substring(0,80)
                }))
                .filter(a => a.href && !a.href.startsWith('javascript'));
        }""")
        for item in hrefs:
            url  = item.get("href", "").strip()
            text = item.get("text", "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            if url.startswith("/"):
                url = urljoin(base_url, url)
            score = score_url(url, base_domain, login_urls)
            if score >= 0:
                links.append((url, text, score))
    except Exception as e:
        print(f"[CRAWLER] <a> extraction error: {e}")

    # Method 2: SPA route probing
    try:
        for route in _SPA_ROUTE_PATTERNS:
            for suffix in [".html", ""]:
                candidate = f"{base_origin}{route}{suffix}"
                if candidate not in seen:
                    seen.add(candidate)
                    score = score_url(candidate, base_domain, login_urls)
                    if score >= 0:
                        links.append((candidate, route.strip("/"), score))
    except Exception as e:
        print(f"[CRAWLER] SPA route error: {e}")

    # Method 3: JS framework attributes
    try:
        js_routes = page.evaluate("""() => {
            const selectors = ['[data-href]','[router-link]','[routerlink]',
                               '[ng-href]','[ui-sref]','[data-url]'];
            const found = [];
            for (const sel of selectors) {
                try {
                    document.querySelectorAll(sel).forEach(el => {
                        const href = el.getAttribute('data-href') ||
                                     el.getAttribute('router-link') ||
                                     el.getAttribute('routerlink') ||
                                     el.getAttribute('ng-href') || '';
                        if (href) found.push({
                            href: href,
                            text: (el.innerText||'').trim().substring(0,60)
                        });
                    });
                } catch(e) {}
            }
            return found;
        }""")
        for item in js_routes:
            url  = item.get("href", "").strip()
            text = item.get("text", "").strip()
            if url and url not in seen:
                seen.add(url)
                if url.startswith("/"):
                    url = urljoin(base_url, url)
                score = score_url(url, base_domain, login_urls)
                if score >= 0:
                    links.append((url, text, score))
    except Exception:
        pass

    links.sort(key=lambda x: x[2], reverse=True)
    print(f"[CRAWLER] Found {len(links)} crawlable links")
    return links


def ai_rank_pages(links, visited, current_url, max_suggest=5):
    """
    AI-based URL ranking — only used at AUTONOMY_LEVEL=3.
    At levels 1 and 2, score_url() sorting in extract_crawlable_links() is sufficient.
    """
    candidates = [(u, t, s) for u, t, s in links if u not in visited][:15]
    if not candidates:
        return []
    if len(candidates) <= 3:
        return [u for u, _, _ in candidates[:max_suggest]]

    candidates_text = "\n".join(
        f"  {i+1}. [{s}pts] {t[:40]:40} -> {u}"
        for i, (u, t, s) in enumerate(candidates)
    )
    prompt = f"""QA engineer selecting pages to test.
Current: {current_url}
Candidates:
{candidates_text}

Pick {max_suggest} most valuable for testing (auth, checkout, forms first).
Respond ONLY with numbers: 1,3,2"""

    try:
        response = generate(prompt)
        if response:
            numbers = [int(n.strip())-1 for n in response.split(",")
                       if n.strip().isdigit()]
            ranked  = [candidates[n][0] for n in numbers
                       if 0 <= n < len(candidates)]
            if ranked:
                return ranked[:max_suggest]
    except Exception:
        pass

    return [u for u, _, _ in candidates[:max_suggest]]


class SmartCrawler:
    def __init__(self, entry_url: str, max_pages: int = 5,
                 max_depth: int = 3, original_entry: str = None):
        self.entry_url      = entry_url
        self.original_entry = original_entry or entry_url
        self.max_pages      = max_pages
        self.max_depth      = max_depth
        self.base_domain    = urlparse(entry_url).netloc

        # Load autonomy to decide if AI ranking is used
        try:
            from core.autonomy import AUTONOMY
            self._use_ai_ranking = AUTONOMY.ai_url_ranking
        except ImportError:
            self._use_ai_ranking = False

        # Pre-populate login URLs to avoid crawling back to login
        self.login_urls = ({original_entry, entry_url}
                           if original_entry != entry_url else set())
        base = f"{urlparse(entry_url).scheme}://{urlparse(entry_url).netloc}"
        for suffix in ["/login", "/login.html", "/signin", "/sign-in",
                       "/users/sign_in", "/auth/login"]:
            self.login_urls.add(f"{base}{suffix}")

        self.visited       = set(self.login_urls)
        self.queue         = []
        self.crawl_log     = []
        self.pages_visited = 0

    def next_url(self):
        while self.queue:
            url, depth, source = self.queue.pop(0)
            if url not in self.visited and depth <= self.max_depth:
                return url, depth
        return None, None

    def mark_visited(self, url, depth, title="",
                     bugs_found=0, tcs_generated=0):
        self.visited.add(url)
        self.pages_visited += 1
        self.crawl_log.append({
            "page": self.pages_visited, "url": url, "depth": depth,
            "title": title, "bugs_found": bugs_found,
            "tcs_generated": tcs_generated,
        })
        print(f"[CRAWLER] Visited {self.pages_visited}/{self.max_pages}: {url[:60]}")

    def add_links(self, page, current_url, current_depth):
        if current_depth >= self.max_depth:
            return 0
        if self.pages_visited >= self.max_pages:
            return 0

        links     = extract_crawlable_links(page, self.entry_url, self.login_urls)
        new_depth = current_depth + 1
        remaining = self.max_pages - self.pages_visited

        # Default: use score_url() ranking (already sorted in extract_crawlable_links)
        # Level 3 only: use ai_rank_pages() for smarter selection
        if self._use_ai_ranking:
            next_urls = ai_rank_pages(links, self.visited, current_url,
                                       max_suggest=min(remaining, 3))
        else:
            # Just take the top-scored links from sorted list
            candidates = [u for u, _, _ in links if u not in self.visited]
            next_urls  = candidates[:min(remaining, 3)]

        added       = 0
        queued_urls = {q[0] for q in self.queue}
        for url in next_urls:
            if url not in self.visited and url not in queued_urls:
                self.queue.append((url, new_depth, current_url))
                added += 1
                print(f"[CRAWLER] Queued: {url[:60]} (depth {new_depth})")

        return added

    def is_complete(self):
        return self.pages_visited >= self.max_pages or not self.queue

    def attach_crawl_map(self):
        if not self.crawl_log:
            return
        lines = [
            "Smart Crawl Summary", "=" * 50,
            f"Entry URL:     {self.entry_url}",
            f"Pages visited: {self.pages_visited}/{self.max_pages}",
            f"Max depth:     {self.max_depth}",
            f"AI ranking:    {'ON (Level 3)' if self._use_ai_ranking else 'OFF (score-based)'}",
            "", "Pages Crawled:", "-" * 50,
        ]
        for log in self.crawl_log:
            status = []
            if log["bugs_found"]:    status.append(f"{log['bugs_found']} bug(s)")
            if log["tcs_generated"]: status.append(f"{log['tcs_generated']} TC(s)")
            status_str = f"  [{', '.join(status)}]" if status else "  [no findings]"
            lines.append(
                f"  Page {log['page']} (depth {log['depth']}){status_str}\n"
                f"    URL:   {log['url']}\n"
                f"    Title: {log['title'] or 'unknown'}\n"
            )
        try:
            allure.attach("\n".join(lines), name="Smart Crawl Map",
                          attachment_type=allure.attachment_type.TEXT)
        except Exception:
            pass
