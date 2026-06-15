"""
Weekly product scraper — WM Dot Com Competitive Intelligence
Runs once per week via cron (or manually triggered).

For each active product (all brands):
  - Price, review count, avg rating → product_snapshots + review_delta

For all products (yours + competitors):
  - Title, bullets, images, below-fold content → content_snapshots
  - Diffs against previous snapshot → content_changes

Uses __NEXT_DATA__ JSON blob extraction from demo 1 — far more reliable
than DOM scraping. Fresh browser per product to avoid bot detection.
"""

import asyncio
import io
import json
import random
import re
from datetime import date, datetime
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    Brand, Product,
    ProductSnapshot, ContentSnapshot, ContentChange, ReviewDelta,
)

import logging
log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

try:
    import requests as _requests
    from PIL import Image as _PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False
    log.warning("Pillow/requests not installed — image resolution check disabled")

CST = ZoneInfo("America/Chicago")


# ── Image resolution helper (from demo 1) ────────────────────────────────────

def fetch_image_dimensions(image_urls: list, timeout: int = 12) -> list:
    """
    Download each image URL (CDN resize params stripped) and return pixel
    dimensions via Pillow. Caps at 8 images to limit latency.
    """
    if not _HAS_PIL or not image_urls:
        return []

    session = _requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    })

    results = []
    for url in image_urls[:8]:
        if not url:
            continue
        try:
            parsed    = urlparse(url)
            clean_url = urlunparse(parsed._replace(query=""))
            r = session.get(clean_url, timeout=timeout)
            r.raise_for_status()
            img  = _PILImage.open(io.BytesIO(r.content))
            w, h = img.size
            results.append({"url": url, "width": w, "height": h})
        except Exception as e:
            results.append({"url": url, "error": str(e)[:120]})

    session.close()
    return results


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_previous_content_snapshot(db: Session, product_id: int) -> ContentSnapshot | None:
    """Get the most recent content snapshot for a product."""
    return (
        db.query(ContentSnapshot)
        .filter(ContentSnapshot.product_id == product_id)
        .order_by(ContentSnapshot.scraped_at.desc())
        .first()
    )


def get_previous_product_snapshot(db: Session, product_id: int) -> ProductSnapshot | None:
    """Get the most recent product snapshot for a product."""
    return (
        db.query(ProductSnapshot)
        .filter(ProductSnapshot.product_id == product_id)
        .order_by(ProductSnapshot.scraped_at.desc())
        .first()
    )


def write_product_snapshot(db: Session, product_id: int, scrape_date: date, data: dict):
    """Write a product snapshot row."""
    db.add(ProductSnapshot(
        product_id=product_id,
        scraped_at=scrape_date,
        price=data.get("price"),
        review_count=data.get("review_count"),
        avg_rating=data.get("avg_rating"),
    ))
    db.commit()


def write_content_snapshot(db: Session, product_id: int, scrape_date: date, data: dict):
    """Write a content snapshot row."""
    db.add(ContentSnapshot(
        product_id=product_id,
        scraped_at=scrape_date,
        title=data.get("title"),
        bullets=data.get("bullets"),
        image_count=data.get("image_count"),
        images=data.get("images"),
        has_aplus=data.get("has_aplus"),
        has_brand_story=data.get("has_brand_story"),
        has_comparison_chart=data.get("has_comparison_chart"),
        has_video=data.get("has_video"),
        has_enhanced_content=data.get("has_enhanced_content"),
    ))
    db.commit()


