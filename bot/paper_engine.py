"""
SMC Dual-Agent Trading Bot — Paper Trading Engine

Simulates order execution locally using real market data.
Wraps any bridge to intercept order/position calls while
passing through market data calls to the real exchange.

Tracks positions, SL/TP fills, and P&L in logs/paper_state.json.
"""

import os
import json
import time
import random
import logging
from datetime import datetime, timezone

from config import LOG_DIR

logger = logging.getLogger(__name__)

_STATE_FILE = os.path.join(LOG_DIR, "paper_state.json")


class PaperPosition:
    """A simulated open position."""

    def __init__(self, ticket, symbol, direction, lot_size, entry_price,
                 sl, tp, comment="", exchange=""):
        self.ticket = ticket
        self.symbol = symbol
        self.direction = direction
        self.lot_size = lot_size
        self.entry_price = entry_price
        self.sl = sl
        self.tp = tp
        self.comment = comment
        self.exchange = exchange
        self.open_time = datetime.now(timezone.utc)
        self.current_price = entry_price
        self.pnl = 0.0

    def update_price(self, bid: float, ask: float):
        """Update current price and unrealized P&L."""
        if self.direction == "buy":
            self.current_price = bid
            self.pnl = (bid - self.entry_price) * self.lot_size
        else:
            self.current_price = ask
            self.pnl = (self.entry_price - ask) * self.lot_size

    def check_sl_tp(self, high: float, low: float) -> str | None:
        """
        Check if SL or TP was hit based on candle high/low.
        Returns 'sl', 'tp', or None.
        """
        if self.direction == "buy":
            if self.sl > 0 and low <= self.sl:
                return "sl"
            if self.tp > 0 and high >= self.tp:
                return "tp"
        else:
            if self.sl > 0 and high >= self.sl:
                return "sl"
            if self.tp > 0 and low <= self.tp:
                return "tp"
        return None

    def close_pnl(self, exit_price: float) -> float:
        """Calculate final P&L at exit price."""
        if self.direction == "buy":
            return (exit_price - self.entry_price) * self.lot_size
        else:
            return (self.entry_price - exit_price) * self.lot_size

    def to_dict(self) -> dict:
        return {
            "ticket": self.ticket,
            "symbol": self.symbol,
            "direction": self.direction,
            "lot_size": self.lot_size,
            "entry_price": self.entry_price,
            "sl": self.sl,
            "tp": self.tp,
            "comment": self.comment,
            "exchange": self.exchange,
            "open_time": self.open_time.isoformat(),
            "current_price": self.current_price,
            "pnl": self.pnl,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PaperPosition":
        pos = cls(
            ticket=d["ticket"], symbol=d["symbol"], direction=d["direction"],
            lot_size=d["lot_size"], entry_price=d["entry_price"],
            sl=d["sl"], tp=d["tp"], comment=d.get("comment", ""),
            exchange=d.get("exchange", ""),
        )
        pos.open_time = datetime.fromisoformat(d["open_time"])
        pos.current_price = d.get("current_price", d["entry_price"])
        pos.pnl = d.get("pnl", 0.0)
        return pos


class PaperEngine:
    """
    Wraps a real bridge. Market data goes through to the real exchange.
    Orders are simulated locally. Drop-in replacement — same interface.
    """

    def __init__(self, real_bridge):
        self.real = real_bridge
        self._positions: dict[int, PaperPosition] = {}
        self._closed: list[dict] = []
        self._next_ticket = 100000
        self._daily_pnl = 0.0
        self._daily_date = None
        self._load_state()

    # ── State Persistence ──────────────────────────────────────

    def _load_state(self):
        """Load paper positions from disk."""
        os.makedirs(LOG_DIR, exist_ok=True)
        if not os.path.exists(_STATE_FILE):
            return
        try:
            with open(_STATE_FILE, "r") as f:
                data = json.load(f)
            for d in data.get("positions", []):
                pos = PaperPosition.from_dict(d)
                self._positions[pos.ticket] = pos
            self._closed = data.get("closed_today", [])
            self._daily_pnl = data.get("daily_pnl", 0.0)
            self._daily_date = data.get("daily_date")
            self._next_ticket = data.get("next_ticket", 100000)
            logger.info("Paper engine: Loaded %d open positions from disk", len(self._positions))
        except Exception as e:
            logger.warning("Paper engine: Could not load state: %s", e)

    def _save_state(self):
        """Persist paper positions to disk."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_pnl = 0.0
            self._closed = []
            self._daily_date = today

        data = {
            "positions": [p.to_dict() for p in self._positions.values()],
            "closed_today": self._closed,
            "daily_pnl": self._daily_pnl,
            "daily_date": self._daily_date,
            "next_ticket": self._next_ticket,
        }
        try:
            with open(_STATE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Paper engine: Could not save state: %s", e)

    # ── Pass-through: Connection ───────────────────────────────

    @property
    def connected(self):
        return self.real.connected

    @connected.setter
    def connected(self, val):
        self.real.connected = val

    def connect(self) -> bool:
        result = self.real.connect()
        if result:
            logger.info("Paper engine: Connected (orders simulated locally)")
        return result

    def disconnect(self):
        self._save_state()
        self.real.disconnect()

    def ensure_connected(self) -> bool:
        return self.real.ensure_connected()

    # ── Pass-through: Market Data ──────────────────────────────

    def fetch_all_instruments(self) -> list[str]:
        return self.real.fetch_all_instruments()

    def get_candles(self, symbol, timeframe, count=200):
        return self.real.get_candles(symbol, timeframe, count)

    def get_tick(self, symbol):
        return self.real.get_tick(symbol)

    def get_symbol_info(self, symbol):
        return self.real.get_symbol_info(symbol)

    # ── Pass-through: Binance-specific attributes ──────────────

    @property
    def _futures_symbols(self):
        return getattr(self.real, '_futures_symbols', set())

    @property
    def _spot_symbols(self):
        return getattr(self.real, '_spot_symbols', set())

    # ── Simulated: Account Info ────────────────────────────────

    def get_account_info(self) -> dict | None:
        """Return simulated account info based on config balance + paper P&L."""
        from config import ACCOUNT_BALANCE

        open_pnl = sum(p.pnl for p in self._positions.values())
        equity = ACCOUNT_BALANCE + self._daily_pnl + open_pnl

        return {
            "login": "paper_trading",
            "balance": ACCOUNT_BALANCE + self._daily_pnl,
            "equity": equity,
            "margin": 0.0,
            "free_margin": equity,
            "profit": open_pnl,
            "leverage": 100,
            "currency": "USD",
        }

    # ── Simulated: Order Execution ─────────────────────────────

    def _simulate_slippage(self, price: float, direction: str, symbol: str) -> float:
        """
        Simulate realistic slippage.
        - Always slips AGAINST the trader (worse fill)
        - 60% of the time: 0 slippage (filled at quoted price)
        - 30% of the time: 1-3 ticks adverse slippage
        - 10% of the time: 3-8 ticks adverse slippage (volatile fill)
        """
        sym_info = self.real.get_symbol_info(symbol)
        tick_size = sym_info["point"] if sym_info else 0.0001

        roll = random.random()
        if roll < 0.60:
            slip_ticks = 0
        elif roll < 0.90:
            slip_ticks = random.randint(1, 3)
        else:
            slip_ticks = random.randint(3, 8)

        slip = slip_ticks * tick_size

        # Slippage is always adverse: buy fills higher, sell fills lower
        if direction == "buy":
            slipped = price + slip
        else:
            slipped = price - slip

        if slip_ticks > 0:
            logger.debug(
                "Paper slippage: %s %s — %d ticks (%.6f → %.6f)",
                direction.upper(), symbol, slip_ticks, price, slipped,
            )

        return slipped

    def place_order(self, symbol, direction, lot_size, sl_price, tp_price,
                    comment="SMC_BOT") -> dict | None:
        """Simulate a market order fill at current price with slippage."""
        tick = self.real.get_tick(symbol)
        if not tick:
            logger.error("Paper engine: Cannot get price for %s", symbol)
            return None

        # Fill at ask for buy, bid for sell, then apply slippage
        raw_price = tick["ask"] if direction == "buy" else tick["bid"]
        fill_price = self._simulate_slippage(raw_price, direction, symbol)

        ticket = self._next_ticket
        self._next_ticket += 1

        exchange = ""
        if hasattr(self.real, '_symbol_exchange'):
            exchange = self.real._symbol_exchange.get(symbol, "")

        pos = PaperPosition(
            ticket=ticket, symbol=symbol, direction=direction,
            lot_size=lot_size, entry_price=fill_price,
            sl=sl_price, tp=tp_price, comment=comment,
            exchange=exchange,
        )
        self._positions[ticket] = pos
        self._save_state()

        logger.info(
            "PAPER ORDER FILLED — %s %s %.4f @ %.6f | SL=%.6f TP=%.6f | Ticket=%d",
            direction.upper(), symbol, lot_size, fill_price, sl_price, tp_price, ticket,
        )

        return {
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "lot_size": lot_size,
            "price": fill_price,
            "sl": sl_price,
            "tp": tp_price,
        }

    def close_position(self, ticket, symbol=None) -> bool:
        """Close a paper position at current market price."""
        pos = self._positions.get(ticket)
        if not pos:
            logger.warning("Paper engine: Ticket %d not found", ticket)
            return False

        tick = self.real.get_tick(pos.symbol)
        if tick:
            exit_price = tick["bid"] if pos.direction == "buy" else tick["ask"]
        else:
            exit_price = pos.current_price

        pnl = pos.close_pnl(exit_price)
        self._daily_pnl += pnl

        hold = datetime.now(timezone.utc) - pos.open_time
        hold_str = f"{hold.total_seconds() / 60:.0f}m"

        self._closed.append({
            "ticket": ticket,
            "symbol": pos.symbol,
            "direction": pos.direction,
            "entry": pos.entry_price,
            "exit": exit_price,
            "pnl": round(pnl, 2),
            "hold_time": hold_str,
        })

        logger.info(
            "PAPER CLOSE — %s %s | Entry=%.6f Exit=%.6f | P&L=$%.2f | Hold=%s",
            pos.direction.upper(), pos.symbol, pos.entry_price, exit_price, pnl, hold_str,
        )

        del self._positions[ticket]
        self._save_state()
        return True

    def modify_sl(self, ticket, new_sl, symbol=None) -> bool:
        """Modify SL on a paper position."""
        pos = self._positions.get(ticket)
        if not pos:
            return False
        pos.sl = new_sl
        self._save_state()
        logger.debug("Paper SL modified — Ticket %d, new SL=%.6f", ticket, new_sl)
        return True

    # ── Simulated: Position Queries ────────────────────────────

    def get_open_positions(self) -> list[dict]:
        """Return all paper positions, updating prices from real market."""
        self._check_sl_tp_all()

        result = []
        for pos in self._positions.values():
            # Update with real price
            tick = self.real.get_tick(pos.symbol)
            if tick:
                pos.update_price(tick["bid"], tick["ask"])

            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "direction": pos.direction,
                "lot_size": pos.lot_size,
                "open_price": pos.entry_price,
                "current_price": pos.current_price,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.pnl,
                "open_time": pos.open_time,
                "comment": pos.comment,
                "exchange": pos.exchange,
            })

        self._save_state()
        return result

    def get_daily_profit(self) -> float:
        """Return today's realized + unrealized P&L."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_pnl = 0.0
            self._closed = []
            self._daily_date = today

        open_pnl = sum(p.pnl for p in self._positions.values())
        return self._daily_pnl + open_pnl

    # ── SL/TP Check Engine ─────────────────────────────────────

    def _check_sl_tp_all(self):
        """Check all open positions for SL/TP hits using latest candle data."""
        to_close = []

        for ticket, pos in self._positions.items():
            tick = self.real.get_tick(pos.symbol)
            if not tick:
                continue

            bid, ask = tick["bid"], tick["ask"]
            # Use bid/ask spread as a proxy for high/low
            high = max(bid, ask)
            low = min(bid, ask)

            hit = pos.check_sl_tp(high, low)
            if hit:
                if hit == "sl":
                    exit_price = pos.sl
                else:
                    exit_price = pos.tp
                to_close.append((ticket, exit_price, hit))

        for ticket, exit_price, hit_type in to_close:
            pos = self._positions[ticket]
            pnl = pos.close_pnl(exit_price)
            self._daily_pnl += pnl

            hold = datetime.now(timezone.utc) - pos.open_time
            hold_str = f"{hold.total_seconds() / 60:.0f}m"

            self._closed.append({
                "ticket": ticket,
                "symbol": pos.symbol,
                "direction": pos.direction,
                "entry": pos.entry_price,
                "exit": exit_price,
                "pnl": round(pnl, 2),
                "hold_time": hold_str,
                "reason": hit_type.upper(),
            })

            logger.info(
                "PAPER %s HIT — %s %s | Entry=%.6f Exit=%.6f | P&L=$%.2f | Hold=%s",
                hit_type.upper(), pos.direction.upper(), pos.symbol,
                pos.entry_price, exit_price, pnl, hold_str,
            )

            # Log to trade CSV
            try:
                import trade_logger
                trade_logger.log_close(
                    {
                        "symbol": pos.symbol,
                        "direction": pos.direction,
                        "lot_size": pos.lot_size,
                        "open_price": pos.entry_price,
                        "ticket": ticket,
                        "comment": pos.comment,
                    },
                    pnl=pnl, hold_time=hold_str,
                    reason=f"Paper {hit_type.upper()} hit",
                    exchange=pos.exchange,
                )
            except Exception:
                pass

            del self._positions[ticket]

        if to_close:
            self._save_state()
