"""
Analysis layer — reads scraped data, produces dashboard-ready aggregations.

Responsibilities:
- Search rank trends per product per keyword (daily, supports WoW/MoM/QoQ/YoY)
- Share of search trends per keyword per brand (daily rollup already in share_of_search)
- Pricing trends per product (weekly)
- Review/rating trends per product (weekly)
- Content change summaries per product (weekly)
- New SKU alerts (flagged during daily scrape, surfaced here)
"""

# TODO: implement query functions consumed by dashboard API endpoints