def write_content_changes(db: Session, product_id: int, scrape_date: date, prev: ContentSnapshot, curr: dict):
    """
    Diff current scraped data against previous snapshot.
    Write a content_changes row for each field that changed.
    """
    fields_to_diff = [
        ("title",                "title"),
        ("has_aplus",            "has_aplus"),
        ("has_brand_story",      "has_brand_story"),
        ("has_comparison_chart", "has_comparison_chart"),
        ("has_video",            "has_video"),
        ("has_enhanced_content", "has_enhanced_content"),
        ("image_count",          "image_count"),
    ]

    changes = []

    for field, curr_key in fields_to_diff:
        prev_val = getattr(prev, field, None)
        curr_val = curr.get(curr_key)
        if prev_val != curr_val:
            changes.append(ContentChange(
                product_id=product_id,
                detected_at=scrape_date,
                field_changed=field,
                previous_value=str(prev_val) if prev_val is not None else None,
                new_value=str(curr_val) if curr_val is not None else None,
            ))

    # Diff bullets as a whole (too granular to diff line by line)
    prev_bullets = json.dumps(prev.bullets or [])
    curr_bullets = json.dumps(curr.get("bullets") or [])
    if prev_bullets != curr_bullets:
        changes.append(ContentChange(
            product_id=product_id,
            detected_at=scrape_date,
            field_changed="bullets",
            previous_value=prev_bullets,
            new_value=curr_bullets,
        ))

    # Diff image array (flag any change in image set)
    prev_images = json.dumps([(i.get("url","")) for i in (prev.images or [])])
    curr_images = json.dumps([(i.get("url","")) for i in (curr.get("images") or [])])
    if prev_images != curr_images:
        changes.append(ContentChange(
            product_id=product_id,
            detected_at=scrape_date,
            field_changed="images",
            previous_value=prev_images,
            new_value=curr_images,
        ))

    if changes:
        for change in changes:
            db.add(change)
        db.commit()
        log.info("[product_id=%d] %d content change(s) detected", product_id, len(changes))


def write_review_delta(db: Session, product_id: int, scrape_date: date, curr: dict, prev: ProductSnapshot | None):
    """Compute and write review delta vs previous snapshot."""
    curr_count  = curr.get("review_count")
    curr_rating = curr.get("avg_rating")

    count_delta  = None
    rating_delta = None

    if prev is not None:
        if curr_count is not None and prev.review_count is not None:
            count_delta = curr_count - prev.review_count
        if curr_rating is not None and prev.avg_rating is not None:
            rating_delta = float(curr_rating) - float(prev.avg_rating)

    db.add(ReviewDelta(
        product_id=product_id,
        date=scrape_date,
        review_count=curr_count,
        review_count_delta=count_delta,
        avg_rating=curr_rating,
        avg_rating_delta=rating_delta,
    ))
    db.commit()


# ── PDP scraper (adapted from demo 1) ────────────────────────────────────────

