"""
Weekly product scraper — runs every week.

Responsibilities:
- For each active product (all brands), scrape product page for:
    - Price
    - Review count + avg rating
- For competitor products only, also scrape:
    - Title, bullets, image count + resolution
    - Below-the-fold content flags: has_aplus, has_brand_story,
      has_comparison_chart, has_video, has_enhanced_content
- Write snapshots to product_snapshots and content_snapshots tables
- Diff content_snapshots against prior week, write deltas to content_changes
- Compute review_delta vs prior week snapshot
"""

# TODO: implement using Playwright
