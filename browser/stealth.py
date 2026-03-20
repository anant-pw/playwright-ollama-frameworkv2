# browser/stealth.py
#
# PHASE 2B: Playwright Stealth
# ─────────────────────────────
# Bypasses bot detection used by Cloudflare, WAFs, and anti-bot systems.
#
# What bot detectors check:
#   1. navigator.webdriver = true  (dead giveaway)
#   2. Chrome automation flags in window.chrome
#   3. Missing plugins / mimeTypes
#   4. Canvas/WebGL fingerprint inconsistencies
#   5. Unusual screen dimensions
#   6. No mouse movement before interaction
#   7. Inhuman typing speed
#   8. Missing permissions API
#   9. navigator.languages empty
#  10. Headless-specific JS properties
#
# This module patches ALL of them.

import random
import time
import math
import allure
from playwright.sync_api import Page, BrowserContext


# ── JS patches to inject into every page ─────────────────────────────────────

_STEALTH_JS = """
// 1. Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});

// 2. Restore window.chrome
if (!window.chrome) {
    window.chrome = {
        app: { isInstalled: false },
        runtime: {
            connect: function() {},
            sendMessage: function() {},
            id: undefined
        },
        loadTimes: function() {},
        csi: function() {},
    };
}

// 3. Fix plugins (headless has 0 plugins)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
        ];
        plugins.item = (i) => plugins[i];
        plugins.namedItem = (name) => plugins.find(p => p.name === name);
        plugins.refresh = () => {};
        return plugins;
    },
    configurable: true
});

// 4. Fix languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
    configurable: true
});

// 5. Fix permissions
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
}

// 6. Fix mimeTypes
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
        const types = [
            { type: 'application/pdf', description: 'Portable Document Format', suffixes: 'pdf' },
            { type: 'application/x-google-chrome-pdf', description: 'Portable Document Format', suffixes: 'pdf' },
        ];
        types.item = (i) => types[i];
        types.namedItem = (name) => types.find(t => t.type === name);
        return types;
    },
    configurable: true
});

// 7. Fix hardware concurrency (headless often shows unusual values)
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
    configurable: true
});

// 8. Fix deviceMemory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
    configurable: true
});

// 9. Fix connection
Object.defineProperty(navigator, 'connection', {
    get: () => ({
        effectiveType: '4g',
        rtt: 50,
        downlink: 10,
        saveData: false
    }),
    configurable: true
});

// 10. Randomize canvas fingerprint slightly
const originalGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, ...args) {
    const ctx = originalGetContext.call(this, type, ...args);
    if (type === '2d' && ctx) {
        const originalFillText = ctx.fillText.bind(ctx);
        ctx.fillText = function(...args) {
            ctx.shadowColor = `rgba(${Math.floor(Math.random()*2)},${Math.floor(Math.random()*2)},${Math.floor(Math.random()*2)},0.01)`;
            return originalFillText(...args);
        };
    }
    return ctx;
};

// 11. Fix headless detection via screen
Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: true });

// 12. Prevent iframe detection
Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
    get: function() {
        return window;
    }
});

console.log('[STEALTH] Anti-detection patches applied');
"""


def apply_stealth(context: BrowserContext) -> None:
    """
    Apply all stealth patches to a browser context.
    Call this immediately after creating the context, before any navigation.
    """
    try:
        context.add_init_script(_STEALTH_JS)
        print("[STEALTH] JS patches injected into browser context")
    except Exception as e:
        print(f"[STEALTH] Warning: Could not inject stealth JS: {e}")


def apply_stealth_to_page(page: Page) -> None:
    """Apply stealth to a specific page (fallback if context method fails)."""
    try:
        page.add_init_script(_STEALTH_JS)
    except Exception as e:
        print(f"[STEALTH] Page stealth warning: {e}")


# ── Human-like mouse movement ─────────────────────────────────────────────────

def human_move_to(page: Page, x: int, y: int, steps: int = None) -> None:
    """
    Move mouse to (x, y) with a curved human-like path.
    Uses Bezier curve to simulate natural mouse movement.
    """
    if steps is None:
        steps = random.randint(15, 30)

    try:
        # Get current mouse position (approximate — start from center)
        start_x = random.randint(400, 600)
        start_y = random.randint(300, 500)

        # Control points for Bezier curve
        cp1_x = start_x + random.randint(-100, 100)
        cp1_y = start_y + random.randint(-100, 100)
        cp2_x = x + random.randint(-50, 50)
        cp2_y = y + random.randint(-50, 50)

        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier formula
            bx = (1-t)**3*start_x + 3*(1-t)**2*t*cp1_x + 3*(1-t)*t**2*cp2_x + t**3*x
            by = (1-t)**3*start_y + 3*(1-t)**2*t*cp1_y + 3*(1-t)*t**2*cp2_y + t**3*y

            # Add tiny jitter
            jitter_x = random.uniform(-1.5, 1.5)
            jitter_y = random.uniform(-1.5, 1.5)

            page.mouse.move(bx + jitter_x, by + jitter_y)

            # Variable speed — faster in middle, slower at start/end
            delay = 0.01 + 0.02 * math.sin(math.pi * t)
            time.sleep(delay)

    except Exception:
        # Fallback: direct move
        try:
            page.mouse.move(x, y)
        except Exception:
            pass


