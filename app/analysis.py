"""
Analysis layer — WM Dot Com Competitive Intelligence

Query functions that read scraped data and produce dashboard-ready aggregations.
All functions accept a group_id to filter data to the tracking group's
brands/products/keywords, and a period string ('wow', 'mom', 'qoq', 'yoy')
to set the date window.

Period windows (rolling, ending today):
  wow — 7 days
  mom — 30 days
  qoq — 90 days
  yoy — 365 days

Trend charts: return daily/weekly data points over the full window.
Stat cards: return current period value + delta vs prior period.
"""

from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models import (
    TrackingGroup, Brand, Product, Keyword,
    SearchResult, ShareOfSearch,
    ProductSnapshot, ContentChange, ReviewDelta,
    group_brands, group_products, group_keywords,
)


# ── Period helpers ────────────────────────────────────────────────────────────

PERIOD_DAYS = {
    'wow':  7,
    'mom':  30,
    'qoq':  90,
    'yoy':  365,
}

def get_date_range(period: str) -> tuple[date, date]:
    """Return (start_date, end_date) for the current period window."""
    days = PERIOD_DAYS.get(period, 7)
    end   = date.today()
    start = end - timedelta(days=days)
    return start, end

def get_prior_date_range(period: str) -> tuple[date, date]:
    """Return (start_date, end_date) for the prior period window (for deltas)."""
    days = PERIOD_DAYS.get(period, 7)
    end   = date.today() - timedelta(days=days)
    start = end - timedelta(days=days)
    return start, end


# ── Group membership helpers ──────────────────────────────────────────────────

def get_group_keyword_ids(db: Session, group_id: int) -> list[int]:
    group = db.query(TrackingGroup).get(group_id)
    return [k.id for k in group.keywords] if group else []

def get_group_product_ids(db: Session, group_id: int) -> list[int]:
    group = db.query(TrackingGroup).get(group_id)
    return [p.id for p in group.products] if group else []

def get_group_brand_ids(db: Session, group_id: int) -> list[int]:
    group = db.query(TrackingGroup).get(group_id)
    return [b.id for b in group.brands] if group else []

def get_my_product_ids(db: Session, group_id: int) -> list[int]:
    """Return product IDs for 'mine' brand products in this group."""
    group = db.query(TrackingGroup).get(group_id)
    if not group:
        return []
    return [
        p.id for p in group.products
        if db.query(Brand).get(p.brand_id) and
           db.query(Brand).get(p.brand_id).type == 'mine'
    ]


# ── Search Rank ───────────────────────────────────────────────────────────────

def get_search_rank_trend(db: Session, group_id: int, keyword_id: int, period: str) -> dict:
    """
    For a specific keyword in a group, return daily search rank positions
    for all 'my' products over the period window.

    Returns:
        {
          "keyword": "tabasco",
          "products": [
            {
              "product_id": 1,
              "product_name": "Tabasco Original 5oz",
              "dates": ["2026-06-01", ...],
              "positions": [3, 4, 2, ...]   # overall position each day
            },
            ...
          ]
        }
    """
    start, end = get_date_range(period)
    my_product_ids = get_my_product_ids(db, group_id)

    keyword = db.query(Keyword).get(keyword_id)
    if not keyword:
        return {}

    # Get all products in this group with their walmart_item_ids
    group = db.query(TrackingGroup).get(group_id)
    my_products = [p for p in group.products if p.id in my_product_ids]

    result = {
        "keyword": keyword.keyword,
        "products": []
    }

    for product in my_products:
        rows = (
            db.query(SearchResult.scraped_at, func.min(SearchResult.position).label("position"))
            .filter(
                SearchResult.keyword_id == keyword_id,
                SearchResult.item_id == product.walmart_item_id,
                SearchResult.scraped_at >= start,
                SearchResult.scraped_at <= end,
            )
            .group_by(SearchResult.scraped_at)
            .order_by(SearchResult.scraped_at)
            .all()
        )

        result["products"].append({
            "product_id":   product.id,
            "product_name": product.name,
            "dates":        [str(r.scraped_at) for r in rows],
            "positions":    [r.position for r in rows],
        })

    return result


# ── Share of Search ───────────────────────────────────────────────────────────

