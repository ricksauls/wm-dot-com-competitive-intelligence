"""
Daily keyword scraper — WM Dot Com Competitive Intelligence
Runs once per day via cron (or manually triggered).

For each active keyword:
  - Scrapes page 1 of Walmart.com search results
  - Records every position to search_results table
  - Flags new SKUs from tracked competitor brands
  - Computes share_of_search rollup per brand per keyword

Uses a fresh browser instance per keyword (same anti-detection
approach as demo 1 — Walmart flags sessions after first scrape).
"""

import asyncio
import random
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    Brand, Product, Keyword,
    SearchResult, ShareOfSearch,
)

import logging
log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

CST = ZoneInfo("America/Chicago")


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_config(db: Session) -> tuple[list, dict, dict]:
    """
    Load active keywords, products, and brands from the database.

    Returns:
        keywords  — list of Keyword objects
        item_map  — dict of walmart_item_id → Product object (for fast lookup)
        brand_map — dict of brand_id → Brand object
    """
    keywords = db.query(Keyword).filter(Keyword.active == True).all()
    products = db.query(Product).filter(Product.active == True).all()
    brands   = db.query(Brand).all()

    item_map  = {p.walmart_item_id: p for p in products}
    brand_map = {b.id: b for b in brands}

    return keywords, item_map, brand_map


def get_seen_item_ids(db: Session, brand_id: int) -> set:
    """
    Return the set of all item_ids ever seen for a given brand.
    Used to detect new SKUs — any item_id not in this set is new.
    """
    rows = (
        db.query(SearchResult.item_id)
        .filter(SearchResult.brand_id == brand_id)
        .distinct()
        .all()
    )
    return {r.item_id for r in rows}


def write_search_results(db: Session, rows: list[dict]):
    """Write a batch of search result rows to the database."""
    for row in rows:
        db.add(SearchResult(**row))
    db.commit()


def write_share_of_search(db: Session, keyword_id: int, scrape_date: date, results: list[dict], brand_map: dict):
    """
    Compute and write share_of_search rollup for a keyword on a given date.

    Groups page-1 results by brand, counting organic and sponsored slots.
    Unmatched brands (brand_id is None) are grouped under a single NULL row
    representing 'other'.
    """
    from collections import defaultdict

    counts: dict = defaultdict(lambda: {"organic": 0, "sponsored": 0})

    for r in results:
        key = r.get("brand_id")
        if r["position_type"] == "organic":
            counts[key]["organic"] += 1
        else:
            counts[key]["sponsored"] += 1

    for brand_id, c in counts.items():
        total = c["organic"] + c["sponsored"]
        db.add(ShareOfSearch(
            keyword_id=keyword_id,
            date=scrape_date,
            brand_id=brand_id,
            organic_count=c["organic"],
            sponsored_count=c["sponsored"],
            total_count=total,
        ))
    db.commit()


# ── Playwright extraction (adapted from demo 1) ───────────────────────────────

async def extract_products(page) -> list[dict]:
    """
    Extract all product cards from the current search results page.

    Uses page.evaluate() to run extraction as a single atomic JavaScript call,
    which avoids stale element handle errors caused by page shifts mid-iteration.
    """
    try:
        products = await page.evaluate("""() => {
            const results = [];

            // Try primary selector, fall back to item-stack children
            let items = Array.from(document.querySelectorAll('div[data-item-id]'));
            if (!items.length) {
                items = Array.from(document.querySelectorAll('[data-testid="item-stack"] > div'));
            }

            for (const item of items) {
                try {
                    const item_id = item.getAttribute('data-item-id') || '';

                    // Name
                    const nameEl = (
                        item.querySelector('[data-automation-id="product-title"]') ||
                        item.querySelector('[data-testid="product-title"]') ||
                        item.querySelector('span.w_iUH7') ||
                        item.querySelector('span[class*="lh-title"]')
                    );
                    if (!nameEl) continue;
                    const name = nameEl.innerText.trim();
                    if (!name) continue;

                    // Sponsored detection
                    const sponsoredEl = (
                        item.querySelector('[data-testid="ad-label"]') ||
                        item.querySelector('[data-testid="sponsored-label"]') ||
                        item.querySelector('span.sponsored-product-badge') ||
                        item.querySelector('[aria-label*="sponsored" i]') ||
                        item.querySelector('span[class*="sponsored" i]')
                    );
                    let listing_type = 'organic';
                    if (sponsoredEl) {
                        listing_type = 'sponsored';
                    } else if (/\\bSponsored\\b/.test(item.innerText)) {
                        listing_type = 'sponsored';
                    }

                    // Product URL
                    const linkEl = (
                        item.querySelector('a[link-identifier]') ||
                        item.querySelector('a[data-testid="product-title-link"]') ||
                        item.querySelector('a[href*="/ip/"]')
                    );
                    let product_url = '';
                    if (linkEl) {
                        const href = linkEl.getAttribute('href') || '';
                        product_url = href.startsWith('/') ? 'https://www.walmart.com' + href : href;
                    }

                    results.push({ name, item_id, listing_type, product_url });
                } catch(e) {
                    continue;
                }
            }
            return results;
        }""")
        return products or []
    except Exception as e:
        log.error("extract_products JS evaluate failed: %s", e)
        return []


