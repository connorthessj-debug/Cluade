#!/usr/bin/env python3
"""
RENDER Dip-Buy Spike-Sell Trading Bot

Strategy:
1. Monitor RENDER-USD price continuously
2. Detect dips (price drops X% from recent high)
3. Buy on the dip using full available USD balance
4. Set take-profit at +10% and stop-loss at -5%
5. Sell when either target is hit
6. Repeat

Uses limit orders for 0% maker fees where possible.
Falls back to market orders for stop-loss (speed matters).
"""

import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from coinbase_client import CoinbaseClient, load_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class BotConfig:
    product_id: str = "RENDER-USD"
    base_currency: str = "RENDER"
    quote_currency: str = "USD"

    # Entry: buy when price dips this much from recent high
    dip_entry_pct: float = 5.0       # Buy after a 5% dip from recent high

    # Exit targets
    take_profit_pct: float = 10.0    # Sell at +10% from buy price
    stop_loss_pct: float = 5.0       # Sell at -5% from buy price

    # Trailing high lookback (hours)
    lookback_hours: int = 24         # Track the high over last 24h

    # Polling interval
    poll_seconds: float = 5.0        # Check price every 5 seconds

    # Capital management
    max_position_pct: float = 95.0   # Use 95% of available USD (keep buffer for rounding)

    # Safety
    min_trade_usd: float = 1.50      # Minimum trade size (RENDER min is $1)
    max_trades_per_day: int = 10      # Don't overtrade

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class Position:
    buy_price: float
    buy_size: float  # in RENDER
    buy_cost_usd: float
    buy_time: str
    take_profit_price: float
    stop_loss_price: float
    status: str = "open"  # open, closed
    sell_price: float = 0
    sell_time: str = ""
    pnl_usd: float = 0
    exit_reason: str = ""


@dataclass
class TradeLog:
    timestamp: str
    action: str  # BUY, SELL, STOP_LOSS
    price: float
    size: float
    usd_value: float
    pnl: float = 0
    reason: str = ""


# ---------------------------------------------------------------------------
# Bot Engine
# ---------------------------------------------------------------------------