def get_share_of_search_trend(db: Session, group_id: int, keyword_id: int, period: str) -> dict:
    """
    For a specific keyword, return daily SOS breakdown by brand over the period.

    Returns:
        {
          "keyword": "tabasco",
          "dates": ["2026-06-01", ...],
          "brands": [
            {
              "brand_id": 1,
              "brand_name": "Tabasco",
              "type": "mine",
              "organic":   [5, 4, 6, ...],
              "sponsored": [2, 3, 1, ...],
              "total":     [7, 7, 7, ...]
            },
            ...
            {
              "brand_id": null,
              "brand_name": "Other",
              "organic":   [...],
              "sponsored": [...],
              "total":     [...]
            }
          ]
        }
    """
    start, end = get_date_range(period)
    group_brand_ids = get_group_brand_ids(db, group_id)

    keyword = db.query(Keyword).get(keyword_id)
    if not keyword:
        return {}

    rows = (
        db.query(ShareOfSearch)
        .filter(
            ShareOfSearch.keyword_id == keyword_id,
            ShareOfSearch.date >= start,
            ShareOfSearch.date <= end,
        )
        .order_by(ShareOfSearch.date)
        .all()
    )

    # Collect all dates
    all_dates = sorted(set(str(r.date) for r in rows))

    # Build per-brand, per-date lookup
    # key: (brand_id or None) → date → {organic, sponsored, total}
    brand_date_data: dict = defaultdict(lambda: defaultdict(lambda: {"organic": 0, "sponsored": 0, "total": 0}))
    for r in rows:
        key = r.brand_id
        brand_date_data[key][str(r.date)]["organic"]   += r.organic_count
        brand_date_data[key][str(r.date)]["sponsored"] += r.sponsored_count
        brand_date_data[key][str(r.date)]["total"]     += r.total_count

    # Build brand list — group brands first, then "other" (None)
    brands_out = []
    brand_map  = {b.id: b for b in db.query(Brand).filter(Brand.id.in_(group_brand_ids)).all()}

    for brand_id in list(group_brand_ids) + [None]:
        if brand_id is not None and brand_id not in brand_date_data and brand_id not in [r.brand_id for r in rows]:
            continue
        if brand_id is None and None not in brand_date_data:
            continue

        brand     = brand_map.get(brand_id)
        date_data = brand_date_data.get(brand_id, {})

        brands_out.append({
            "brand_id":   brand_id,
            "brand_name": brand.name if brand else "Other",
            "type":       brand.type if brand else "other",
            "organic":    [date_data.get(d, {}).get("organic", 0)   for d in all_dates],
            "sponsored":  [date_data.get(d, {}).get("sponsored", 0) for d in all_dates],
            "total":      [date_data.get(d, {}).get("total", 0)     for d in all_dates],
        })

    return {
        "keyword": keyword.keyword,
        "dates":   all_dates,
        "brands":  brands_out,
    }


# ── Pricing ───────────────────────────────────────────────────────────────────

def get_pricing_trend(db: Session, group_id: int, period: str) -> dict:
    """
    Return weekly price per product over the period window.

    Returns:
        {
          "products": [
            {
              "product_id":   1,
              "product_name": "Tabasco Original 5oz",
              "brand_name":   "Tabasco",
              "type":         "mine",
              "dates":        ["2026-06-01", ...],
              "prices":       [3.98, 3.98, 4.12, ...]
            },
            ...
          ]
        }
    """
    start, end = get_date_range(period)
    product_ids = get_group_product_ids(db, group_id)

    group   = db.query(TrackingGroup).get(group_id)
    products = [p for p in group.products if p.id in product_ids] if group else []

    result = {"products": []}

    for product in products:
        brand = db.query(Brand).get(product.brand_id)
        rows  = (
            db.query(ProductSnapshot.scraped_at, ProductSnapshot.price)
            .filter(
                ProductSnapshot.product_id == product.id,
                ProductSnapshot.scraped_at >= start,
                ProductSnapshot.scraped_at <= end,
                ProductSnapshot.price.isnot(None),
            )
            .order_by(ProductSnapshot.scraped_at)
            .all()
        )

        result["products"].append({
            "product_id":   product.id,
            "product_name": product.name,
            "brand_name":   brand.name if brand else "",
            "type":         brand.type if brand else "",
            "dates":        [str(r.scraped_at) for r in rows],
            "prices":       [float(r.price) for r in rows],
        })

    return result


