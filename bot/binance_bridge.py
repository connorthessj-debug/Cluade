"""
SMC Dual-Agent Trading Bot — Binance Bridge
Spot + USDT-M Perpetual Futures via Binance REST API.
Same interface as OandaBridge for drop-in compatibility.

Supports:
- Auto-discovery of all tradeable pairs
- Candle/tick data for spot and futures
- Market orders with SL/TP (futures uses stop-market orders)
- Position management, trailing stops
"""

import time
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
import pandas as pd

from config import (
    BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET,
)

logger = logging.getLogger(__name__)

# API base URLs
_SPOT_URL = "https://api.binance.com"
_SPOT_TESTNET = "https://testnet.binance.vision"
_FUTURES_URL = "https://fapi.binance.com"
_FUTURES_TESTNET = "https://testnet.binancefuture.com"

# Timeframe mapping
TF_MAP = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w",
}

BOT_TAG = "smc_bot"


class BinanceBridge:
    """Interface to Binance REST API for spot and USDT-M futures."""

    def __init__(self):
        self.connected = False
        self.testnet = BINANCE_TESTNET
        self.spot_url = _SPOT_TESTNET if self.testnet else _SPOT_URL
        self.futures_url = _FUTURES_TESTNET if self.testnet else _FUTURES_URL
        self._symbol_cache = {}
        self._futures_symbols = set()  # Symbols available on futures
        self._spot_symbols = set()

    # ── HTTP Helpers ───────────────────────────────────────────

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": BINANCE_API_KEY}

    def _sign(self, params: dict) -> dict:
        """Add timestamp and HMAC-SHA256 signature to params."""
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        sig = hmac.new(
            BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = sig
        return params

    def _get(self, base_url: str, path: str, params: dict = None, signed: bool = False) -> dict | None:
        url = f"{base_url}{path}"
        if params is None:
            params = {}
        if signed:
            params = self._sign(params)
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Binance GET %s → %d: %s", path, resp.status_code, resp.text[:200])
            return None
        except requests.RequestException as e:
            logger.error("Binance GET %s failed: %s", path, e)
            return None

    def _post(self, base_url: str, path: str, params: dict, signed: bool = True) -> dict | None:
        url = f"{base_url}{path}"
        if signed:
            params = self._sign(params)
        try:
            resp = requests.post(url, headers=self._headers(), params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Binance POST %s → %d: %s", path, resp.status_code, resp.text[:200])
            return None
        except requests.RequestException as e:
            logger.error("Binance POST %s failed: %s", path, e)
            return None

    def _delete(self, base_url: str, path: str, params: dict, signed: bool = True) -> dict | None:
        url = f"{base_url}{path}"
        if signed:
            params = self._sign(params)
        try:
            resp = requests.delete(url, headers=self._headers(), params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Binance DELETE %s → %d: %s", path, resp.status_code, resp.text[:200])
            return None
        except requests.RequestException as e:
            logger.error("Binance DELETE %s failed: %s", path, e)
            return None

    # ── Symbol Helpers ─────────────────────────────────────────

    def _is_futures(self, symbol: str) -> bool:
        """Check if a symbol should be traded on futures."""
        return symbol in self._futures_symbols

    def _base_url_for(self, symbol: str) -> str:
        """Return the correct base URL for a symbol."""
        return self.futures_url if self._is_futures(symbol) else self.spot_url

    # ── Connection ─────────────────────────────────────────────

    def connect(self) -> bool:
        """Verify Binance API connection. Works without keys for public data only."""
        if not BINANCE_API_KEY or not BINANCE_API_SECRET:
            # No keys — test public endpoint only (enough for paper trading)
            data = self._get(self.spot_url, "/api/v3/ping")
            if data is not None:
                logger.info("Binance public API reachable (no auth — paper data only)")
                self.connected = True
                return True
            logger.error("Binance public API unreachable")
            return False

        # Test spot connection
        data = self._get(self.spot_url, "/api/v3/account", signed=True)
        if data and "balances" in data:
            usdt_balance = 0
            for b in data["balances"]:
                if b["asset"] == "USDT":
                    usdt_balance = float(b["free"]) + float(b["locked"])
                    break
            logger.info("Binance Spot connected — USDT: %.2f", usdt_balance)
        else:
            logger.warning("Binance Spot connection failed, trying futures only")

        # Test futures connection
        fdata = self._get(self.futures_url, "/fapi/v2/balance", signed=True)
        if fdata:
            for b in fdata:
                if b.get("asset") == "USDT":
                    logger.info("Binance Futures connected — USDT: %s", b.get("balance", "?"))
                    break
            self.connected = True
            return True

        if data and "balances" in data:
            self.connected = True
            return True

        logger.error("Binance connection failed")
        return False

    def disconnect(self):
        self.connected = False
        logger.info("Binance bridge disconnected")

    def ensure_connected(self) -> bool:
        if self.connected:
            return True
        for attempt in range(3):
            if self.connect():
                return True
            wait = 2 ** (attempt + 1)
            logger.warning("Binance reconnect attempt %d failed, waiting %ds", attempt + 1, wait)
            time.sleep(wait)
        return False

    # ── Instrument Discovery ───────────────────────────────────

    def fetch_all_instruments(self) -> list[str]:
        """Fetch all tradeable instruments from both spot and futures."""
        symbols = []

        # Futures — USDT-M perpetuals
        fdata = self._get(self.futures_url, "/fapi/v1/exchangeInfo")
        if fdata and "symbols" in fdata:
            for s in fdata["symbols"]:
                if s["status"] == "TRADING" and s["contractType"] == "PERPETUAL":
                    sym = s["symbol"]
                    self._futures_symbols.add(sym)
                    symbols.append(sym)

        # Spot — only USDT pairs that aren't already in futures
        sdata = self._get(self.spot_url, "/api/v3/exchangeInfo")
        if sdata and "symbols" in sdata:
            for s in sdata["symbols"]:
                if s["status"] == "TRADING" and s["quoteAsset"] == "USDT":
                    sym = s["symbol"]
                    if sym not in self._futures_symbols:
                        self._spot_symbols.add(sym)
                        symbols.append(sym)

        logger.info(
            "Binance: Discovered %d instruments (futures: %d, spot-only: %d)",
            len(symbols), len(self._futures_symbols), len(self._spot_symbols),
        )
        return symbols

    # ── Account Info ───────────────────────────────────────────

    def get_account_info(self) -> dict | None:
        if not self.ensure_connected():
            return None

        # Futures account info
        fdata = self._get(self.futures_url, "/fapi/v2/account", signed=True)
        if not fdata:
            return None

        return {
            "login": "binance_futures",
            "balance": float(fdata.get("totalWalletBalance", 0)),
            "equity": float(fdata.get("totalMarginBalance", 0)),
            "margin": float(fdata.get("totalInitialMargin", 0)),
            "free_margin": float(fdata.get("availableBalance", 0)),
            "profit": float(fdata.get("totalUnrealizedProfit", 0)),
            "leverage": 20,  # Default, varies by symbol
            "currency": "USDT",
        }

    # ── Market Data ────────────────────────────────────────────

    def get_candles(self, symbol: str, timeframe: str, count: int = 200) -> pd.DataFrame | None:
        if not self.ensure_connected():
            return None

        interval = TF_MAP.get(timeframe)
        if not interval:
            logger.error("Unknown timeframe: %s", timeframe)
            return None

        base = self._base_url_for(symbol)
        path = "/fapi/v1/klines" if self._is_futures(symbol) else "/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": min(count, 1500)}

        data = self._get(base, path, params)
        if not data:
            return None

        rows = []
        for k in data:
            rows.append({
                "datetime": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        return pd.DataFrame(rows) if rows else None

    def get_tick(self, symbol: str) -> dict | None:
        if not self.ensure_connected():
            return None

        base = self._base_url_for(symbol)
        path = "/fapi/v1/ticker/bookTicker" if self._is_futures(symbol) else "/api/v3/ticker/bookTicker"
        data = self._get(base, path, {"symbol": symbol})

        if not data:
            return None

        return {
            "bid": float(data["bidPrice"]),
            "ask": float(data["askPrice"]),
            "time": datetime.now(timezone.utc),
        }

    def get_symbol_info(self, symbol: str) -> dict | None:
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]

        base = self._base_url_for(symbol)
        path = "/fapi/v1/exchangeInfo" if self._is_futures(symbol) else "/api/v3/exchangeInfo"
        data = self._get(base, path)
        if not data:
            return None

        sym_data = None
        for s in data.get("symbols", []):
            if s["symbol"] == symbol:
                sym_data = s
                break

        if not sym_data:
            return None

        # Parse filters
        price_precision = int(sym_data.get("pricePrecision", 8))
        qty_precision = int(sym_data.get("quantityPrecision", 8))
        min_qty = 0.001
        max_qty = 1000000
        step_size = 0.001

        for f in sym_data.get("filters", []):
            if f["filterType"] == "LOT_SIZE":
                min_qty = float(f["minQty"])
                max_qty = float(f["maxQty"])
                step_size = float(f["stepSize"])

        point = 10 ** (-price_precision)

        info = {
            "name": symbol,
            "digits": price_precision,
            "point": point,
            "pip_size": point,
            "trade_tick_size": point,
            "trade_tick_value": point,
            "volume_min": min_qty,
            "volume_max": max_qty,
            "volume_step": step_size,
            "trade_contract_size": 1,  # Crypto is 1:1 (units, not lots)
            "spread": 0,
            "qty_precision": qty_precision,
            "is_futures": self._is_futures(symbol),
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
        if not self.ensure_connected():
            return None

        sym_info = self.get_symbol_info(symbol)
        if not sym_info:
            return None

        is_futures = sym_info.get("is_futures", False)
        base = self.futures_url if is_futures else self.spot_url
        digits = sym_info["digits"]
        qty_prec = sym_info.get("qty_precision", 3)

        # Round quantity
        step = sym_info["volume_step"]
        quantity = round(round(lot_size / step) * step, qty_prec)
        quantity = max(sym_info["volume_min"], min(quantity, sym_info["volume_max"]))

        side = "BUY" if direction == "buy" else "SELL"

        if is_futures:
            return self._place_futures_order(
                base, symbol, side, quantity, sl_price, tp_price, digits, comment
            )
        else:
            return self._place_spot_order(
                base, symbol, side, quantity, sl_price, tp_price, digits, comment
            )

    def _place_futures_order(
        self, base, symbol, side, quantity, sl_price, tp_price, digits, comment
    ) -> dict | None:
        """Place futures market order + separate SL/TP stop orders."""
        # Main market order
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "newClientOrderId": f"{BOT_TAG}_{int(time.time())}",
        }

        result = self._post(base, "/fapi/v1/order", params)
        if not result or "orderId" not in result:
            logger.error("Futures order failed for %s %s", side, symbol)
            return None

        fill_price = float(result.get("avgPrice", 0))
        order_id = result["orderId"]

        # Place stop-loss
        sl_side = "SELL" if side == "BUY" else "BUY"
        sl_params = {
            "symbol": symbol,
            "side": sl_side,
            "type": "STOP_MARKET",
            "stopPrice": f"{sl_price:.{digits}f}",
            "closePosition": "true",
            "newClientOrderId": f"{BOT_TAG}_sl_{int(time.time())}",
        }
        self._post(base, "/fapi/v1/order", sl_params)

        # Place take-profit
        tp_params = {
            "symbol": symbol,
            "side": sl_side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": f"{tp_price:.{digits}f}",
            "closePosition": "true",
            "newClientOrderId": f"{BOT_TAG}_tp_{int(time.time())}",
        }
        self._post(base, "/fapi/v1/order", tp_params)

        logger.info(
            "ORDER PLACED [FUTURES] — %s %s %.4f @ %.{digits}f | SL=%.{digits}f TP=%.{digits}f",
            side, symbol, quantity, fill_price, sl_price, tp_price,
        )
        return {
            "ticket": order_id,
            "symbol": symbol,
            "direction": "buy" if side == "BUY" else "sell",
            "lot_size": quantity,
            "price": fill_price,
            "sl": sl_price,
            "tp": tp_price,
        }

    def _place_spot_order(
        self, base, symbol, side, quantity, sl_price, tp_price, digits, comment
    ) -> dict | None:
        """Place spot market order. SL/TP via OCO or manual management."""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "newClientOrderId": f"{BOT_TAG}_{int(time.time())}",
        }

        result = self._post(base, "/api/v3/order", params)
        if not result or "orderId" not in result:
            logger.error("Spot order failed for %s %s", side, symbol)
            return None

        # Calculate average fill price
        fills = result.get("fills", [])
        if fills:
            total_qty = sum(float(f["qty"]) for f in fills)
            fill_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
        else:
            fill_price = 0

        logger.info(
            "ORDER PLACED [SPOT] — %s %s %.4f @ %.{digits}f",
            side, symbol, quantity, fill_price,
        )
        return {
            "ticket": result["orderId"],
            "symbol": symbol,
            "direction": "buy" if side == "BUY" else "sell",
            "lot_size": quantity,
            "price": fill_price,
            "sl": sl_price,
            "tp": tp_price,
        }

    def close_position(self, ticket: int) -> bool:
        """Close a futures position or sell spot holdings."""
        if not self.ensure_connected():
            return False

        # Try futures first
        positions = self._get(self.futures_url, "/fapi/v2/positionRisk", signed=True)
        if positions:
            for pos in positions:
                amt = float(pos.get("positionAmt", 0))
                if amt == 0:
                    continue
                symbol = pos["symbol"]
                side = "SELL" if amt > 0 else "BUY"
                params = {
                    "symbol": symbol,
                    "side": side,
                    "type": "MARKET",
                    "quantity": abs(amt),
                }
                result = self._post(self.futures_url, "/fapi/v1/order", params)
                if result:
                    # Cancel any open SL/TP orders
                    self._delete(self.futures_url, "/fapi/v1/allOpenOrders",
                                 {"symbol": symbol})
                    logger.info("POSITION CLOSED [FUTURES] — %s", symbol)
                    return True

        return False

    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify SL for a futures position by canceling old and placing new."""
        if not self.ensure_connected():
            return False

        # Get open orders to find the current SL
        positions = self._get(self.futures_url, "/fapi/v2/positionRisk", signed=True)
        if not positions:
            return False

        for pos in positions:
            amt = float(pos.get("positionAmt", 0))
            if amt == 0:
                continue

            symbol = pos["symbol"]
            sym_info = self.get_symbol_info(symbol)
            digits = sym_info["digits"] if sym_info else 2

            # Cancel existing SL orders
            orders = self._get(self.futures_url, "/fapi/v1/openOrders",
                               {"symbol": symbol}, signed=True)
            if orders:
                for o in orders:
                    if o.get("type") == "STOP_MARKET" and BOT_TAG in o.get("clientOrderId", ""):
                        self._delete(self.futures_url, "/fapi/v1/order",
                                     {"symbol": symbol, "orderId": o["orderId"]})

            # Place new SL
            sl_side = "SELL" if amt > 0 else "BUY"
            params = {
                "symbol": symbol,
                "side": sl_side,
                "type": "STOP_MARKET",
                "stopPrice": f"{new_sl:.{digits}f}",
                "closePosition": "true",
                "newClientOrderId": f"{BOT_TAG}_sl_{int(time.time())}",
            }
            result = self._post(self.futures_url, "/fapi/v1/order", params)
            if result:
                logger.debug("SL modified — %s, new SL=%.{digits}f", symbol, new_sl)
                return True

        return False

    # ── Position Queries ───────────────────────────────────────

    def get_open_positions(self) -> list[dict]:
        """Return open futures positions."""
        if not self.ensure_connected():
            return []

        positions = self._get(self.futures_url, "/fapi/v2/positionRisk", signed=True)
        if not positions:
            return []

        result = []
        for pos in positions:
            amt = float(pos.get("positionAmt", 0))
            if amt == 0:
                continue

            symbol = pos["symbol"]
            entry = float(pos.get("entryPrice", 0))
            mark = float(pos.get("markPrice", 0))
            pnl = float(pos.get("unRealizedProfit", 0))

            result.append({
                "ticket": hash(f"{symbol}_{entry}") & 0x7FFFFFFF,
                "symbol": symbol,
                "direction": "buy" if amt > 0 else "sell",
                "lot_size": abs(amt),
                "open_price": entry,
                "current_price": mark,
                "sl": 0,  # Would need to query open orders
                "tp": 0,
                "profit": pnl,
                "open_time": datetime.now(timezone.utc),  # Approx
                "comment": BOT_TAG,
            })

        return result

    def get_daily_profit(self) -> float:
        """Get today's realized + unrealized P&L."""
        if not self.ensure_connected():
            return 0.0

        # Unrealized from open positions
        open_pnl = sum(p["profit"] for p in self.get_open_positions())

        # Realized from income history (today)
        now = int(time.time() * 1000)
        start = now - 86400000  # 24h ago
        data = self._get(self.futures_url, "/fapi/v1/income",
                         {"incomeType": "REALIZED_PNL", "startTime": start, "limit": 1000},
                         signed=True)

        realized = 0.0
        if data:
            realized = sum(float(d.get("income", 0)) for d in data)

        return open_pnl + realized
