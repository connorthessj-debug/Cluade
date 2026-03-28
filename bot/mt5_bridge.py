"""
SMC Dual-Agent Trading Bot — MetaTrader 5 Bridge
Handles all communication with MT5: connection, market data, and order execution.
"""

import time
import logging
from datetime import datetime, timezone

import MetaTrader5 as mt5
import pandas as pd

from config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH,
)

logger = logging.getLogger(__name__)

# MT5 timeframe mapping
TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}


class MT5Bridge:
    """Interface to MetaTrader 5 for data and execution."""

    def __init__(self):
        self.connected = False

    # ── Connection ─────────────────────────────────────────────

    def connect(self) -> bool:
        """Initialize MT5 and log in."""
        kwargs = {}
        if MT5_PATH:
            kwargs["path"] = MT5_PATH
        if MT5_LOGIN:
            kwargs["login"] = MT5_LOGIN
            kwargs["password"] = MT5_PASSWORD
            kwargs["server"] = MT5_SERVER

        if not mt5.initialize(**kwargs):
            logger.error("MT5 initialize failed: %s", mt5.last_error())
            return False

        # Verify login if credentials provided
        if MT5_LOGIN:
            account = mt5.account_info()
            if account is None:
                logger.error("MT5 login failed: %s", mt5.last_error())
                mt5.shutdown()
                return False
            logger.info(
                "MT5 connected — Account: %s, Balance: %.2f, Server: %s",
                account.login, account.balance, account.server,
            )

        self.connected = True
        return True

    def disconnect(self):
        """Shut down MT5 connection."""
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 disconnected")

    def ensure_connected(self) -> bool:
        """Reconnect if connection dropped."""
        if self.connected:
            # Quick health check
            account = mt5.account_info()
            if account is not None:
                return True
            logger.warning("MT5 connection lost, reconnecting...")
            self.connected = False

        for attempt in range(3):
            if self.connect():
                return True
            wait = 2 ** (attempt + 1)
            logger.warning("Reconnect attempt %d failed, waiting %ds", attempt + 1, wait)
            time.sleep(wait)

        logger.error("Failed to reconnect to MT5 after 3 attempts")
        return False

    # ── Account Info ───────────────────────────────────────────

    def get_account_info(self) -> dict | None:
        """Return account details as a dict."""
        if not self.ensure_connected():
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "profit": info.profit,
            "leverage": info.leverage,
            "currency": info.currency,
        }

    # ── Market Data ────────────────────────────────────────────

    def get_candles(self, symbol: str, timeframe: str, count: int = 200) -> pd.DataFrame | None:
        """Fetch OHLCV candles as a DataFrame."""
        if not self.ensure_connected():
            return None

        tf = TF_MAP.get(timeframe)
        if tf is None:
            logger.error("Unknown timeframe: %s", timeframe)
            return None

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning("No candle data for %s %s: %s", symbol, timeframe, mt5.last_error())
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(columns={
            "time": "datetime",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "tick_volume": "volume",
        }, inplace=True)
        return df[["datetime", "open", "high", "low", "close", "volume"]]

    def get_tick(self, symbol: str) -> dict | None:
        """Get the latest tick (bid/ask) for a symbol."""
        if not self.ensure_connected():
            return None
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "time": datetime.fromtimestamp(tick.time, tz=timezone.utc),
        }

    def get_symbol_info(self, symbol: str) -> dict | None:
        """Get symbol properties (pip size, lot sizes, etc.)."""
        if not self.ensure_connected():
            return None

        info = mt5.symbol_info(symbol)
        if info is None:
            # Try to enable the symbol first
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            if info is None:
                logger.warning("Symbol not found: %s", symbol)
                return None

        return {
            "name": info.name,
            "digits": info.digits,
            "point": info.point,
            "trade_tick_size": info.trade_tick_size,
            "trade_tick_value": info.trade_tick_value,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_contract_size": info.trade_contract_size,
            "spread": info.spread,
        }

    # ── Order Execution ────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        direction: str,  # "buy" or "sell"
        lot_size: float,
        sl_price: float,
        tp_price: float,
        comment: str = "SMC_BOT",
    ) -> dict | None:
        """Place a market order with SL and TP. Returns order result or None."""
        if not self.ensure_connected():
            return None

        # Validate symbol
        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            mt5.symbol_select(symbol, True)
            sym_info = mt5.symbol_info(symbol)
        if sym_info is None or not sym_info.visible:
            logger.error("Symbol %s not available for trading", symbol)
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error("Cannot get tick for %s", symbol)
            return None

        if direction == "buy":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        elif direction == "sell":
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            logger.error("Invalid direction: %s", direction)
            return None

        # Round lot size to volume step
        vol_step = sym_info.volume_step
        lot_size = round(round(lot_size / vol_step) * vol_step, 8)
        lot_size = max(sym_info.volume_min, min(lot_size, sym_info.volume_max))

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 20,  # max slippage in points
            "magic": 240325,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error("Order send returned None: %s", mt5.last_error())
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                "Order failed — %s %s %.2f lots: retcode=%d, comment=%s",
                direction, symbol, lot_size, result.retcode, result.comment,
            )
            return None

        logger.info(
            "ORDER PLACED — %s %s %.2f lots @ %.5f | SL=%.5f TP=%.5f | Ticket=%d",
            direction.upper(), symbol, lot_size, result.price,
            sl_price, tp_price, result.order,
        )
        return {
            "ticket": result.order,
            "symbol": symbol,
            "direction": direction,
            "lot_size": lot_size,
            "price": result.price,
            "sl": sl_price,
            "tp": tp_price,
        }

    def close_position(self, ticket: int) -> bool:
        """Close an open position by ticket number."""
        if not self.ensure_connected():
            return False

        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.warning("Position %d not found (may already be closed)", ticket)
            return False

        pos = position[0]
        symbol = pos.symbol
        lot_size = pos.volume

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error("Cannot get tick to close %s", symbol)
            return False

        # Reverse the direction to close
        if pos.type == mt5.ORDER_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 240325,
            "comment": "SMC_BOT_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else mt5.last_error()
            logger.error("Failed to close position %d: %s", ticket, err)
            return False

        logger.info("POSITION CLOSED — Ticket %d, %s %.2f lots", ticket, symbol, lot_size)
        return True

    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify the stop loss of an open position (for trailing)."""
        if not self.ensure_connected():
            return False

        position = mt5.positions_get(ticket=ticket)
        if not position:
            return False

        pos = position[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": pos.tp,
            "magic": 240325,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else mt5.last_error()
            logger.error("Failed to modify SL for %d: %s", ticket, err)
            return False

        logger.debug("SL modified — Ticket %d, new SL=%.5f", ticket, new_sl)
        return True

    # ── Position Queries ───────────────────────────────────────

    def get_open_positions(self) -> list[dict]:
        """Return all open positions placed by this bot."""
        if not self.ensure_connected():
            return []

        positions = mt5.positions_get()
        if positions is None:
            return []

        bot_positions = []
        for pos in positions:
            if pos.magic != 240325:
                continue
            bot_positions.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "direction": "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell",
                "lot_size": pos.volume,
                "open_price": pos.price_open,
                "current_price": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "open_time": datetime.fromtimestamp(pos.time, tz=timezone.utc),
                "comment": pos.comment,
            })
        return bot_positions

    def get_daily_profit(self) -> float:
        """Calculate total profit/loss for today's closed + open trades."""
        if not self.ensure_connected():
            return 0.0

        # Open position P&L
        open_pnl = sum(p["profit"] for p in self.get_open_positions())

        # Today's closed trades
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        deals = mt5.history_deals_get(start_of_day, now)
        closed_pnl = 0.0
        if deals:
            for deal in deals:
                if deal.magic == 240325 and deal.entry == mt5.DEAL_ENTRY_OUT:
                    closed_pnl += deal.profit + deal.commission + deal.swap

        return open_pnl + closed_pnl
