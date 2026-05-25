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
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# URL normalization (short/mobile share links)
# ---------------------------------------------------------------------------

AMAZON_SHORT_HOSTS = frozenset({
    "amzn.in", "amzn.to", "a.co", "amzn.eu", "amzn.asia", "amzn.com",
})
FLIPKART_SHORT_HOSTS = frozenset({"fkrt.it", "dl.flipkart.com"})
_ASIN_RE = re.compile(
    r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})",
    re.I,
)
_STRIP_QUERY_KEYS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "ref_", "tag", "linkCode", "psc", "smid",
})


def extract_url_from_text(text: str) -> str:
    """Pull the first http(s) URL from pasted share text."""
    if not text:
        return ""
    text = re.sub(r"[\u200b-\u200d\ufeff\u00a0]", "", text.strip())
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return _trim_url_token(text.split()[0])
    match = re.search(r"https?://[^\s<>\"']+", text, re.I)
    return _trim_url_token(match.group(0)) if match else text


def _trim_url_token(url: str) -> str:
    return url.rstrip(".,;:!?)\"]'")


def is_amazon_host(host: str) -> bool:
    host = host.lower().removeprefix("www.")
    return "amazon" in host or host in AMAZON_SHORT_HOSTS


def is_flipkart_host(host: str) -> bool:
    host = host.lower().removeprefix("www.")
    return "flipkart" in host or host in FLIPKART_SHORT_HOSTS


def canonicalize_product_url(url: str) -> str:
    """Strip tracking params and canonicalize known store product URLs."""
    if not url:
        return url
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path or ""

    if is_amazon_host(host):
        match = _ASIN_RE.search(path)
        if match:
            asin = match.group(1).upper()
            if host == "amzn.in" or ".in" in host or "amazon.in" in host:
                base = "https://www.amazon.in"
            elif host in ("a.co", "amzn.to") or host.endswith(".com"):
                base = "https://www.amazon.com"
            elif host.endswith(".co.uk") or "amazon.co.uk" in host:
                base = "https://www.amazon.co.uk"
            else:
                base = f"https://www.{host}" if "amazon" in host else "https://www.amazon.in"
            return f"{base}/dp/{asin}"
        if "amazon" in host:
            return _strip_tracking_params(url)

    if is_flipkart_host(host):
        return _strip_tracking_params(url)

    return _strip_tracking_params(url)


def _strip_tracking_params(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in params.items() if k.lower() not in _STRIP_QUERY_KEYS}
    if not filtered and parsed.query:
        keep = {k: v for k, v in params.items() if k.lower() in ("th", "psc")}
        filtered = keep
    if not filtered:
        return urlunparse(parsed._replace(query=""))
    return urlunparse(parsed._replace(query=urlencode(filtered, doseq=True)))


def prepare_product_url(raw: str) -> str:
    """Clean pasted text into a bare URL (resolve happens in stealth_fetch)."""
    return extract_url_from_text(raw)
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
def stealth_fetch(url: str) -> tuple[str, str]:
    """
    Fetch a URL using curl_cffi with TLS fingerprint spoofing.
    Returns (HTML text, final URL after redirects).
    Raises RetryableError for 403/429/503.
    Raises CaptchaDetected if a CAPTCHA page is detected.
    """
    # If a scraping API is configured, use it instead
    if SCRAPER_API_KEY:
        api_url = SCRAPER_API_URL.format(key=SCRAPER_API_KEY, url=url)
        resp = cffi_requests.get(api_url, timeout=30)
        if resp.status_code == 200:
            return resp.text, url
        if resp.status_code in (403, 429, 503):
            raise RetryableError(resp.status_code)
        return "", url

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
        return "", url

    final_url = getattr(resp, "url", None) or url

    if resp.status_code in (403, 429, 503):
        raise RetryableError(resp.status_code)

    if resp.status_code != 200:
        logger.warning("HTTP %d for %s", resp.status_code, url)
        return "", final_url

    html = resp.text

    # Detect CAPTCHA pages
    captcha_signals = [
        "captcha", "robot", "automated", "unusual traffic",
        "verify you are a human", "are you a robot",
    ]
    lower_html = html[:5000].lower()
    if any(sig in lower_html for sig in captcha_signals) and len(html) < 20000:
        raise CaptchaDetected(f"CAPTCHA detected at {url}")

    return html, final_url


# ---------------------------------------------------------------------------
# Price parsing utilities
# ---------------------------------------------------------------------------

def currency_from_text(text: str) -> str | None:
    """Detect currency symbol from price text (e.g. a-offscreen content)."""
    if not text:
        return None
    t = text.strip()
    if "₹" in t or re.search(r"\bRs\.?\s*\d", t, re.I) or "INR" in t.upper():
        return "₹"
    if "€" in t or "EUR" in t.upper():
        return "€"
    if "£" in t or "GBP" in t.upper():
        return "£"
    if "¥" in t or "JPY" in t.upper():
        return "¥"
    if "$" in t or "USD" in t.upper():
        return "$"
    return None


def currency_from_url(url: str) -> str:
    """Default currency from store domain."""
    domain = urlparse(url).netloc.lower()
    if is_amazon_host(domain) and (domain == "amzn.in" or ".in" in domain or "amazon.in" in domain):
        return "₹"
    if domain in ("a.co", "amzn.to") or domain.endswith("amazon.com"):
        return "$"
    if ".in" in domain or "amazon.in" in domain or "flipkart" in domain or "desidime" in domain:
        return "₹"
    if domain.endswith(".co.uk") or domain.endswith(".uk"):
        return "£"
    if any(domain.endswith(s) for s in (".eu", ".de", ".fr", ".it", ".es")):
        return "€"
    if domain.endswith(".co.jp") or domain.endswith(".jp"):
        return "¥"
    if domain.endswith(".com.au") or domain.endswith(".au"):
        return "A$"
    if domain.endswith(".ca"):
        return "C$"
    return "$"


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