# ── Reviews & Ratings ─────────────────────────────────────────────────────────

def get_review_trend(db: Session, group_id: int, period: str) -> dict:
    """
    Return weekly review count and avg rating per product over the period.

    Returns:
        {
          "products": [
            {
              "product_id":   1,
              "product_name": "Tabasco Original 5oz",
              "brand_name":   "Tabasco",
              "type":         "mine",
              "dates":        ["2026-06-01", ...],
              "review_counts": [1200, 1215, 1230, ...],
              "avg_ratings":   [4.5, 4.5, 4.6, ...],
              "count_deltas":  [null, 15, 15, ...]
            },
            ...
          ]
        }
    """
    start, end = get_date_range(period)
    product_ids = get_group_product_ids(db, group_id)

    group    = db.query(TrackingGroup).get(group_id)
    products = [p for p in group.products if p.id in product_ids] if group else []

    result = {"products": []}

    for product in products:
        brand = db.query(Brand).get(product.brand_id)
        rows  = (
            db.query(ReviewDelta)
            .filter(
                ReviewDelta.product_id == product.id,
                ReviewDelta.date >= start,
                ReviewDelta.date <= end,
            )
            .order_by(ReviewDelta.date)
            .all()
        )

        result["products"].append({
            "product_id":    product.id,
            "product_name":  product.name,
            "brand_name":    brand.name if brand else "",
            "type":          brand.type if brand else "",
            "dates":         [str(r.date) for r in rows],
            "review_counts": [r.review_count for r in rows],
            "avg_ratings":   [float(r.avg_rating) if r.avg_rating else None for r in rows],
            "count_deltas":  [r.review_count_delta for r in rows],
        })

    return result


# ── Content Changes ───────────────────────────────────────────────────────────

def get_content_changes(db: Session, group_id: int, period: str) -> list:
    """
    Return list of content changes detected for products in this group.

    Returns:
        [
          {
            "product_id":    1,
            "product_name":  "Tabasco Original 5oz",
            "brand_name":    "Tabasco",
            "detected_at":   "2026-06-01",
            "field_changed": "title",
            "previous_value": "...",
            "new_value":      "..."
          },
          ...
        ]
    """
    start, end = get_date_range(period)
    product_ids = get_group_product_ids(db, group_id)

    rows = (
        db.query(ContentChange)
        .filter(
            ContentChange.product_id.in_(product_ids),
            ContentChange.detected_at >= start,
            ContentChange.detected_at <= end,
        )
        .order_by(ContentChange.detected_at.desc())
        .all()
    )

    result = []
    for r in rows:
        product = db.query(Product).get(r.product_id)
        brand   = db.query(Brand).get(product.brand_id) if product else None
        result.append({
            "product_id":     r.product_id,
            "product_name":   product.name if product else "",
            "brand_name":     brand.name if brand else "",
            "detected_at":    str(r.detected_at),
            "field_changed":  r.field_changed,
            "previous_value": r.previous_value,
            "new_value":      r.new_value,
        })

    return result


# ── New SKU Alerts ────────────────────────────────────────────────────────────

def get_new_sku_alerts(db: Session, group_id: int, period: str) -> list:
    """
    Return new SKUs detected for tracked competitor brands in this group.

    Returns:
        [
          {
            "item_id":    "ABC123",
            "brand_name": "Cholula",
            "keyword":    "hot sauce",
            "first_seen": "2026-06-01"
          },
          ...
        ]
    """
    start, end = get_date_range(period)
    keyword_ids     = get_group_keyword_ids(db, group_id)
    group_brand_ids = get_group_brand_ids(db, group_id)

    rows = (
        db.query(SearchResult)
        .filter(
            SearchResult.keyword_id.in_(keyword_ids),
            SearchResult.is_new_sku == True,
            SearchResult.scraped_at >= start,
            SearchResult.scraped_at <= end,
            SearchResult.brand_id.in_(group_brand_ids),
        )
        .order_by(SearchResult.scraped_at.desc())
        .all()
    )

    result = []
    seen = set()
    for r in rows:
        key = (r.item_id, r.brand_id)
        if key in seen:
            continue
        seen.add(key)
        brand   = db.query(Brand).get(r.brand_id) if r.brand_id else None
        keyword = db.query(Keyword).get(r.keyword_id)
        result.append({
            "item_id":    r.item_id,
            "brand_name": brand.name if brand else "Unknown",
            "keyword":    keyword.keyword if keyword else "",
            "first_seen": str(r.scraped_at),
        })

    return result


