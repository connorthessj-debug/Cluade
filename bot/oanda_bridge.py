"""
SMC Dual-Agent Trading Bot — OANDA v20 REST API Bridge
Drop-in replacement for MT5Bridge. Same interface, pure Python, no Wine needed.

Uses OANDA's v20 REST API for:
- Account info
- Market data (candles, ticks)
- Order execution (market orders with SL/TP)
- Position management (close, modify SL)
"""

import time
import logging
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd

from config import (
    OANDA_API_KEY, OANDA_ACCOUNT_ID, OANDA_ENVIRONMENT,
)

logger = logging.getLogger(__name__)

# OANDA API base URLs
_BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

# Timeframe mapping: our names → OANDA granularity
TF_MAP = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D",
    "W1": "W",
}

# Magic tag to identify our bot's trades
BOT_TAG = "smc_bot_240325"


class OandaBridge:
    """Interface to OANDA v20 REST API for data and execution."""

    def __init__(self):
        self.connected = False
        self.base_url = _BASE_URLS.get(OANDA_ENVIRONMENT, _BASE_URLS["practice"])
        self.account_id = OANDA_ACCOUNT_ID
        self.headers = {
            "Authorization": f"Bearer {OANDA_API_KEY}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "UNIX",
        }
        self._symbol_cache = {}

    # ── HTTP Helpers ───────────────────────────────────────────

    def _get(self, path: str, params: dict = None) -> dict | None:
        """Make a GET request to OANDA API."""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            logger.error("OANDA GET %s → %d: %s", path, resp.status_code, resp.text[:200])
            return None
        except requests.RequestException as e:
            logger.error("OANDA GET %s failed: %s", path, e)
            return None

    def _post(self, path: str, data: dict) -> dict | None:
        """Make a POST request to OANDA API."""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.post(url, headers=self.headers, json=data, timeout=15)
            if resp.status_code in (200, 201):
                return resp.json()
            logger.error("OANDA POST %s → %d: %s", path, resp.status_code, resp.text[:200])
            return None
        except requests.RequestException as e:
            logger.error("OANDA POST %s failed: %s", path, e)
            return None

    def _put(self, path: str, data: dict) -> dict | None:
        """Make a PUT request to OANDA API."""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.put(url, headers=self.headers, json=data, timeout=15)
            if resp.status_code in (200, 201):
                return resp.json()
            logger.error("OANDA PUT %s → %d: %s", path, resp.status_code, resp.text[:200])
            return None
        except requests.RequestException as e:
            logger.error("OANDA PUT %s failed: %s", path, e)
            return None

    # ── Symbol Conversion ──────────────────────────────────────

    # Bidirectional mapping for non-obvious symbols
    _OANDA_MAP = {
        "XAUUSD": "XAU_USD", "XAGUSD": "XAG_USD",
        "XPTUSD": "XPT_USD", "XPDUSD": "XPD_USD",
        "XCUUSD": "XCU_USD",
        "US30": "US30_USD", "NAS100": "NAS100_USD", "SPX500": "SPX500_USD",
        "GER40": "DE30_EUR", "UK100": "UK100_GBP", "JP225": "JP225_USD",
        "FRA40": "FR40_EUR", "AUS200": "AU200_AUD", "HK33": "HK33_HKD",
        "CHINAH": "CN50_USD", "SING30": "SG30_SGD", "TWIX": "TWIX_USD",
        "NATGAS": "NATGAS_USD", "WTICO": "WTICO_USD", "BRENT": "BCO_USD",
        "WHEAT": "WHEAT_USD", "CORN": "CORN_USD", "SUGAR": "SUGAR_USD",
        "SOYBN": "SOYBN_USD",
    }
    _OANDA_REV = {v: k for k, v in _OANDA_MAP.items()}

    @classmethod
    def _to_oanda(cls, symbol: str) -> str:
        """Convert standard symbol to OANDA format."""
        if symbol in cls._OANDA_MAP:
            return cls._OANDA_MAP[symbol]
        # Forex pairs (6 chars, all alpha)
        if len(symbol) == 6 and symbol.isalpha():
            return f"{symbol[:3]}_{symbol[3:]}"
        return symbol

    @classmethod
    def _from_oanda(cls, oanda_symbol: str) -> str:
        """Convert OANDA format back to standard."""
        if oanda_symbol in cls._OANDA_REV:
            return cls._OANDA_REV[oanda_symbol]
        if "_" in oanda_symbol:
            parts = oanda_symbol.split("_")
            if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                combined = parts[0] + parts[1]
                if combined.isalpha():
                    return combined
        return oanda_symbol

    # ── Connection ─────────────────────────────────────────────

    def connect(self) -> bool:
        """Verify OANDA API connection."""
        if not OANDA_API_KEY or not OANDA_ACCOUNT_ID:
            logger.error("OANDA credentials not set in config.py")
            return False

        data = self._get(f"/v3/accounts/{self.account_id}")
        if data and "account" in data:
            acct = data["account"]
            logger.info(
                "OANDA connected — Account: %s, Balance: %s, Currency: %s",
                self.account_id, acct.get("balance", "?"), acct.get("currency", "?"),
            )
            self.connected = True
            return True

        logger.error("OANDA connection failed")
        return False

    def disconnect(self):
        """No persistent connection to close."""
        self.connected = False
        logger.info("OANDA bridge disconnected")

    def ensure_connected(self) -> bool:
        """Verify connection is still good."""
        if self.connected:
            return True

        for attempt in range(3):
            if self.connect():
                return True
            wait = 2 ** (attempt + 1)
            logger.warning("Reconnect attempt %d failed, waiting %ds", attempt + 1, wait)
            time.sleep(wait)

        logger.error("Failed to connect to OANDA after 3 attempts")
        return False

    # ── Instrument Discovery ───────────────────────────────────

    def fetch_all_instruments(self) -> list[str]:
        """Fetch all tradeable instruments from OANDA and return internal symbol names."""
        if not self.ensure_connected():
            return []

        data = self._get(f"/v3/accounts/{self.account_id}/instruments")
        if not data or "instruments" not in data:
            logger.warning("Could not fetch OANDA instruments")
            return []

        symbols = []
        for inst in data["instruments"]:
            oanda_name = inst["name"]
            internal = self._from_oanda(oanda_name)
            symbols.append(internal)
            # Cache the mapping for later
            if internal not in self._OANDA_MAP and oanda_name != internal:
                self._OANDA_MAP[internal] = oanda_name
                self._OANDA_REV[oanda_name] = internal

        logger.info("OANDA: Discovered %d tradeable instruments", len(symbols))
        return symbols

    # ── Account Info ───────────────────────────────────────────

    def get_account_info(self) -> dict | None:
        """Return account details as a dict (same interface as MT5Bridge)."""
        if not self.ensure_connected():
            return None

        data = self._get(f"/v3/accounts/{self.account_id}")
        if not data or "account" not in data:
            return None

        acct = data["account"]
        return {
            "login": self.account_id,
            "balance": float(acct.get("balance", 0)),
            "equity": float(acct.get("NAV", 0)),
            "margin": float(acct.get("marginUsed", 0)),
            "free_margin": float(acct.get("marginAvailable", 0)),
            "profit": float(acct.get("unrealizedPL", 0)),
            "leverage": int(1 / float(acct.get("marginRate", 0.01))),
            "currency": acct.get("currency", "USD"),
        }

    # ── Market Data ────────────────────────────────────────────

    def get_candles(self, symbol: str, timeframe: str, count: int = 200) -> pd.DataFrame | None:
        """Fetch OHLCV candles as a DataFrame."""
        if not self.ensure_connected():
            return None

        granularity = TF_MAP.get(timeframe)
        if granularity is None:
            logger.error("Unknown timeframe: %s", timeframe)
            return None

        oanda_sym = self._to_oanda(symbol)
        params = {
            "granularity": granularity,
            "count": min(count, 5000),
            "price": "M",  # midpoint
        }

        data = self._get(f"/v3/instruments/{oanda_sym}/candles", params)
        if not data or "candles" not in data:
            logger.warning("No candle data for %s %s", symbol, timeframe)
            return None

        candles = data["candles"]
        if not candles:
            return None

        rows = []
        for c in candles:
            if not c.get("complete", True) and len(candles) > 1:
                continue  # Skip incomplete candle unless it's the only one
            mid = c["mid"]
            rows.append({
                "datetime": datetime.fromtimestamp(float(c["time"]), tz=timezone.utc),
                "open": float(mid["o"]),
                "high": float(mid["h"]),
                "low": float(mid["l"]),
                "close": float(mid["c"]),
                "volume": int(c.get("volume", 0)),
            })

        if not rows:
            return None

        return pd.DataFrame(rows)

    def get_tick(self, symbol: str) -> dict | None:
        """Get the latest bid/ask for a symbol."""
        if not self.ensure_connected():
            return None

        oanda_sym = self._to_oanda(symbol)
        params = {"instruments": oanda_sym}
        data = self._get(f"/v3/accounts/{self.account_id}/pricing", params)

        if not data or "prices" not in data or not data["prices"]:
            return None

        price = data["prices"][0]
        return {
            "bid": float(price["bids"][0]["price"]),
            "ask": float(price["asks"][0]["price"]),
            "time": datetime.fromtimestamp(float(price["time"]), tz=timezone.utc),
        }

    def get_symbol_info(self, symbol: str) -> dict | None:
        """Get symbol properties (pip size, lot sizes, etc.)."""
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]

        if not self.ensure_connected():
            return None

        oanda_sym = self._to_oanda(symbol)
        data = self._get(f"/v3/accounts/{self.account_id}/instruments",
                         {"instruments": oanda_sym})

        if not data or "instruments" not in data or not data["instruments"]:
            logger.warning("Symbol not found: %s", symbol)
            return None

        inst = data["instruments"][0]
        pip_loc = abs(int(inst.get("pipLocation", -4)))
        digits = int(inst.get("displayPrecision", 5))
        point = 10 ** (-digits)
        pip_size = 10 ** (-pip_loc)

        # OANDA uses units, not lots. 1 standard lot = 100,000 units
        min_units = float(inst.get("minimumTradeSize", "1"))
        max_units = float(inst.get("maximumOrderUnits", "100000000"))

        info = {
            "name": symbol,
            "oanda_name": oanda_sym,
            "digits": digits,
            "point": point,
            "pip_size": pip_size,
            "trade_tick_size": point,
            "trade_tick_value": point,  # Approximation, varies by pair
            "volume_min": min_units / 100_000,  # Convert units to lots
            "volume_max": max_units / 100_000,
            "volume_step": 0.01,  # OANDA supports micro lots
            "trade_contract_size": 100_000,
            "spread": 0,  # Will be filled from live pricing
            "min_units": min_units,
            "max_units": max_units,
            "type": inst.get("type", "CURRENCY"),
            "margin_rate": float(inst.get("marginRate", "0.01")),
        }

        self._symbol_cache[symbol] = info
        return info

    # ── Order Execution ────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        sl_price: float,
        tp_price: float,
        comment: str = "SMC_BOT",
    ) -> dict | None:
        """Place a market order with SL and TP."""
        if not self.ensure_connected():
            return None

        sym_info = self.get_symbol_info(symbol)
        if not sym_info:
            logger.error("Cannot get symbol info for %s", symbol)
            return None

        oanda_sym = self._to_oanda(symbol)
        digits = sym_info["digits"]

        # Convert lots to units (1 lot = 100,000 units for forex)
        units = int(lot_size * 100_000)
        if direction == "sell":
            units = -units

        # Round SL/TP to proper precision
        sl_str = f"{sl_price:.{digits}f}"
        tp_str = f"{tp_price:.{digits}f}"

        order_data = {
            "order": {
                "type": "MARKET",
                "instrument": oanda_sym,
                "units": str(units),
                "stopLossOnFill": {"price": sl_str},
                "takeProfitOnFill": {"price": tp_str},
                "clientExtensions": {
                    "tag": BOT_TAG,
                    "comment": comment,
                },
            }
        }

        result = self._post(f"/v3/accounts/{self.account_id}/orders", order_data)
        if not result:
            logger.error("Order send failed for %s %s", direction, symbol)
            return None

        # Check for fill
        if "orderFillTransaction" in result:
            fill = result["orderFillTransaction"]
            trade_id = fill.get("tradeOpened", {}).get("tradeID", "0")
            fill_price = float(fill.get("price", 0))

            logger.info(
                "ORDER PLACED — %s %s %.2f lots @ %.5f | SL=%s TP=%s | TradeID=%s",
                direction.upper(), symbol, lot_size, fill_price,
                sl_str, tp_str, trade_id,
            )
            return {
                "ticket": int(trade_id),
                "symbol": symbol,
                "direction": direction,
                "lot_size": lot_size,
                "price": fill_price,
                "sl": sl_price,
                "tp": tp_price,
            }

        # Check for rejection
        if "orderCancelTransaction" in result:
            reason = result["orderCancelTransaction"].get("reason", "unknown")
            logger.error("Order rejected — %s %s: %s", direction, symbol, reason)
            return None

        logger.error("Unexpected order response for %s %s: %s", direction, symbol, result)
        return None

    def close_position(self, ticket: int) -> bool:
        """Close an open trade by trade ID."""
        if not self.ensure_connected():
            return False

        # Close by sending a PUT to the trade's close endpoint
        result = self._put(
            f"/v3/accounts/{self.account_id}/trades/{ticket}/close",
            {"units": "ALL"},
        )

        if result and "orderFillTransaction" in result:
            fill = result["orderFillTransaction"]
            symbol = self._from_oanda(fill.get("instrument", ""))
            logger.info(
                "POSITION CLOSED — TradeID %d, %s, P&L: %s",
                ticket, symbol, fill.get("pl", "?"),
            )
            return True

        logger.error("Failed to close trade %d", ticket)
        return False

    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify the stop loss of an open trade (for trailing)."""
        if not self.ensure_connected():
            return False

        # First get the trade to know the symbol precision
        data = self._get(f"/v3/accounts/{self.account_id}/trades/{ticket}")
        if not data or "trade" not in data:
            return False

        trade = data["trade"]
        symbol = self._from_oanda(trade["instrument"])
        sym_info = self.get_symbol_info(symbol)
        digits = sym_info["digits"] if sym_info else 5

        sl_str = f"{new_sl:.{digits}f}"

        # Get existing TP if any
        tp_data = {}
        if trade.get("takeProfitOrder"):
            tp_data["takeProfit"] = {"price": trade["takeProfitOrder"]["price"]}

        order_data = {
            "stopLoss": {"price": sl_str},
            **tp_data,
        }

        result = self._put(
            f"/v3/accounts/{self.account_id}/trades/{ticket}/orders",
            order_data,
        )

        if result:
            logger.debug("SL modified — TradeID %d, new SL=%s", ticket, sl_str)
            return True

        logger.error("Failed to modify SL for trade %d", ticket)
        return False

    # ── Position Queries ───────────────────────────────────────

    def get_open_positions(self) -> list[dict]:
        """Return all open trades placed by this bot."""
        if not self.ensure_connected():
            return []

        data = self._get(f"/v3/accounts/{self.account_id}/trades",
                         {"state": "OPEN"})
        if not data or "trades" not in data:
            return []

        bot_trades = []
        for trade in data["trades"]:
            # Filter to only our bot's trades
            ext = trade.get("clientExtensions", {})
            if ext.get("tag") != BOT_TAG:
                continue

            units = int(trade["currentUnits"])
            symbol = self._from_oanda(trade["instrument"])

            bot_trades.append({
                "ticket": int(trade["id"]),
                "symbol": symbol,
                "direction": "buy" if units > 0 else "sell",
                "lot_size": abs(units) / 100_000,
                "open_price": float(trade["price"]),
                "current_price": float(trade.get("unrealizedPL", 0)),  # Updated below
                "sl": float(trade.get("stopLossOrder", {}).get("price", 0)),
                "tp": float(trade.get("takeProfitOrder", {}).get("price", 0)),
                "profit": float(trade.get("unrealizedPL", 0)),
                "open_time": datetime.fromtimestamp(
                    float(trade["openTime"]), tz=timezone.utc
                ),
                "comment": ext.get("comment", ""),
            })

        # Update current prices from live pricing
        for pos in bot_trades:
            tick = self.get_tick(pos["symbol"])
            if tick:
                pos["current_price"] = tick["bid"] if pos["direction"] == "buy" else tick["ask"]

        return bot_trades

    def get_daily_profit(self) -> float:
        """Calculate total P&L for today (open + closed)."""
        if not self.ensure_connected():
            return 0.0

        # Open position P&L
        open_pnl = sum(p["profit"] for p in self.get_open_positions())

        # Today's closed trades
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        data = self._get(
            f"/v3/accounts/{self.account_id}/transactions",
            {
                "from": start_of_day.isoformat(),
                "type": "ORDER_FILL",
            },
        )

        closed_pnl = 0.0
        if data and "transactions" in data:
            for txn in data["transactions"]:
                ext = txn.get("clientExtensions", {})
                if ext.get("tag") != BOT_TAG:
                    continue
                # Only count closing fills
                if txn.get("reason") in ("STOP_LOSS_ORDER", "TAKE_PROFIT_ORDER",
                                          "MARKET_ORDER_TRADE_CLOSE"):
                    closed_pnl += float(txn.get("pl", 0))
                    closed_pnl += float(txn.get("commission", 0))

        return open_pnl + closed_pnl