class RenderTrader:
    def __init__(self, client: CoinbaseClient, config: BotConfig = None):
        self.client = client
        self.config = config or BotConfig()
        self.logger = logging.getLogger("trader")

        # State
        self.running = False
        self.position: Optional[Position] = None
        self.recent_high = 0.0
        self.current_price = 0.0
        self.current_bid = 0.0
        self.current_ask = 0.0
        self.usd_balance = 0.0
        self.render_balance = 0.0
        self.trades: list[TradeLog] = []
        self.daily_trades = 0
        self.last_trade_day = ""
        self.price_history: list[tuple] = []  # (timestamp, price)
        self.status_message = "Idle"
        self.total_pnl = 0.0

        # State file for persistence
        self.state_file = Path(__file__).parent / "bot_state.json"

    # --- State Persistence ---

    def save_state(self):
        state = {
            "position": asdict(self.position) if self.position else None,
            "recent_high": self.recent_high,
            "trades": [asdict(t) for t in self.trades[-100:]],  # Keep last 100
            "total_pnl": self.total_pnl,
            "daily_trades": self.daily_trades,
            "last_trade_day": self.last_trade_day,
            "config": self.config.to_dict(),
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    state = json.load(f)
                if state.get("position"):
                    self.position = Position(**state["position"])
                self.recent_high = state.get("recent_high", 0)
                self.trades = [TradeLog(**t) for t in state.get("trades", [])]
                self.total_pnl = state.get("total_pnl", 0)
                self.daily_trades = state.get("daily_trades", 0)
                self.last_trade_day = state.get("last_trade_day", "")
                if state.get("config"):
                    self.config = BotConfig.from_dict(state["config"])
                self.logger.info(f"Loaded state: position={'OPEN' if self.position else 'NONE'}, total_pnl=${self.total_pnl:.2f}")
            except Exception as e:
                self.logger.error(f"Failed to load state: {e}")

    # --- Price Tracking ---

    def update_price(self):
        """Fetch current price and update tracking."""
        try:
            data = self.client.get_best_bid_ask(self.config.product_id)
            self.current_bid = data["bid"]
            self.current_ask = data["ask"]
            self.current_price = (self.current_bid + self.current_ask) / 2

            now = time.time()
            self.price_history.append((now, self.current_price))

            # Trim history to lookback window
            cutoff = now - (self.config.lookback_hours * 3600)
            self.price_history = [(t, p) for t, p in self.price_history if t > cutoff]

            # Update recent high
            if self.price_history:
                self.recent_high = max(p for _, p in self.price_history)

            return True
        except Exception as e:
            self.logger.error(f"Price update failed: {e}")
            return False

    def update_balances(self):
        """Fetch current account balances."""
        try:
            self.usd_balance = self.client.get_balance(self.config.quote_currency)
            self.render_balance = self.client.get_balance(self.config.base_currency)
        except Exception as e:
            self.logger.error(f"Balance update failed: {e}")

    # --- Trading Logic ---

    def check_daily_reset(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.last_trade_day:
            self.daily_trades = 0
            self.last_trade_day = today

    def should_buy(self) -> bool:
        """Check if we should enter a position."""
        if self.position is not None:
            return False  # Already in a position

        if self.daily_trades >= self.config.max_trades_per_day:
            self.status_message = f"Daily limit reached ({self.config.max_trades_per_day})"
            return False

        if self.usd_balance < self.config.min_trade_usd:
            self.status_message = f"Insufficient USD (${self.usd_balance:.2f})"
            return False

        if self.recent_high <= 0 or self.current_ask <= 0:
            return False

        # Calculate dip from recent high
        dip_pct = ((self.recent_high - self.current_ask) / self.recent_high) * 100

        if dip_pct >= self.config.dip_entry_pct:
            self.status_message = f"DIP DETECTED: -{dip_pct:.1f}% from ${self.recent_high:.3f}"
            return True

        self.status_message = f"Watching: -{dip_pct:.1f}% from high ${self.recent_high:.3f} (need -{self.config.dip_entry_pct}%)"
        return False

    def should_sell(self) -> Optional[str]:
        """Check if we should exit position. Returns reason or None."""
        if self.position is None:
            return None

        if self.current_bid <= 0:
            return None

        price = self.current_bid

        # Take profit
        if price >= self.position.take_profit_price:
            return "TAKE_PROFIT"

        # Stop loss
        if price <= self.position.stop_loss_price:
            return "STOP_LOSS"

        return None

    def execute_buy(self):
        """Buy RENDER with available USD balance."""
        try:
            self.update_balances()
            trade_usd = self.usd_balance * (self.config.max_position_pct / 100)

            if trade_usd < self.config.min_trade_usd:
                self.logger.warning(f"Trade size too small: ${trade_usd:.2f}")
                return False

            # Use market order for immediate fill on dip entry
            result = self.client.place_market_order(
                self.config.product_id, "BUY", quote_size=trade_usd
            )

            order_id = result.get("order_id") or result.get("success_response", {}).get("order_id", "")
            if not order_id:
                self.logger.error(f"Buy order failed: {result}")
                return False

            # Wait for fill
            time.sleep(1)
            order = self.client.get_order(order_id)
            order_data = order.get("order", order)

            fill_price = float(order_data.get("average_filled_price", self.current_ask))
            filled_size = float(order_data.get("filled_size", trade_usd / self.current_ask))

            # Calculate targets
            tp_price = fill_price * (1 + self.config.take_profit_pct / 100)
            sl_price = fill_price * (1 - self.config.stop_loss_pct / 100)

            self.position = Position(
                buy_price=fill_price,
                buy_size=filled_size,
                buy_cost_usd=trade_usd,
                buy_time=datetime.now(timezone.utc).isoformat(),
                take_profit_price=tp_price,
                stop_loss_price=sl_price,
            )

            self.trades.append(TradeLog(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action="BUY",
                price=fill_price,
                size=filled_size,
                usd_value=trade_usd,
                reason=f"Dip entry at ${fill_price:.3f}",
            ))

            self.daily_trades += 1
            self.save_state()
            self.update_balances()

            self.logger.info(f"BOUGHT {filled_size:.2f} RENDER @ ${fill_price:.3f} (${trade_usd:.2f})")
            self.logger.info(f"  Take profit: ${tp_price:.3f} (+{self.config.take_profit_pct}%)")
            self.logger.info(f"  Stop loss:   ${sl_price:.3f} (-{self.config.stop_loss_pct}%)")
            self.status_message = f"HOLDING: bought @ ${fill_price:.3f} | TP ${tp_price:.3f} | SL ${sl_price:.3f}"
            return True

        except Exception as e:
            self.logger.error(f"Buy execution failed: {e}")
            return False

    def execute_sell(self, reason: str):
        """Sell all RENDER holdings."""
        try:
            self.update_balances()
            sell_size = self.render_balance

            if sell_size < 0.01:  # RENDER min increment
                self.logger.warning(f"Nothing to sell: {sell_size} RENDER")
                self.position = None
                self.save_state()
                return False

            # Market order for speed (especially on stop-loss)
            result = self.client.place_market_order(
                self.config.product_id, "SELL", base_size=sell_size
            )

            order_id = result.get("order_id") or result.get("success_response", {}).get("order_id", "")
            if not order_id:
                self.logger.error(f"Sell order failed: {result}")
                return False

            time.sleep(1)
            order = self.client.get_order(order_id)
            order_data = order.get("order", order)

            fill_price = float(order_data.get("average_filled_price", self.current_bid))
            usd_received = fill_price * sell_size

            # Calculate P&L
            pnl = usd_received - self.position.buy_cost_usd if self.position else 0
            self.total_pnl += pnl

            self.position.status = "closed"
            self.position.sell_price = fill_price
            self.position.sell_time = datetime.now(timezone.utc).isoformat()
            self.position.pnl_usd = pnl
            self.position.exit_reason = reason

            self.trades.append(TradeLog(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action="SELL",
                price=fill_price,
                size=sell_size,
                usd_value=usd_received,
                pnl=pnl,
                reason=reason,
            ))

            emoji = "+" if pnl >= 0 else ""
            self.logger.info(f"SOLD {sell_size:.2f} RENDER @ ${fill_price:.3f} ({reason}) | P&L: {emoji}${pnl:.2f}")
            self.status_message = f"SOLD ({reason}): ${fill_price:.3f} | P&L: {emoji}${pnl:.2f}"

            # Reset for next trade
            self.position = None
            self.recent_high = self.current_price  # Reset high after selling
            self.price_history = [(time.time(), self.current_price)]
            self.daily_trades += 1
            self.save_state()
            self.update_balances()
            return True

        except Exception as e:
            self.logger.error(f"Sell execution failed: {e}")
            return False

    # --- Main Loop ---

    def run(self):
        """Main trading loop."""
        self.running = True
        self.load_state()
        self.logger.info("=" * 50)
        self.logger.info("  RENDER DIP-BUY SPIKE-SELL BOT STARTED")
        self.logger.info("=" * 50)
        self.logger.info(f"  Product: {self.config.product_id}")
        self.logger.info(f"  Dip entry: -{self.config.dip_entry_pct}%")
        self.logger.info(f"  Take profit: +{self.config.take_profit_pct}%")
        self.logger.info(f"  Stop loss: -{self.config.stop_loss_pct}%")
        self.logger.info(f"  Poll interval: {self.config.poll_seconds}s")

        # Initial data fetch
        self.update_balances()
        self.logger.info(f"  USD balance: ${self.usd_balance:.2f}")
        self.logger.info(f"  RENDER balance: {self.render_balance:.2f}")

        if self.position:
            self.logger.info(f"  Resuming open position: bought @ ${self.position.buy_price:.3f}")

        error_count = 0

        while self.running:
            try:
                self.check_daily_reset()

                if not self.update_price():
                    error_count += 1
                    if error_count > 10:
                        self.logger.error("Too many consecutive errors, sleeping 60s")
                        time.sleep(60)
                        error_count = 0
                    continue

                error_count = 0

                # Check sell conditions first (if in position)
                sell_reason = self.should_sell()
                if sell_reason:
                    self.execute_sell(sell_reason)

                # Check buy conditions (if not in position)
                elif self.should_buy():
                    self.execute_buy()

                time.sleep(self.config.poll_seconds)

            except KeyboardInterrupt:
                self.logger.info("Shutting down...")
                self.running = False
                break
            except Exception as e:
                self.logger.error(f"Main loop error: {e}")
                time.sleep(10)

        self.save_state()
        self.logger.info("Bot stopped.")

    def stop(self):
        self.running = False

    # --- Status for Dashboard ---

    def get_status(self) -> dict:
        pos_data = None
        if self.position:
            unrealized_pnl = (self.current_bid - self.position.buy_price) * self.position.buy_size
            unrealized_pct = ((self.current_bid - self.position.buy_price) / self.position.buy_price) * 100 if self.position.buy_price > 0 else 0
            pos_data = {
                "buy_price": self.position.buy_price,
                "buy_size": self.position.buy_size,
                "buy_cost": self.position.buy_cost_usd,
                "buy_time": self.position.buy_time,
                "take_profit": self.position.take_profit_price,
                "stop_loss": self.position.stop_loss_price,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pct": unrealized_pct,
            }

        dip_pct = ((self.recent_high - self.current_price) / self.recent_high * 100) if self.recent_high > 0 else 0

        return {
            "running": self.running,
            "price": self.current_price,
            "bid": self.current_bid,
            "ask": self.current_ask,
            "recent_high": self.recent_high,
            "dip_from_high_pct": dip_pct,
            "usd_balance": self.usd_balance,
            "render_balance": self.render_balance,
            "position": pos_data,
            "total_pnl": self.total_pnl,
            "daily_trades": self.daily_trades,
            "total_trades": len(self.trades),
            "status_message": self.status_message,
            "config": self.config.to_dict(),
            "recent_trades": [asdict(t) for t in self.trades[-20:]],
        }