async def scrape_keyword(
    page,
    keyword,
    item_map: dict,
    brand_map: dict,
    seen_ids_by_brand: dict,
    scrape_date: date,
    run_id: str,
    db: Session,
):
    """
    Scrape a single keyword search page and write results to the database.
    """
    search_url = f"https://www.walmart.com/search?q={keyword.keyword.replace(' ', '+')}"
    log.info("[%s] scraping → %s", keyword.keyword, search_url)

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(3, 5))

        # Bot detection check
        page_text = (await page.inner_text("body")).lower()
        if any(x in page_text for x in [
            "captcha", "access denied", "unusual traffic",
            "verify you are human", "blocked"
        ]):
            log.warning("[%s] bot detection triggered — skipping", keyword.keyword)
            return

        # Poll for products
        products = []
        for _ in range(12):
            await asyncio.sleep(1)
            products = await extract_products(page)
            if products:
                break

        if not products:
            log.error("[%s] no products found after 12s — possible block or layout change", keyword.keyword)
            return

        # Build URL index for fallback matching
        url_map = {}
        for item_id, product in item_map.items():
            if product.walmart_url:
                clean = product.walmart_url.rstrip("/").split("?")[0].lower()
                url_map[clean] = product

        rows = []
        overall_pos = sponsored_pos = organic_pos = 0

        for product in products:
            overall_pos += 1
            listing_type = product["listing_type"]
            if listing_type == "sponsored":
                sponsored_pos += 1
            else:
                organic_pos += 1

            item_id = product["item_id"]

            # Match against known products — item_id first, URL fallback
            matched_product = item_map.get(item_id)
            if not matched_product and product.get("product_url"):
                clean_url = product["product_url"].rstrip("/").split("?")[0].lower()
                matched_product = url_map.get(clean_url)

            brand_id = matched_product.brand_id if matched_product else None

            # New SKU detection — competitor brand item never seen before
            is_new_sku = False
            if brand_id is not None:
                brand = brand_map.get(brand_id)
                if brand and brand.type == "competitor" and brand.tracked:
                    seen = seen_ids_by_brand.setdefault(brand_id, set())
                    if item_id and item_id not in seen:
                        is_new_sku = True
                        seen.add(item_id)
                        log.info(
                            "[%s] NEW SKU detected — item_id=%s brand=%s name=%s",
                            keyword.keyword, item_id, brand.name, product["name"]
                        )

            rows.append({
                "keyword_id": keyword.id,
                "scraped_at": scrape_date,
                "position": overall_pos,
                "position_type": listing_type,
                "item_id": item_id,
                "brand_id": brand_id,
                "is_new_sku": is_new_sku,
            })

        # Write raw results
        write_search_results(db, rows)

        # Write SOS rollup
        write_share_of_search(db, keyword.id, scrape_date, rows, brand_map)

        log.info(
            "[%s] done — %d results | organic=%d sponsored=%d",
            keyword.keyword, len(rows), organic_pos, sponsored_pos,
        )

    except PlaywrightTimeout as e:
        log.error("[%s] TIMEOUT: %s", keyword.keyword, e)
    except Exception as e:
        log.error("[%s] FAILED: %s", keyword.keyword, e)


async def scrape_one_keyword(playwright, keyword, item_map, brand_map, seen_ids_by_brand, scrape_date, run_id, db):
    """Fresh browser per keyword — mirrors demo 1 anti-detection approach."""
    browser = await playwright.chromium.launch(
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    try:
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        page = await context.new_page()
        await scrape_keyword(
            page, keyword, item_map, brand_map,
            seen_ids_by_brand, scrape_date, run_id, db
        )
    finally:
        await browser.close()


# ── Entry point ───────────────────────────────────────────────────────────────

async def run(db: Session = None):
    """
    Main scraper entry point. Can be called directly or from FastAPI trigger.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        run_id = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
        scrape_date = date.today()
        log.info("Daily scraper starting — run_id=%s date=%s", run_id, scrape_date)

        keywords, item_map, brand_map = load_config(db)

        if not keywords:
            log.warning("No active keywords found — nothing to scrape.")
            return

        if not item_map:
            log.warning("No active products found — SOS brand matching will be limited.")

        log.info("Loaded %d keywords, %d products, %d brands",
                 len(keywords), len(item_map), len(brand_map))

        # Pre-load seen item IDs per competitor brand for new SKU detection
        seen_ids_by_brand = {}
        for brand in brand_map.values():
            if brand.type == "competitor" and brand.tracked:
                seen_ids_by_brand[brand.id] = get_seen_item_ids(db, brand.id)

        async with async_playwright() as p:
            for i, keyword in enumerate(keywords):
                await scrape_one_keyword(
                    p, keyword, item_map, brand_map,
                    seen_ids_by_brand, scrape_date, run_id, db
                )
                if i < len(keywords) - 1:
                    delay = random.uniform(15, 25)
                    log.info("Waiting %.1fs before next keyword...", delay)
                    await asyncio.sleep(delay)

        log.info("Daily scraper complete — run_id=%s", run_id)

    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    asyncio.run(run())