# ── Dashboard Summary Stats ───────────────────────────────────────────────────

def get_summary_stats(db: Session, group_id: int, period: str) -> dict:
    """
    Return summary stat card data: current values + delta vs prior period.

    Returns:
        {
          "total_keywords":   10,
          "total_products":   6,
          "new_skus":         2,
          "content_changes":  5,
          "avg_rank": {
            "current": 4.2,
            "delta":   -0.8   # negative = improved (lower rank number)
          },
          "avg_sos_pct": {
            "current": 28.5,
            "delta":   2.1
          }
        }
    """
    start,       end       = get_date_range(period)
    prior_start, prior_end = get_prior_date_range(period)

    keyword_ids     = get_group_keyword_ids(db, group_id)
    product_ids     = get_group_product_ids(db, group_id)
    my_product_ids  = get_my_product_ids(db, group_id)
    group_brand_ids = get_group_brand_ids(db, group_id)

    # Get my products' item IDs for rank lookup
    group = db.query(TrackingGroup).get(group_id)
    my_item_ids = [
        p.walmart_item_id for p in (group.products if group else [])
        if p.id in my_product_ids
    ]

    def avg_rank(start_d, end_d):
        if not my_item_ids or not keyword_ids:
            return None
        rows = (
            db.query(func.avg(SearchResult.position))
            .filter(
                SearchResult.keyword_id.in_(keyword_ids),
                SearchResult.item_id.in_(my_item_ids),
                SearchResult.scraped_at >= start_d,
                SearchResult.scraped_at <= end_d,
            )
            .scalar()
        )
        return round(float(rows), 1) if rows else None

    def avg_sos_pct(start_d, end_d):
        """My brand's share of total page 1 slots as a percentage."""
        if not keyword_ids or not group_brand_ids:
            return None
        my_brand_ids = [
            b.id for b in (group.brands if group else [])
            if db.query(Brand).get(b.id) and db.query(Brand).get(b.id).type == 'mine'
        ]
        if not my_brand_ids:
            return None
        my_total = (
            db.query(func.sum(ShareOfSearch.total_count))
            .filter(
                ShareOfSearch.keyword_id.in_(keyword_ids),
                ShareOfSearch.brand_id.in_(my_brand_ids),
                ShareOfSearch.date >= start_d,
                ShareOfSearch.date <= end_d,
            )
            .scalar() or 0
        )
        all_total = (
            db.query(func.sum(ShareOfSearch.total_count))
            .filter(
                ShareOfSearch.keyword_id.in_(keyword_ids),
                ShareOfSearch.date >= start_d,
                ShareOfSearch.date <= end_d,
            )
            .scalar() or 0
        )
        return round((my_total / all_total * 100), 1) if all_total else None

    curr_rank  = avg_rank(start, end)
    prior_rank = avg_rank(prior_start, prior_end)
    curr_sos   = avg_sos_pct(start, end)
    prior_sos  = avg_sos_pct(prior_start, prior_end)

    new_skus = (
        db.query(func.count(SearchResult.id))
        .filter(
            SearchResult.keyword_id.in_(keyword_ids),
            SearchResult.is_new_sku == True,
            SearchResult.scraped_at >= start,
            SearchResult.scraped_at <= end,
        )
        .scalar() or 0
    )

    content_changes = (
        db.query(func.count(ContentChange.id))
        .filter(
            ContentChange.product_id.in_(product_ids),
            ContentChange.detected_at >= start,
            ContentChange.detected_at <= end,
        )
        .scalar() or 0
    )

    return {
        "total_keywords":  len(keyword_ids),
        "total_products":  len(product_ids),
        "new_skus":        new_skus,
        "content_changes": content_changes,
        "avg_rank": {
            "current": curr_rank,
            "delta":   round(curr_rank - prior_rank, 1) if curr_rank and prior_rank else None,
        },
        "avg_sos_pct": {
            "current": curr_sos,
            "delta":   round(curr_sos - prior_sos, 1) if curr_sos and prior_sos else None,
        },
    }
