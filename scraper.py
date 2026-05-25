"""
Stealth price scraper module.

Uses curl_cffi for TLS fingerprint spoofing, rotating headers,
humanized timing, exponential backoff, and proxy support.
Designed to be stateless — no loops, no threads, no persistent state.
"""

import json
import logging
import os
import random
import re
import time
from functools import wraps
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

logger = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# Configuration via environment variables
# ---------------------------------------------------------------------------

# Comma-separated proxy list, e.g. "http://user:pass@host:port,socks5://..."
PROXY_LIST = [p.strip() for p in os.environ.get("PROXY_LIST", "").split(",") if p.strip()]

# Third-party scraping API (ScraperAPI, ZenRows, etc.)
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")
SCRAPER_API_URL = os.environ.get(
    "SCRAPER_API_URL", "https://api.scraperapi.com/?api_key={key}&url={url}"
)

# ---------------------------------------------------------------------------
# Browser fingerprints to impersonate (curl_cffi supported browsers)
# ---------------------------------------------------------------------------

BROWSER_FINGERPRINTS = [
    "chrome120", "chrome119", "chrome116", "chrome110",
    "chrome107", "chrome104", "chrome101", "chrome100",
    "safari17_0", "safari15_5",
    "edge101", "edge99",
]

# ---------------------------------------------------------------------------
# Realistic rotating headers
# ---------------------------------------------------------------------------

USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

SEC_CH_UA_VALUES = [
    '"Chromium";v="125", "Google Chrome";v="125", "Not-A.Brand";v="24"',
    '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="24"',
    '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="8"',
    '"Microsoft Edge";v="125", "Chromium";v="125", "Not-A.Brand";v="24"',
]

ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.8",
]

REFERERS = [
    "https://www.google.com/",
    "https://www.google.co.in/",
    "https://www.google.com/search?q=",
    "",  # sometimes no referer is more natural
]


def _generate_headers() -> dict:
    """Generate a realistic, randomized set of browser headers."""
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    referer = random.choice(REFERERS)
    if referer:
        headers["Referer"] = referer

    # Add Sec-Ch-Ua headers for Chrome/Edge UAs
    if "Chrome" in ua or "Edg" in ua:
        headers["Sec-Ch-Ua"] = random.choice(SEC_CH_UA_VALUES)
        headers["Sec-Ch-Ua-Mobile"] = "?0"
        headers["Sec-Ch-Ua-Platform"] = random.choice(['"Windows"', '"macOS"'])
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none" if not referer else "cross-site"
        headers["Sec-Fetch-User"] = "?1"

    return headers


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------

