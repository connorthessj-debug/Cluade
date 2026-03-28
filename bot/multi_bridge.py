"""
SMC Dual-Agent Trading Bot — Multi-Exchange Bridge
Unified interface wrapping OandaBridge + BinanceBridge.

Routes symbols to the correct exchange automatically.
Aggregates positions, P&L, and account info across all exchanges.
"""

import logging

from config import (
    OANDA_API_KEY, OANDA_ACCOUNT_ID,
    BINANCE_API_KEY, BINANCE_API_SECRET,
    AUTO_DISCOVER_INSTRUMENTS, PAPER_TRADING,
)
from oanda_bridge import OandaBridge
from binance_bridge import BinanceBridge
from paper_engine import PaperEngine

logger = logging.getLogger(__name__)


class MultiBridge:
    """
    Unified bridge that routes calls to OANDA or Binance
    based on the symbol being traded.
    """

    def __init__(self):
        self.oanda = None
        self.binance = None
        self._oanda_symbols = set()
        self._binance_symbols = set()
        self._symbol_exchange = {}  # symbol -> "oanda" | "binance"

    # ── Connection ─────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to all configured exchanges."""
        any_connected = False

        # OANDA
        if OANDA_API_KEY and OANDA_ACCOUNT_ID:
            self.oanda = OandaBridge()
            if self.oanda.connect():
                logger.info("MultiBridge: OANDA connected")
                any_connected = True
            else:
                logger.warning("MultiBridge: OANDA connection failed")
                self.oanda = None
        else:
            logger.info("MultiBridge: OANDA not configured, skipping")

        # Binance
        if BINANCE_API_KEY and BINANCE_API_SECRET:
            raw_binance = BinanceBridge()
            if PAPER_TRADING:
                # Paper mode: use real URLs for market data, simulate orders
                raw_binance.spot_url = "https://api.binance.com"
                raw_binance.futures_url = "https://fapi.binance.com"
            if raw_binance.connect():
                if PAPER_TRADING:
                    self.binance = PaperEngine(raw_binance)
                    logger.info("MultiBridge: Binance connected (PAPER MODE — orders simulated locally)")
                else:
                    self.binance = raw_binance
                    logger.info("MultiBridge: Binance connected (LIVE)")
                any_connected = True
            else:
                logger.warning("MultiBridge: Binance connection failed")
                self.binance = None
        elif PAPER_TRADING:
            # Paper mode: no keys needed — use public market data only
            # Force REAL Binance URLs (not testnet) since we only read public data
            raw_binance = BinanceBridge()
            raw_binance.spot_url = "https://api.binance.com"
            raw_binance.futures_url = "https://fapi.binance.com"
            raw_binance.connected = True
            self.binance = PaperEngine(raw_binance)
            logger.info("MultiBridge: Binance PAPER MODE (public data + simulated orders)")
            any_connected = True
        else:
            logger.info("MultiBridge: Binance not configured, skipping")

        if any_connected:
            connected = []
            if self.oanda:
                connected.append("OANDA")
            if self.binance:
                connected.append("Binance")
            logger.info("MultiBridge: Active exchanges: %s", " + ".join(connected))
        else:
            logger.error("MultiBridge: No exchanges connected!")

        return any_connected

    def disconnect(self):
        """Disconnect all exchanges."""
        if self.oanda:
            self.oanda.disconnect()
        if self.binance:
            self.binance.disconnect()
        logger.info("MultiBridge: All exchanges disconnected")

    def ensure_connected(self) -> bool:
        """Ensure at least one exchange is connected."""
        oanda_ok = self.oanda and self.oanda.ensure_connected()
        binance_ok = self.binance and self.binance.ensure_connected()
        return oanda_ok or binance_ok

    # ── Instrument Discovery ───────────────────────────────────

    def fetch_all_instruments(self) -> list[str]:
        """Fetch instruments from all connected exchanges."""
        all_symbols = []

        if self.oanda:
            oanda_syms = self.oanda.fetch_all_instruments()
            for s in oanda_syms:
                self._oanda_symbols.add(s)
                self._symbol_exchange[s] = "oanda"
            all_symbols.extend(oanda_syms)
            logger.info("MultiBridge: OANDA — %d instruments", len(oanda_syms))

        if self.binance:
            binance_syms = self.binance.fetch_all_instruments()
            for s in binance_syms:
                self._binance_symbols.add(s)
                # Don't overwrite if OANDA already has it (unlikely for crypto)
                if s not in self._symbol_exchange:
                    self._symbol_exchange[s] = "binance"
            all_symbols.extend(binance_syms)
            logger.info("MultiBridge: Binance — %d instruments", len(binance_syms))

        logger.info("MultiBridge: Total — %d instruments across all exchanges", len(all_symbols))
        return all_symbols

    # ── Routing ────────────────────────────────────────────────

    def _bridge_for(self, symbol: str):
        """Return the correct bridge for a symbol."""
        exchange = self._symbol_exchange.get(symbol)
        if exchange == "binance" and self.binance:
            return self.binance
        if exchange == "oanda" and self.oanda:
            return self.oanda

        # Fallback: guess by symbol pattern
        # Binance symbols are usually uppercase with USDT suffix (BTCUSDT)
        if symbol.endswith("USDT") or symbol.endswith("BUSD"):
            if self.binance:
                self._symbol_exchange[symbol] = "binance"
                return self.binance

        # Default to OANDA for forex/metals/indices
        if self.oanda:
            self._symbol_exchange[symbol] = "oanda"
            return self.oanda

        # Last resort: return whichever is connected
        if self.binance:
            return self.binance
        return None

    # ── Account Info ───────────────────────────────────────────

    def get_account_info(self) -> dict | None:
        """Aggregate account info across all exchanges."""
        total_balance = 0.0
        total_equity = 0.0
        total_margin = 0.0
        total_free_margin = 0.0
        total_profit = 0.0
        login_parts = []

        if self.oanda:
            info = self.oanda.get_account_info()
            if info:
                total_balance += info["balance"]
                total_equity += info["equity"]
                total_margin += info["margin"]
                total_free_margin += info["free_margin"]
                total_profit += info["profit"]
                login_parts.append(f"OANDA:{info['login']}")

        if self.binance:
            info = self.binance.get_account_info()
            if info:
                total_balance += info["balance"]
                total_equity += info["equity"]
                total_margin += info["margin"]
                total_free_margin += info["free_margin"]
                total_profit += info["profit"]
                login_parts.append(f"BIN:{info['login']}")

        if not login_parts:
            return None

        return {
            "login": " + ".join(login_parts),
            "balance": total_balance,
            "equity": total_equity,
            "margin": total_margin,
            "free_margin": total_free_margin,
            "profit": total_profit,
            "leverage": 100,  # Varies by exchange/symbol
            "currency": "USD",
        }

    # ── Market Data ────────────────────────────────────────────

    def get_candles(self, symbol, timeframe, count=200):
        bridge = self._bridge_for(symbol)
        if not bridge:
            return None
        return bridge.get_candles(symbol, timeframe, count)

    def get_tick(self, symbol):
        bridge = self._bridge_for(symbol)
        if not bridge:
            return None
        return bridge.get_tick(symbol)

    def get_symbol_info(self, symbol):
        bridge = self._bridge_for(symbol)
        if not bridge:
            return None
        return bridge.get_symbol_info(symbol)

    # ── Order Execution ────────────────────────────────────────

    def place_order(self, symbol, direction, lot_size, sl_price, tp_price, comment="SMC_BOT"):
        bridge = self._bridge_for(symbol)
        if not bridge:
            logger.error("No exchange found for symbol: %s", symbol)
            return None
        return bridge.place_order(symbol, direction, lot_size, sl_price, tp_price, comment)

    def close_position(self, ticket, symbol=None):
        """Close a position. Symbol hint helps route to the correct exchange."""
        if symbol:
            bridge = self._bridge_for(symbol)
            if bridge:
                return bridge.close_position(ticket)

        # Try OANDA first, then Binance
        if self.oanda:
            result = self.oanda.close_position(ticket)
            if result:
                return result
        if self.binance:
            return self.binance.close_position(ticket)
        return False

    def modify_sl(self, ticket, new_sl, symbol=None):
        """Modify SL. Symbol hint helps route."""
        if symbol:
            bridge = self._bridge_for(symbol)
            if bridge:
                return bridge.modify_sl(ticket, new_sl)

        if self.oanda:
            result = self.oanda.modify_sl(ticket, new_sl)
            if result:
                return result
        if self.binance:
            return self.binance.modify_sl(ticket, new_sl)
        return False

    # ── Position Queries ───────────────────────────────────────

    def get_open_positions(self) -> list[dict]:
        """Aggregate open positions from all exchanges."""
        positions = []

        if self.oanda:
            oanda_pos = self.oanda.get_open_positions()
            for p in oanda_pos:
                p["exchange"] = "oanda"
            positions.extend(oanda_pos)

        if self.binance:
            binance_pos = self.binance.get_open_positions()
            for p in binance_pos:
                p["exchange"] = "binance"
            positions.extend(binance_pos)

        return positions

    def get_daily_profit(self) -> float:
        """Aggregate daily P&L across all exchanges."""
        total = 0.0
        if self.oanda:
            total += self.oanda.get_daily_profit()
        if self.binance:
            total += self.binance.get_daily_profit()
        return total
