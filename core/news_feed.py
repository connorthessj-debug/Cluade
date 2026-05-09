"""Background news feed — polls fetch_news.py for the ticker."""

from .scanner import run_fetch_script

REFRESH_SECONDS = 300  # 5 minutes
DEFAULT_QUERY = "stock market federal reserve economy"


async def get_news_snapshot(query: str = DEFAULT_QUERY) -> dict:
    """One-shot fetch of headlines from fetch_news.py."""
    return await run_fetch_script("fetch_news.py", query)
