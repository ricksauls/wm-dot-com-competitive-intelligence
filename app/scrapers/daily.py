"""
Daily keyword scraper — runs every day.

Responsibilities:
- For each active keyword, scrape page 1 of Walmart.com search results
- Capture all positions: item_id, position, position_type (organic/sponsored)
- Write raw results to search_results table
- Flag is_new_sku if item_id is from a tracked competitor brand and not seen before
- Compute and write share_of_search rollup per keyword per brand
"""

# TODO: port and extend from demo 1 Playwright scraper
