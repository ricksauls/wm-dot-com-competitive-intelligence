# Competitive Intelligence — Claude Context

## What this project is
A web application for tracking competitive intelligence on Walmart.com. Monitors search rank, share of search, pricing, reviews/ratings, content changes, and new SKU detection for tracked brands and products.

## Stack
- **Backend**: Python, FastAPI, SQLAlchemy, Alembic
- **Frontend**: Jinja2 templates, HTMX, Plotly.js
- **Database**: PostgreSQL
- **Scraping**: Playwright (Chromium)
- **Server**: Ubuntu 24.04, nginx, systemd, Digital Ocean
- **Repo**: GitHub, deployed to /home/deploy/apps/wm-competitive-intel on the droplet

## Project structure
- `app/main.py` — FastAPI app entry point, page routes, auth routes
- `app/models.py` — SQLAlchemy models
- `app/schemas.py` — Pydantic request/response schemas
- `app/analysis.py` — analysis layer (reads scraped data, produces dashboard aggregations)
- `app/core/database.py` — DB engine and session
- `app/core/config.py` — settings from environment variables
- `app/core/auth.py` — single-user session auth
- `app/api/routes/` — CRUD API routes for brands, products, keywords
- `app/scrapers/daily.py` — daily keyword scraper (rank, SOS, new SKU detection)
- `app/scrapers/weekly.py` — weekly product scraper (pricing, reviews, content changes)
- `app/frontend/templates/` — Jinja2 HTML templates
- `migrations/` — Alembic migrations

## Database tables
Config: brands, products, keywords
Daily scraped: search_results
Weekly scraped: product_snapshots, content_snapshots, content_changes
Analysis/rollup: share_of_search, review_delta

## Scraping cadence
- Daily: keyword searches → search rank, share of search, new SKU detection
- Weekly: product pages → pricing, reviews/ratings, content snapshots + diffs

## Key conventions
- All settings via environment variables, loaded from .env (never committed)
- Auth is single-user, credentials in .env as ADMIN_USERNAME and ADMIN_PASSWORD
- API routes all require authentication via get_current_user dependency
- Migrations use Alembic — run `alembic upgrade head` after schema changes
- Virtual environment at venv/ — always activate before running Python commands
- Restart app after code changes: `sudo systemctl restart wm-competitive-intel`
- View logs: `sudo journalctl -u wm-competitive-intel -n 50 --no-pager`