def human_click(page: Page, selector: str = None,
                x: int = None, y: int = None) -> bool:
    """
    Click with human-like behavior:
    1. Move mouse to element with curved path
    2. Small pause before clicking
    3. Occasional double-movement (like a real human)
    """
    try:
        if selector:
            element = page.locator(selector).first
            box     = element.bounding_box()
            if not box:
                return False

            # Click in slightly random position within element
            click_x = box["x"] + box["width"]  * random.uniform(0.3, 0.7)
            click_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        elif x is not None and y is not None:
            click_x, click_y = x, y
        else:
            return False

        # Move to element
        human_move_to(page, int(click_x), int(click_y))

        # Pause before click (humans take 50-200ms)
        time.sleep(random.uniform(0.05, 0.2))

        # Click
        page.mouse.click(click_x, click_y)
        return True

    except Exception as e:
        print(f"[STEALTH] human_click error: {e}")
        return False


def human_type(page: Page, selector: str, text: str,
               clear_first: bool = True) -> bool:
    """
    Type text with human-like timing:
    - Variable speed between keystrokes (30-150ms)
    - Occasional typo + correction (5% chance per char)
    - Brief pauses after punctuation
    """
    try:
        element = page.locator(selector).first
        element.click()
        time.sleep(random.uniform(0.1, 0.3))

        if clear_first:
            element.select_all()
            time.sleep(0.05)

        for char in text:
            # Occasional typo (5% chance)
            if random.random() < 0.05 and char.isalpha():
                # Type wrong character nearby on keyboard
                wrong = chr(ord(char) + random.choice([-1, 1]))
                page.keyboard.type(wrong)
                time.sleep(random.uniform(0.05, 0.15))
                page.keyboard.press("Backspace")
                time.sleep(random.uniform(0.05, 0.1))

            page.keyboard.type(char)

            # Variable delay between keystrokes
            if char in ".,!?;:":
                time.sleep(random.uniform(0.1, 0.3))  # Pause after punctuation
            elif char == " ":
                time.sleep(random.uniform(0.05, 0.15))
            else:
                time.sleep(random.uniform(0.03, 0.12))

        return True

    except Exception as e:
        print(f"[STEALTH] human_type error: {e}")
        return False


def human_scroll(page: Page, direction: str = "down",
                 amount: int = None) -> None:
    """
    Scroll with human-like behavior — variable speed, pauses mid-scroll.
    """
    if amount is None:
        amount = random.randint(200, 600)

    if direction == "up":
        amount = -amount

    # Scroll in multiple small steps
    steps    = random.randint(3, 8)
    per_step = amount // steps

    for _ in range(steps):
        page.mouse.wheel(0, per_step + random.randint(-20, 20))
        time.sleep(random.uniform(0.05, 0.15))


# ── Random delays ─────────────────────────────────────────────────────────────

def human_pause(min_ms: int = 500, max_ms: int = 2000) -> None:
    """Random pause simulating human reading/thinking time."""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def pre_interaction_pause() -> None:
    """Short pause before interacting with an element — like a human."""
    time.sleep(random.uniform(0.3, 0.8))


def post_navigation_pause() -> None:
    """Pause after navigation — like a human waiting for page to settle."""
    time.sleep(random.uniform(0.5, 1.5))


# ── Stealth context creator ───────────────────────────────────────────────────

def get_stealth_launch_args() -> list:
    """
    Additional Chrome args that help bypass bot detection.
    These go INTO browser_launch_kwargs()['args'].
    """
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-gpu",
        "--disable-http2",
        "--ignore-certificate-errors",
        "--disable-web-security",
        "--allow-running-insecure-content",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
        # Prevent Chrome from showing automation banner
        "--disable-extensions",
        "--disable-default-apps",
        "--no-first-run",
        "--no-default-browser-check",
        # Randomize window size slightly to avoid fingerprinting
        f"--window-size={random.randint(1260, 1300)},{random.randint(780, 820)}",
    ]


def get_stealth_context_args(user_agent: str = None,
                              viewport_w: int = 1280,
                              viewport_h: int = 800) -> dict:
    """
    Browser context args with stealth settings.
    """
    # Rotate through realistic user agents
    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    ]

    ua = user_agent or random.choice(_USER_AGENTS)

    # Slightly randomize viewport to avoid fingerprinting
    vw = viewport_w + random.randint(-10, 10)
    vh = viewport_h + random.randint(-10, 10)

    return {
        "user_agent":          ua,
        "viewport":            {"width": vw, "height": vh},
        "locale":              "en-US",
        "timezone_id":         "America/New_York",
        "java_script_enabled": True,
        "accept_downloads":    False,
        "ignore_https_errors": True,
        "extra_http_headers":  {
            "Accept-Language":           "en-US,en;q=0.9",
            "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding":           "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest":            "document",
            "Sec-Fetch-Mode":            "navigate",
            "Sec-Fetch-Site":            "none",
            "Sec-Fetch-User":            "?1",
        },
    }


def verify_stealth(page: Page) -> dict:
    """
    Run bot-detection checks and return results.
    Useful for debugging — shows what a bot detector would see.
    """
    results = {}
    checks = {
        "webdriver":        "navigator.webdriver",
        "chrome_exists":    "!!window.chrome",
        "plugins_count":    "navigator.plugins.length",
        "languages":        "JSON.stringify(navigator.languages)",
        "hw_concurrency":   "navigator.hardwareConcurrency",
        "device_memory":    "navigator.deviceMemory",
        "connection_type":  "navigator.connection ? navigator.connection.effectiveType : 'unknown'",
    }

    for name, js in checks.items():
        try:
            results[name] = page.evaluate(js)
        except Exception:
            results[name] = "error"

    return results
