"""
Synthetic Data Generator — WM Dot Com Competitive Intelligence
Generates 12 weeks of plausible historical data for dashboard demo purposes.

Run once after configuring brands, products, and keywords in the UI:
    python3 scripts/synthetic_data.py

Populates:
  - search_results      (daily, 12 weeks back)
  - share_of_search     (daily rollup, 12 weeks back)
  - product_snapshots   (weekly, 12 weeks back)
  - content_snapshots   (weekly, 12 weeks back)
  - review_delta        (weekly, 12 weeks back)

Data is designed to tell a plausible story:
  - Your brand ranks well for branded keywords, lower for generic
  - SOS shows realistic brand distribution across page 1
  - Prices stable with minor fluctuations
  - Reviews trend upward over time
  - Occasional content changes for competitor products
"""

import random
import json
from datetime import date, timedelta
from collections import defaultdict

from app.core.database import SessionLocal
from app.models import (
    Brand, Product, Keyword,
    SearchResult, ShareOfSearch,
    ProductSnapshot, ContentSnapshot, ContentChange, ReviewDelta,
)

import logging
log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ── Config ────────────────────────────────────────────────────────────────────

WEEKS_BACK = 12
TODAY = date.today()
START_DATE = TODAY - timedelta(weeks=WEEKS_BACK)

# Page 1 has ~20 organic + ~8 sponsored slots typically
PAGE1_ORGANIC_SLOTS  = 20
PAGE1_SPONSORED_SLOTS = 8
PAGE1_TOTAL = PAGE1_ORGANIC_SLOTS + PAGE1_SPONSORED_SLOTS


# ── Helpers ───────────────────────────────────────────────────────────────────

