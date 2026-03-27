"""Exchange connectivity layer.

CryptoExchangeManager - ccxt async wrapper for Binance / Coinbase.
OandaClient          - Raw aiohttp wrapper for the OANDA v20 REST API.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
import ccxt.async_support as ccxt_async

from .models import OHLCV, OrderBook

logger = logging.getLogger(__name__)


# ======================================================================
# Crypto exchanges via ccxt
# ======================================================================

class CryptoExchangeManager:
    """Async ccxt wrapper with rate limiting and retry logic."""

    # Maximum concurrent requests per exchange
    _DEFAULT_CONCURRENCY = 5
    # Retry parameters
    _MAX_RETRIES = 3
    _BASE_BACKOFF = 1.0  # seconds

    def __init__(self, exchange_name: str, config) -> None:
        """
        Args:
            exchange_name: 'binance' or 'coinbase'.
            config: An ExchangeConfig instance from core.config.
        """
        self.exchange_name = exchange_name
        self._config = config
        self._exchange: Optional[ccxt_async.Exchange] = None
        self._semaphore = asyncio.Semaphore(self._DEFAULT_CONCURRENCY)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Instantiate and load markets for the exchange."""
        exchange_class = getattr(ccxt_async, self.exchange_name, None)
        if exchange_class is None:
            raise ValueError(f"Unsupported exchange: {self.exchange_name}")

        self._exchange = exchange_class(
            {
                "apiKey": self._config.api_key,
                "secret": self._config.secret,
                "enableRateLimit": True,
                "rateLimit": self._config.rate_limit,
                "options": self._config.options,
            }
        )

        if self._config.sandbox:
            self._exchange.set_sandbox_mode(True)

        await self._exchange.load_markets()
        logger.info("Connected to %s (%d markets loaded)", self.exchange_name, len(self._exchange.markets))

    async def close(self) -> None:
        """Close the exchange connection."""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _retry(self, coro_factory, description: str = "request"):
        """Execute an async call with exponential-backoff retry.

        Args:
            coro_factory: A zero-argument callable that returns an awaitable.
            description: Human-readable label for logging.
        """
        last_exc = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                async with self._semaphore:
                    return await coro_factory()
            except (ccxt_async.NetworkError, ccxt_async.ExchangeNotAvailable) as exc:
                last_exc = exc
                wait = self._BASE_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "%s %s attempt %d/%d failed: %s – retrying in %.1fs",
                    self.exchange_name, description, attempt, self._MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)
            except ccxt_async.ExchangeError as exc:
                # Non-transient exchange errors should not be retried
                logger.error("%s %s failed: %s", self.exchange_name, description, exc)
                raise
        raise last_exc  # type: ignore[misc]

    def _require_connection(self) -> None:
        if self._exchange is None:
            raise RuntimeError(f"{self.exchange_name}: not connected. Call connect() first.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch the latest ticker for *symbol*."""
        self._require_connection()
        return await self._retry(lambda: self._exchange.fetch_ticker(symbol), f"fetch_ticker({symbol})")

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> OrderBook:
        """Fetch L2 order book."""
        self._require_connection()
        raw = await self._retry(
            lambda: self._exchange.fetch_order_book(symbol, limit),
            f"fetch_order_book({symbol})",
        )
        return OrderBook(
            bids=[(b[0], b[1]) for b in raw.get("bids", [])],
            asks=[(a[0], a[1]) for a in raw.get("asks", [])],
            timestamp=datetime.utcnow(),
            exchange=self.exchange_name,
            symbol=symbol,
        )

    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Place an order on the exchange."""
        self._require_connection()
        return await self._retry(
            lambda: self._exchange.create_order(symbol, order_type, side, amount, price, params or {}),
            f"create_order({symbol} {side} {amount})",
        )

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: Optional[int] = None,
        limit: int = 100,
    ) -> List[OHLCV]:
        """Fetch OHLCV candles."""
        self._require_connection()
        raw = await self._retry(
            lambda: self._exchange.fetch_ohlcv(symbol, timeframe, since, limit),
            f"fetch_ohlcv({symbol} {timeframe})",
        )
        return [
            OHLCV(
                timestamp=datetime.utcfromtimestamp(c[0] / 1000),
                open=c[1],
                high=c[2],
                low=c[3],
                close=c[4],
                volume=c[5],
            )
            for c in raw
        ]

    async def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balances."""
        self._require_connection()
        return await self._retry(lambda: self._exchange.fetch_balance(), "fetch_balance")


# ======================================================================
# OANDA v20 REST API via aiohttp
# ======================================================================

class OandaClient:
    """Async OANDA v20 REST client using raw aiohttp.

    Does *not* depend on the oandapyV20 library.
    """

    _MAX_RETRIES = 3
    _BASE_BACKOFF = 1.0

    def __init__(self, config) -> None:
        """
        Args:
            config: An OandaConfig instance from core.config.
        """
        self._config = config
        self._base_url: str = config.base_url
        self._account_id: str = config.account_id
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open an aiohttp session with the required auth headers."""
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._config.access_token}",
                "Content-Type": "application/json",
                "Accept-Datetime-Format": "RFC3339",
            }
        )
        logger.info(
            "OANDA client connected to %s (account %s)",
            self._base_url,
            self._account_id,
        )

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _account_url(self, path: str = "") -> str:
        return self._url(f"/v3/accounts/{self._account_id}{path}")

    async def _request(
        self,
        method: str,
        url: str,
        description: str = "request",
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute an HTTP request with retry and error handling."""
        if self._session is None:
            raise RuntimeError("OandaClient: not connected. Call connect() first.")

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                async with self._session.request(method, url, **kwargs) as resp:
                    body = await resp.json()
                    if resp.status >= 400:
                        error_msg = body.get("errorMessage", str(body))
                        raise OandaAPIError(resp.status, error_msg)
                    return body
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                wait = self._BASE_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "OANDA %s attempt %d/%d failed: %s – retrying in %.1fs",
                    description, attempt, self._MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)
            except OandaAPIError:
                raise
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    async def get_pricing(self, instruments: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get current prices for one or more instruments.

        Args:
            instruments: List of instrument names (e.g. ['EUR_USD']). Defaults
                         to all instruments in config.
        """
        if instruments is None:
            instruments = self._config.instruments
        params = {"instruments": ",".join(instruments)}
        return await self._request(
            "GET",
            self._account_url("/pricing"),
            description="get_pricing",
            params=params,
        )

    # ------------------------------------------------------------------
    # Candles
    # ------------------------------------------------------------------

    async def get_candles(
        self,
        instrument: str,
        granularity: str = "M5",
        count: int = 100,
        price: str = "MBA",
    ) -> Dict[str, Any]:
        """Fetch candlestick data.

        Args:
            instrument: e.g. 'EUR_USD'.
            granularity: OANDA granularity string (S5, M1, M5, M15, H1, H4, D, W, M).
            count: Number of candles (max 5000).
            price: Price component(s) - M=mid, B=bid, A=ask.
        """
        params = {
            "granularity": granularity,
            "count": str(count),
            "price": price,
        }
        return await self._request(
            "GET",
            self._url(f"/v3/instruments/{instrument}/candles"),
            description=f"get_candles({instrument} {granularity})",
            params=params,
        )

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def create_order(
        self,
        instrument: str,
        units: float,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create an order on OANDA.

        Args:
            instrument: e.g. 'EUR_USD'.
            units: Positive for buy, but this method also accepts a *side*
                   parameter and will negate units automatically for sells.
            side: 'buy' or 'sell'.
            order_type: 'MARKET', 'LIMIT', 'STOP'.
            price: Required for LIMIT / STOP orders.
            stop_loss: Optional stop-loss price.
            take_profit: Optional take-profit price.
        """
        signed_units = abs(units) if side == "buy" else -abs(units)
        order_body: Dict[str, Any] = {
            "type": order_type,
            "instrument": instrument,
            "units": str(int(signed_units)) if signed_units == int(signed_units) else str(signed_units),
            "timeInForce": "FOK" if order_type == "MARKET" else "GTC",
        }

        if order_type in ("LIMIT", "STOP") and price is not None:
            order_body["price"] = str(price)

        if stop_loss is not None:
            order_body["stopLossOnFill"] = {"price": str(stop_loss)}
        if take_profit is not None:
            order_body["takeProfitOnFill"] = {"price": str(take_profit)}

        payload = {"order": order_body}
        return await self._request(
            "POST",
            self._account_url("/orders"),
            description=f"create_order({instrument} {side} {units})",
            json=payload,
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def close_position(
        self,
        instrument: str,
        long_units: Optional[str] = None,
        short_units: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Close (fully or partially) a position on an instrument.

        Args:
            instrument: e.g. 'EUR_USD'.
            long_units: Units to close on the long side ('ALL' or a number string).
            short_units: Units to close on the short side ('ALL' or a number string).
        """
        body: Dict[str, Any] = {}
        if long_units:
            body["longUnits"] = long_units
        if short_units:
            body["shortUnits"] = short_units
        if not body:
            body["longUnits"] = "ALL"

        return await self._request(
            "PUT",
            self._account_url(f"/positions/{instrument}/close"),
            description=f"close_position({instrument})",
            json=body,
        )

    async def get_open_positions(self) -> Dict[str, Any]:
        """Retrieve all open positions on the account."""
        return await self._request(
            "GET",
            self._account_url("/openPositions"),
            description="get_open_positions",
        )

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary (balance, NAV, margin, etc.)."""
        return await self._request(
            "GET",
            self._account_url("/summary"),
            description="get_account_summary",
        )

    # ------------------------------------------------------------------
    # Order book
    # ------------------------------------------------------------------

    async def get_order_book(self, instrument: str) -> Dict[str, Any]:
        """Fetch the public order book snapshot for an instrument."""
        return await self._request(
            "GET",
            self._url(f"/v3/instruments/{instrument}/orderBook"),
            description=f"get_order_book({instrument})",
        )


# ======================================================================
# Exceptions
# ======================================================================

class OandaAPIError(Exception):
    """Raised when the OANDA API returns an error response."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"OANDA API error {status}: {message}")