def _price_from_offscreen(el) -> tuple[float | None, str | None]:
    if not el:
        return None, None
    raw = el.get_text()
    return parse_price(raw), currency_from_text(raw)


def _parse_amazon(soup: BeautifulSoup, url: str = "") -> tuple[str | None, float | None, str | None]:
    """Parse product name and price from Amazon."""
    name = None
    price = None
    currency = None
    domain = urlparse(url).netloc.lower() if url else ""
    india = ".in" in domain or "amazon.in" in domain

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
                price, currency = _price_from_offscreen(core_el)
                if price is not None:
                    return name, price, currency

    # Priority 2: specific price block IDs (skip worldwide USD block on Amazon India)
    block_ids = ["priceblock_ourprice", "priceblock_dealprice"]
    if not india:
        block_ids.insert(0, "tp_price_block_total_price_ww")
    for pid in block_ids:
        el = soup.find(id=pid)
        if el:
            offscreen = el.find("span", class_="a-offscreen")
            price, currency = _price_from_offscreen(offscreen or el)
            if price is not None:
                if india and currency == "$":
                    continue
                return name, price, currency

    # Priority 3: any a-offscreen with local currency on India sites
    if india:
        for off in soup.select("span.a-offscreen"):
            raw = off.get_text()
            if "₹" not in raw and "INR" not in raw.upper():
                continue
            price, currency = _price_from_offscreen(off)
            if price is not None:
                return name, price, currency or "₹"

    apex_price = soup.select_one("span.a-price.apex-core-price-identifier span.a-offscreen")
    if apex_price:
        price, currency = _price_from_offscreen(apex_price)
        if price is not None:
            if not (india and currency == "$"):
                return name, price, currency

    return name, price, currency


def _parse_flipkart(soup: BeautifulSoup) -> tuple[str | None, float | None, str | None]:
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
    currency = "₹"
    for cls in ("Nx9bqj", "_30jeq3", "CxhGGd"):
        el = soup.find("div", class_=cls)
        if el:
            price = parse_price(el.get_text())
            if price is not None:
                break

    return name, price, currency


def _parse_desidime(soup: BeautifulSoup) -> tuple[str | None, float | None, str | None]:
    """Parse product name and price from DesiDime."""
    name = None
    price = None

    title_el = soup.find("h1")
    if title_el:
        name = title_el.get_text(strip=True)

    price_el = soup.find("span", class_="amount") or soup.find("span", class_="price")
    if price_el:
        price = parse_price(price_el.get_text())

    return name, price, "₹"


# ---------------------------------------------------------------------------
# Main scraping function
# ---------------------------------------------------------------------------

def scrape_price(url: str) -> tuple[str | None, float | None, str, str]:
    """
    Scrape product name, price, and currency from a URL.
    Returns (name, price, currency, canonical_url). Price/name may be None on failure.
    """
    canonical_url = url
    try:
        html, final_url = stealth_fetch(url)
        if final_url and final_url != url:
            logger.info("Resolved %s → %s", url[:60], final_url[:80])
        page_url = canonicalize_product_url(final_url or url)
        canonical_url = page_url
        if not html:
            logger.warning("Empty response from %s", url)
            return None, None, currency_from_url(page_url), canonical_url
    except CaptchaDetected:
        logger.error("CAPTCHA detected at %s — skipping", url)
        return None, None, currency_from_url(url), url
    except RetryableError as e:
        logger.error("Failed after retries for %s: HTTP %s", url, e.status_code)
        return None, None, currency_from_url(url), url
    except Exception as e:
        logger.error("Unexpected fetch error for %s: %s", url, e)
        return None, None, currency_from_url(url), url

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.error("HTML parsing failed for %s: %s", page_url, e)
        return None, None, currency_from_url(page_url), canonical_url

    domain = urlparse(page_url).netloc.lower()
    name = None
    price = None
    currency = currency_from_url(page_url)

    # Site-specific parsing (use final URL host — short links like amzn.in redirect to amazon.*)
    try:
        if is_amazon_host(domain):
            name, price, cur = _parse_amazon(soup, page_url)
            if cur:
                currency = cur
        elif is_flipkart_host(domain):
            name, price, cur = _parse_flipkart(soup)
            if cur:
                currency = cur
        elif "desidime" in domain:
            name, price, cur = _parse_desidime(soup)
            if cur:
                currency = cur
    except Exception as e:
        logger.error("Site-specific parsing error for %s: %s", page_url, e)

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
            sym_match = re.search(
                r'([$\u20ac\u00a3\u20b9\u00a5])\s*([\d,]+(?:\.\d{1,2})?)',
                text,
            )
            if sym_match:
                cur = currency_from_text(sym_match.group(1))
                if cur:
                    currency = cur
                price = parse_price(sym_match.group(0))
            if price is None:
                for m in re.finditer(
                    r'([\d,]+(?:\.\d{1,2})?)\s*(USD|EUR|GBP|INR)',
                    text,
                    re.I,
                ):
                    p = parse_price(m.group(1))
                    if p and p > 0:
                        price = p
                        code = m.group(2).upper()
                        currency = {"INR": "₹", "GBP": "£", "EUR": "€", "USD": "$"}.get(code, currency)
                        break
        except Exception as e:
            logger.debug("Regex price parsing failed: %s", e)

    return name, price, currency, canonical_url