async def scrape_product_page(page, product) -> dict:
    """
    Navigate to a Walmart PDP and extract content from __NEXT_DATA__.
    Adapted from demo 1's pdp_scraper.py — same extraction logic,
    adapted for DB-driven product list instead of hardcoded TARGET_ITEMS.

    Returns a structured dict with all extracted fields.
    """
    url = product.walmart_url or f"https://www.walmart.com/ip/{product.walmart_item_id}"
    log.info("[%s] scraping PDP → %s", product.name, url[:72])

    result = {
        "product_id":           product.id,
        "title":                None,
        "bullets":              [],
        "image_count":          0,
        "images":               [],   # [{url, width, height}]
        "has_aplus":            False,
        "has_brand_story":      False,
        "has_comparison_chart": False,
        "has_video":            False,
        "has_enhanced_content": False,
        "price":                None,
        "review_count":         None,
        "avg_rating":           None,
        "error":                None,
    }

    try:
        # Warm up session on walmart.com homepage before hitting PDP directly.
        # Going cold to a PDP URL triggers bot detection — this mimics how a
        # real shopper arrives (browse homepage first, then navigate to product).
        log.debug("[%s] warming up session on walmart.com...", product.name)
        await page.goto("https://www.walmart.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(4, 7))

        # Check for block on homepage
        home_text = (await page.inner_text("body")).lower()
        if any(x in home_text for x in [
            "captcha", "access denied", "unusual traffic",
            "verify you are human", "blocked", "robot"
        ]):
            result["error"] = "BLOCKED"
            log.warning("[%s] blocked on homepage warmup", product.name)
            return result

        # Now navigate to the product page
        await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        await asyncio.sleep(random.uniform(3, 5))

        # Bot detection check on PDP
        body_text = (await page.inner_text("body")).lower()
        if any(x in body_text for x in [
            "captcha", "access denied", "unusual traffic",
            "verify you are human", "blocked", "robot"
        ]):
            result["error"] = "BLOCKED"
            log.warning("[%s] blocked by bot detection", product.name)
            return result

        # Extract __NEXT_DATA__ — server-side rendered, always present
        nd_raw = await page.evaluate(
            "() => document.getElementById('__NEXT_DATA__')?.textContent"
        )
        if not nd_raw:
            result["error"] = "NO_NEXT_DATA"
            log.warning("[%s] __NEXT_DATA__ not found", product.name)
            return result

        nd = json.loads(nd_raw)
        prod = nd["props"]["pageProps"]["initialData"]["data"]["product"]

        # Title
        result["title"] = prod.get("name") or None

        # Price — pull from priceInfo
        try:
            price_info = prod.get("priceInfo", {})
            current_price = (
                price_info.get("currentPrice", {}).get("price")
                or price_info.get("wasPrice", {}).get("price")
            )
            result["price"] = float(current_price) if current_price else None
        except Exception:
            result["price"] = None

        # Ratings & reviews
        result["avg_rating"]   = prod.get("averageRating")
        result["review_count"] = prod.get("numberOfReviews")

        # Bullets — 4 fallback strategies from demo 1
        bullets = []

        kf = prod.get("keyFeatures")
        if isinstance(kf, list):
            bullets = [b for b in kf if isinstance(b, str) and b.strip()]

        if not bullets:
            hl = prod.get("highlights")
            if isinstance(hl, list):
                bullets = [b for b in hl if isinstance(b, str) and b.strip()]

        if not bullets and result.get("short_description"):
            lines = [ln.strip().lstrip("•·-–—*").strip()
                     for ln in result["short_description"].splitlines()
                     if ln.strip() and len(ln.strip()) < 250]
            short_lines = [ln for ln in lines if len(ln) < 120]
            if len(short_lines) >= 3 and len(short_lines) / max(len(lines), 1) > 0.6:
                bullets = short_lines

        if not bullets:
            try:
                for _ in range(5):
                    await page.evaluate("window.scrollBy(0, 500)")
                    await asyncio.sleep(1.5)
                dom_bullets = await page.evaluate("""
                    () => {
                        const headings = [...document.querySelectorAll('h2,h3,h4,span,div,p')];
                        const kif = headings.find(el =>
                            el.textContent.trim() === 'Key item features'
                        );
                        if (!kif) return [];
                        let container = kif;
                        for (let i = 0; i < 6; i++) {
                            container = container.parentElement;
                            if (!container) break;
                            const lis = container.querySelectorAll('li');
                            if (lis.length > 0)
                                return [...lis].map(li => li.textContent.trim()).filter(t => t.length > 2);
                        }
                        return [];
                    }
                """)
                if dom_bullets:
                    bullets = dom_bullets
            except Exception:
                pass

        result["bullets"] = bullets

        # Images
        image_info = prod.get("imageInfo", {})
        all_images = image_info.get("allImages", [])
        image_urls = [img.get("url", "") for img in all_images if img.get("url")]
        result["image_count"] = len(all_images)

        # Fetch image dimensions via Pillow
        if image_urls and _HAS_PIL:
            dims = fetch_image_dimensions(image_urls)
            result["images"] = dims
        else:
            result["images"] = [{"url": u} for u in image_urls]

        # BTF module detection — from demo 1
        try:
            cl = nd["props"]["pageProps"]["initialData"]["data"].get("contentLayout", {})
            btf_modules  = cl.get("modules", []) if cl else []
            module_types = [m.get("type", "") for m in btf_modules if m.get("type")]

            result["has_brand_story"]      = "MarketingContentBtf" in module_types
            result["has_comparison_chart"] = "ComparisonChart"      in module_types

            _VIDEO_MODULES = {
                "VideoModule", "WalmartVideo", "IdmlVideo",
                "ProductVideo", "VideoContent", "VideoPlayer",
            }
            has_video_module = bool(_VIDEO_MODULES & set(module_types))
            has_video_media  = False
            try:
                mc = prod.get("mediaContent") or {}
                if mc.get("videos") or prod.get("videos"):
                    has_video_media = True
                elif any(
                    img.get("type", "").lower() == "video"
                    for img in image_info.get("allImages", [])
                ):
                    has_video_media = True
            except Exception:
                pass
            result["has_video"] = has_video_module or has_video_media

            # A+ detection — Walmart doesn't have a single reliable flag for this.
            # Best proxy: presence of MarketingContentBtf or RichMediaModule modules.
            _APLUS_MODULES = {"MarketingContentBtf", "RichMediaModule", "BrandAmplifier"}
            result["has_aplus"] = bool(_APLUS_MODULES & set(module_types))

            result["has_enhanced_content"] = (
                result["has_brand_story"]
                or result["has_comparison_chart"]
                or result["has_video"]
                or result["has_aplus"]
            )
        except Exception as e:
            log.warning("[%s] BTF detection skipped: %s", product.name, e)

        log.info(
            "[%s] done — title=%s price=%s rating=%s reviews=%s bullets=%d imgs=%d",
            product.name,
            "yes" if result["title"] else "no",
            result["price"],
            result["avg_rating"],
            result["review_count"],
            len(result["bullets"]),
            result["image_count"],
        )

    except PlaywrightTimeout:
        result["error"] = "TIMEOUT"
        log.error("[%s] TIMEOUT", product.name)
    except KeyError as e:
        result["error"] = f"KEY_ERROR:{e}"
        log.error("[%s] key error in __NEXT_DATA__: %s", product.name, e)
    except Exception as e:
        result["error"] = str(e)
        log.exception("[%s] unhandled error", product.name)

    return result


async def scrape_one_product(playwright, product) -> dict:
    """Fresh browser per product — same anti-detection pattern as demo 1."""
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
        return await scrape_product_page(page, product)
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
        scrape_date = date.today()
        run_id = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
        log.info("Weekly scraper starting — run_id=%s date=%s", run_id, scrape_date)

        products = db.query(Product).filter(Product.active == True).all()
        if not products:
            log.warning("No active products found — nothing to scrape.")
            return

        log.info("Loaded %d products", len(products))

        async with async_playwright() as p:
            for i, product in enumerate(products):
                result = await scrape_one_product(p, product)

                # Skip writing if blocked — don't overwrite good prior data
                if result.get("error") in ("BLOCKED", "TIMEOUT", "NO_NEXT_DATA"):
                    log.warning("[%s] skipping DB write due to error: %s",
                                product.name, result["error"])
                else:
                    # Get previous snapshots for diffing
                    prev_product_snap  = get_previous_product_snapshot(db, product.id)
                    prev_content_snap  = get_previous_content_snapshot(db, product.id)

                    # Write product snapshot (price, reviews, rating — all products)
                    write_product_snapshot(db, product.id, scrape_date, result)

                    # Write review delta
                    write_review_delta(db, product.id, scrape_date, result, prev_product_snap)

                    # Write content snapshot (all products)
                    write_content_snapshot(db, product.id, scrape_date, result)

                    # Write content changes if we have a previous snapshot to diff against
                    if prev_content_snap:
                        write_content_changes(db, product.id, scrape_date, prev_content_snap, result)

                if i < len(products) - 1:
                    delay = random.uniform(25, 40)
                    log.info("Waiting %.1fs before next product...", delay)
                    await asyncio.sleep(delay)

        log.info("Weekly scraper complete — run_id=%s", run_id)

    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    asyncio.run(run())