def date_range(start: date, end: date):
    """Yield every date from start to end inclusive."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def weekly_dates(start: date, end: date):
    """Yield one date per week from start to end."""
    current = start
    while current <= end:
        yield current
        current += timedelta(weeks=1)


def weeks_since_start(d: date) -> int:
    return (d - START_DATE).days // 7


# ── Search results + SOS generation ──────────────────────────────────────────

def generate_daily_search_data(db, keywords, products, brands):
    """
    Generate search_results and share_of_search for every keyword for every day.

    Strategy:
    - My brand products rank well for branded keywords (positions 1-8)
    - My brand products rank lower for generic keywords (positions 5-18)
    - Competitor products fill remaining slots
    - Untracked brands fill the rest of page 1
    - Small random variation day to day
    """
    my_brands     = [b for b in brands if b.type == "mine"]
    comp_brands   = [b for b in brands if b.type == "competitor" and b.tracked]
    my_products   = [p for p in products if any(b.id == p.brand_id for b in my_brands)]
    comp_products = [p for p in products if any(b.id == p.brand_id for b in comp_brands)]

    # Determine if keyword is "branded" (contains a tracked brand name)
    brand_names = [b.name.lower() for b in my_brands + comp_brands]

    def is_branded(keyword):
        kw = keyword.keyword.lower()
        return any(name in kw for name in brand_names)

    log.info("Generating daily search data for %d keywords × %d days...",
             len(keywords), (TODAY - START_DATE).days + 1)

    batch_size = 500
    result_batch = []
    sos_batch = []

    for kw in keywords:
        branded = is_branded(kw)

        for day in date_range(START_DATE, TODAY):
            week_num = weeks_since_start(day)

            # Build a page-1 result set for this keyword on this day
            page1 = []
            used_positions = set()

            # Place my products
            for prod in my_products:
                if branded:
                    # Good rank for branded keywords — positions 1-8, with some variance
                    base_pos = random.randint(1, 8)
                else:
                    # Lower rank for generic keywords
                    base_pos = random.randint(5, 18)

                # Small day-to-day variance
                pos = max(1, base_pos + random.randint(-2, 2))
                while pos in used_positions and pos < PAGE1_TOTAL:
                    pos += 1
                if pos <= PAGE1_TOTAL:
                    used_positions.add(pos)
                    # My products are usually organic but occasionally sponsored
                    pos_type = "sponsored" if random.random() < 0.1 else "organic"
                    page1.append({
                        "keyword_id": kw.id,
                        "scraped_at": day,
                        "position": pos,
                        "position_type": pos_type,
                        "item_id": prod.walmart_item_id,
                        "brand_id": prod.brand_id,
                        "is_new_sku": False,
                    })

            # Place competitor products
            for prod in comp_products:
                base_pos = random.randint(3, 15)
                pos = max(1, base_pos + random.randint(-2, 2))
                while pos in used_positions and pos < PAGE1_TOTAL:
                    pos += 1
                if pos <= PAGE1_TOTAL:
                    used_positions.add(pos)
                    pos_type = "sponsored" if random.random() < 0.25 else "organic"
                    page1.append({
                        "keyword_id": kw.id,
                        "scraped_at": day,
                        "position": pos,
                        "position_type": pos_type,
                        "item_id": prod.walmart_item_id,
                        "brand_id": prod.brand_id,
                        "is_new_sku": False,
                    })

            # Fill remaining page 1 slots with "other" (untracked brands)
            other_items = [
                f"OTHER_{kw.id}_{i}" for i in range(1, 20)
            ]
            random.shuffle(other_items)
            other_idx = 0
            for pos in range(1, PAGE1_TOTAL + 1):
                if pos not in used_positions and other_idx < len(other_items):
                    pos_type = "sponsored" if pos <= PAGE1_SPONSORED_SLOTS and random.random() < 0.5 else "organic"
                    page1.append({
                        "keyword_id": kw.id,
                        "scraped_at": day,
                        "position": pos,
                        "position_type": pos_type,
                        "item_id": other_items[other_idx],
                        "brand_id": None,
                        "is_new_sku": False,
                    })
                    other_idx += 1

            result_batch.extend(page1)

            # Compute SOS rollup
            sos_counts = defaultdict(lambda: {"organic": 0, "sponsored": 0})
            for row in page1:
                key = row["brand_id"]
                sos_counts[key][row["position_type"]] += 1

            for brand_id, counts in sos_counts.items():
                sos_batch.append({
                    "keyword_id": kw.id,
                    "date": day,
                    "brand_id": brand_id,
                    "organic_count": counts["organic"],
                    "sponsored_count": counts["sponsored"],
                    "total_count": counts["organic"] + counts["sponsored"],
                })

            # Write in batches to avoid memory issues
            if len(result_batch) >= batch_size:
                for row in result_batch:
                    db.add(SearchResult(**row))
                for row in sos_batch:
                    db.add(ShareOfSearch(**row))
                db.commit()
                result_batch = []
                sos_batch = []

    # Write remaining
    for row in result_batch:
        db.add(SearchResult(**row))
    for row in sos_batch:
        db.add(ShareOfSearch(**row))
    db.commit()
    log.info("Daily search data written.")


# ── Weekly product data generation ───────────────────────────────────────────

def generate_weekly_product_data(db, products, brands):
    """
    Generate product_snapshots, content_snapshots, review_delta for each product.

    Strategy:
    - Prices stable with ±5% weekly variance
    - Review counts trend upward (~5-15 new reviews per week)
    - Ratings stable around 4.2-4.7 with tiny variance
    - Content changes for competitor products every 3-6 weeks
    """
    brand_map = {b.id: b for b in brands}

    # Starting values per product
    product_state = {}
    for prod in products:
        brand = brand_map.get(prod.brand_id)
        is_mine = brand and brand.type == "mine"
        product_state[prod.id] = {
            "price":        round(random.uniform(3.50, 8.99), 2),
            "review_count": random.randint(150, 800),
            "avg_rating":   round(random.uniform(4.2, 4.7), 1),
            "title":        f"{prod.name}",
            "bullets":      [
                f"Feature 1 for {prod.name[:30]}",
                f"Feature 2 for {prod.name[:30]}",
                f"Feature 3 for {prod.name[:30]}",
            ],
            "image_count":  random.randint(4, 8),
            "has_aplus":          is_mine,
            "has_brand_story":    is_mine,
            "has_comparison_chart": False,
            "has_video":          random.random() < 0.3,
            "last_content_change": None,
        }

    log.info("Generating weekly product data for %d products × %d weeks...",
             len(products), WEEKS_BACK)

    prev_snapshots = {prod.id: None for prod in products}

    for week_date in weekly_dates(START_DATE, TODAY):
        for prod in products:
            state = product_state[prod.id]
            brand = brand_map.get(prod.brand_id)

            # Price — small weekly variance
            price_change = random.uniform(-0.25, 0.25)
            state["price"] = round(max(1.99, state["price"] + price_change), 2)

            # Reviews — trend upward
            new_reviews = random.randint(3, 15)
            state["review_count"] += new_reviews

            # Rating — tiny variance
            rating_change = round(random.uniform(-0.05, 0.05), 2)
            state["avg_rating"] = round(
                max(3.5, min(5.0, state["avg_rating"] + rating_change)), 1
            )

            # Write product snapshot
            snap = ProductSnapshot(
                product_id=prod.id,
                scraped_at=week_date,
                price=state["price"],
                review_count=state["review_count"],
                avg_rating=state["avg_rating"],
            )
            db.add(snap)

            # Write review delta
            prev = prev_snapshots[prod.id]
            count_delta  = new_reviews if prev else None
            rating_delta = rating_change if prev else None
            db.add(ReviewDelta(
                product_id=prod.id,
                date=week_date,
                review_count=state["review_count"],
                review_count_delta=count_delta,
                avg_rating=state["avg_rating"],
                avg_rating_delta=rating_delta,
            ))

            # Content changes — simulate competitor content updates every 3-6 weeks
            content_changed = False
            if brand and brand.type == "competitor":
                weeks_since_change = (
                    (week_date - state["last_content_change"]).days // 7
                    if state["last_content_change"] else WEEKS_BACK
                )
                if weeks_since_change >= random.randint(3, 6):
                    # Simulate a content change
                    change_type = random.choice(["title", "bullets", "image_count", "has_video"])
                    if change_type == "title":
                        old_title = state["title"]
                        state["title"] = f"{prod.name} — Updated"
                        if prev_snapshots[prod.id]:
                            db.add(ContentChange(
                                product_id=prod.id,
                                detected_at=week_date,
                                field_changed="title",
                                previous_value=old_title,
                                new_value=state["title"],
                            ))
                    elif change_type == "bullets":
                        old_bullets = state["bullets"].copy()
                        state["bullets"] = [
                            f"Updated feature 1 for {prod.name[:25]}",
                            f"Updated feature 2 for {prod.name[:25]}",
                            f"New feature added week {weeks_since_start(week_date)}",
                        ]
                        if prev_snapshots[prod.id]:
                            db.add(ContentChange(
                                product_id=prod.id,
                                detected_at=week_date,
                                field_changed="bullets",
                                previous_value=json.dumps(old_bullets),
                                new_value=json.dumps(state["bullets"]),
                            ))
                    elif change_type == "image_count":
                        old_count = state["image_count"]
                        state["image_count"] = old_count + random.choice([-1, 1, 2])
                        state["image_count"] = max(1, state["image_count"])
                        if prev_snapshots[prod.id]:
                            db.add(ContentChange(
                                product_id=prod.id,
                                detected_at=week_date,
                                field_changed="image_count",
                                previous_value=str(old_count),
                                new_value=str(state["image_count"]),
                            ))
                    elif change_type == "has_video":
                        old_val = state["has_video"]
                        state["has_video"] = not old_val
                        if prev_snapshots[prod.id]:
                            db.add(ContentChange(
                                product_id=prod.id,
                                detected_at=week_date,
                                field_changed="has_video",
                                previous_value=str(old_val),
                                new_value=str(state["has_video"]),
                            ))
                    state["last_content_change"] = week_date
                    content_changed = True

            # Write content snapshot
            images = [
                {"url": f"https://i5.walmartimages.com/fake/{prod.walmart_item_id}_{j}.jpg",
                 "width": random.choice([2000, 2000, 1500, 2400]),
                 "height": random.choice([2000, 2000, 1500, 2400])}
                for j in range(state["image_count"])
            ]
            content_snap = ContentSnapshot(
                product_id=prod.id,
                scraped_at=week_date,
                title=state["title"],
                bullets=state["bullets"],
                image_count=state["image_count"],
                images=images,
                has_aplus=state["has_aplus"],
                has_brand_story=state["has_brand_story"],
                has_comparison_chart=state["has_comparison_chart"],
                has_video=state["has_video"],
                has_enhanced_content=(
                    state["has_aplus"] or state["has_brand_story"] or
                    state["has_comparison_chart"] or state["has_video"]
                ),
            )
            db.add(content_snap)
            prev_snapshots[prod.id] = content_snap

        db.commit()

    log.info("Weekly product data written.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    db = SessionLocal()
    try:
        # Load config from DB
        keywords = db.query(Keyword).filter(Keyword.active == True).all()
        products = db.query(Product).filter(Product.active == True).all()
        brands   = db.query(Brand).all()

        if not keywords:
            log.error("No active keywords found. Add keywords in the config UI first.")
            return
        if not products:
            log.error("No active products found. Add products in the config UI first.")
            return

        log.info("Loaded %d keywords, %d products, %d brands",
                 len(keywords), len(products), len(brands))
        log.info("Generating %d weeks of synthetic data from %s to %s",
                 WEEKS_BACK, START_DATE, TODAY)

        # Check for existing data
        existing = db.query(SearchResult).count()
        if existing > 0:
            log.warning(
                "%d search_results rows already exist. "
                "Run will ADD to existing data, not replace it. "
                "To start fresh, truncate the tables first.",
                existing
            )

        generate_daily_search_data(db, keywords, products, brands)
        generate_weekly_product_data(db, products, brands)

        # Summary
        log.info("=" * 50)
        log.info("Synthetic data generation complete.")
        log.info("  search_results:   %d rows", db.query(SearchResult).count())
        log.info("  share_of_search:  %d rows", db.query(ShareOfSearch).count())
        log.info("  product_snapshots:%d rows", db.query(ProductSnapshot).count())
        log.info("  content_snapshots:%d rows", db.query(ContentSnapshot).count())
        log.info("  review_delta:     %d rows", db.query(ReviewDelta).count())
        log.info("=" * 50)

    finally:
        db.close()


if __name__ == "__main__":
    main()