def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """Decorator: retries on 403, 429, 503 with exponential backoff + jitter."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    return result
                except RetryableError as e:
                    if attempt == max_retries:
                        logger.warning("Max retries reached for %s: %s", func.__name__, e)
                        raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0.5, 2.0)
                    logger.info("Retry %d/%d after %.1fs (status %s)", attempt + 1, max_retries, delay, e.status_code)
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


class RetryableError(Exception):
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(message or f"HTTP {status_code}")


class CaptchaDetected(Exception):
    pass


# ---------------------------------------------------------------------------
# Core HTTP fetch with stealth
# ---------------------------------------------------------------------------

def _get_proxy() -> str | None:
    """Pick a random proxy from the configured list, or None."""
    if PROXY_LIST:
        return random.choice(PROXY_LIST)
    return None


@retry_with_backoff(max_retries=3, base_delay=2.0)
def stealth_fetch(url: str) -> str:
    """
    Fetch a URL using curl_cffi with TLS fingerprint spoofing.
    Returns the HTML text on success.
    Raises RetryableError for 403/429/503.
    Raises CaptchaDetected if a CAPTCHA page is detected.
    """
    # If a scraping API is configured, use it instead
    if SCRAPER_API_KEY:
        api_url = SCRAPER_API_URL.format(key=SCRAPER_API_KEY, url=url)
        resp = cffi_requests.get(api_url, timeout=30)
        if resp.status_code == 200:
            return resp.text
        if resp.status_code in (403, 429, 503):
            raise RetryableError(resp.status_code)
        return ""

    headers = _generate_headers()
    impersonate = random.choice(BROWSER_FINGERPRINTS)
    proxy = _get_proxy()
    proxies = {"https": proxy, "http": proxy} if proxy else None

    try:
        resp = cffi_requests.get(
            url,
            headers=headers,
            impersonate=impersonate,
            timeout=20,
            allow_redirects=True,
            proxies=proxies,
        )
    except Exception as e:
        logger.error("Request failed for %s: %s", url, e)
        return ""

    if resp.status_code in (403, 429, 503):
        raise RetryableError(resp.status_code)

    if resp.status_code != 200:
        logger.warning("HTTP %d for %s", resp.status_code, url)
        return ""

    html = resp.text

    # Detect CAPTCHA pages
    captcha_signals = [
        "captcha", "robot", "automated", "unusual traffic",
        "verify you are a human", "are you a robot",
    ]
    lower_html = html[:5000].lower()
    if any(sig in lower_html for sig in captcha_signals) and len(html) < 20000:
        raise CaptchaDetected(f"CAPTCHA detected at {url}")

    return html


# ---------------------------------------------------------------------------
# Price parsing utilities
# ---------------------------------------------------------------------------

def parse_price(text: str) -> float | None:
    """Extract a numeric price from a text string."""
    if not text:
        return None
    cleaned = re.sub(r'[^\d.,]', '', text.strip())
    if not cleaned:
        return None
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rindex(',') > cleaned.rindex('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def _extract_price_from_ld(data) -> float | None:
    """Recursively extract price from JSON-LD structured data."""
    if isinstance(data, dict):
        if "price" in data:
            return parse_price(str(data["price"]))
        if "lowPrice" in data:
            return parse_price(str(data["lowPrice"]))
        offers = data.get("offers")
        if offers:
            return _extract_price_from_ld(offers)
        for v in data.values():
            result = _extract_price_from_ld(v)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_price_from_ld(item)
            if result is not None:
                return result
    return None


# ---------------------------------------------------------------------------
# Site-specific parsers
# ---------------------------------------------------------------------------

def _parse_amazon(soup: BeautifulSoup) -> tuple[str | None, float | None]:
    """Parse product name and price from Amazon."""
    name = None
    price = None

    title_el = soup.find("span", id="productTitle")
    if title_el:
        name = title_el.get_text(strip=True)

    # Priority 1: core price container (most reliable on modern Amazon pages)
    for container_id in ("corePrice_feature_div", "corePriceDisplay_desktop_feature_div"):
        container = soup.find(id=container_id)
        if container:
            core_el = container.select_one("span.a-price.apex-core-price-identifier span.a-offscreen")
            if not core_el:
                core_el = container.select_one("span.a-price span.a-offscreen")
            if core_el:
                price = parse_price(core_el.get_text())
                if price is not None:
                    return name, price

    # Priority 2: specific price block IDs
    for pid in ("tp_price_block_total_price_ww", "priceblock_ourprice", "priceblock_dealprice"):
        el = soup.find(id=pid)
        if el:
            offscreen = el.find("span", class_="a-offscreen")
            price = parse_price((offscreen or el).get_text())
            if price is not None:
                return name, price

    # Priority 3: apex price identifier class (deal/sale price)
    apex_price = soup.select_one("span.a-price.apex-core-price-identifier span.a-offscreen")
    if apex_price:
        price = parse_price(apex_price.get_text())
        if price is not None:
            return name, price

    return name, price


def _parse_flipkart(soup: BeautifulSoup) -> tuple[str | None, float | None]:
    """Parse product name and price from Flipkart."""
    name = None
    price = None

    # Flipkart title
    for cls in ("B_NuCI", "VU-ZEz"):
        el = soup.find("span", class_=cls)
        if el:
            name = el.get_text(strip=True)
            break
    if not name:
        title_el = soup.find("h1")
        if title_el:
            name = title_el.get_text(strip=True)

    # Flipkart price (class names change frequently)
    for cls in ("Nx9bqj", "_30jeq3", "CxhGGd"):
        el = soup.find("div", class_=cls)
        if el:
            price = parse_price(el.get_text())
            if price is not None:
                break

    return name, price


def _parse_desidime(soup: BeautifulSoup) -> tuple[str | None, float | None]:
    """Parse product name and price from DesiDime."""
    name = None
    price = None

    title_el = soup.find("h1")
    if title_el:
        name = title_el.get_text(strip=True)

    price_el = soup.find("span", class_="amount") or soup.find("span", class_="price")
    if price_el:
        price = parse_price(price_el.get_text())

    return name, price


# ---------------------------------------------------------------------------
# Main scraping function
# ---------------------------------------------------------------------------

def scrape_price(url: str) -> tuple[str | None, float | None]:
    """
    Scrape product name and price from a URL.
    Returns (name, price). Both may be None on failure.
    Stateless — executes once and returns.
    """
    try:
        html = stealth_fetch(url)
        if not html:
            logger.warning("Empty response from %s", url)
            return None, None
    except CaptchaDetected:
        logger.error("CAPTCHA detected at %s — skipping", url)
        return None, None
    except RetryableError as e:
        logger.error("Failed after retries for %s: HTTP %s", url, e.status_code)
        return None, None
    except Exception as e:
        logger.error("Unexpected fetch error for %s: %s", url, e)
        return None, None

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.error("HTML parsing failed for %s: %s", url, e)
        return None, None

    domain = urlparse(url).netloc.lower()
    name = None
    price = None

    # Site-specific parsing
    try:
        if "amazon" in domain:
            name, price = _parse_amazon(soup)
        elif "flipkart" in domain:
            name, price = _parse_flipkart(soup)
        elif "desidime" in domain:
            name, price = _parse_desidime(soup)
    except Exception as e:
        logger.error("Site-specific parsing error for %s: %s", url, e)

    # Fallback: product title from meta tags
    if not name:
        try:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                name = og_title["content"].strip()
            elif soup.title:
                name = soup.title.get_text(strip=True)
        except Exception:
            pass

    # Fallback: JSON-LD structured data
    if price is None:
        try:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    ld = json.loads(script.string)
                    price = _extract_price_from_ld(ld)
                    if price is not None:
                        break
                except (json.JSONDecodeError, TypeError):
                    continue
        except Exception as e:
            logger.debug("JSON-LD parsing failed: %s", e)

    # Fallback: price meta tags
    if price is None:
        try:
            for meta in soup.find_all("meta"):
                prop = (meta.get("property") or meta.get("name") or "").lower()
                if "price" in prop and "amount" in prop:
                    price = parse_price(meta.get("content", ""))
                    if price is not None:
                        break
        except Exception as e:
            logger.debug("Meta price parsing failed: %s", e)

    # Fallback: regex price patterns in visible text
    if price is None:
        try:
            text = soup.get_text()[:10000]
            price_matches = re.findall(
                r'(?:[$\u20ac\u00a3\u20b9\u00a5])\s*([\d,]+(?:\.\d{1,2})?)|'
                r'([\d,]+(?:\.\d{1,2})?)\s*(?:USD|EUR|GBP|INR)',
                text,
            )
            for m in price_matches:
                val = m[0] or m[1]
                p = parse_price(val)
                if p and p > 0:
                    price = p
                    break
        except Exception as e:
            logger.debug("Regex price parsing failed: %s", e)

    return name, price
