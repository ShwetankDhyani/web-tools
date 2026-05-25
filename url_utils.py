"""Re-exports from scraper (keeps imports working if this module is expected)."""
from scraper import (  # noqa: F401
    canonicalize_product_url,
    extract_url_from_text,
    is_amazon_host,
    is_flipkart_host,
    prepare_product_url,
)
