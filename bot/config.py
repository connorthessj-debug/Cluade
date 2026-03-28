"""
SMC Dual-Agent Trading Bot — Configuration
All settings for FTMO compliance, instruments, timeframes, and MT5 connection.
"""

# ─── Mode ──────────────────────────────────────────────────────
PAPER_TRADING = True           # True = demo (paper), False = live/FTMO
DUAL_AGENT_MODE = True         # True = run BOTH agents simultaneously

# ─── OANDA API Connection (Practice/Demo) ────────────────────
OANDA_API_KEY = ""             # Your OANDA API token (generate at oanda.com)
OANDA_ACCOUNT_ID = ""          # Your OANDA account ID (e.g., "101-001-12345678-001")
OANDA_ENVIRONMENT = "practice" # "practice" for demo, "live" for real money

# How to get your OANDA credentials:
# 1. Sign up at https://www.oanda.com (choose "Demo/Practice" account)
# 2. Log in → My Services → Manage API Access → Generate token
# 3. Your Account ID is shown on the account summary page

# ─── FTMO Risk Limits ─────────────────────────────────────────
ACCOUNT_BALANCE = 10_000       # Starting balance (update from MT5 on init)
MAX_DAILY_LOSS_PCT = 5.0       # Max daily drawdown (FTMO: 5%)
MAX_TOTAL_DRAWDOWN_PCT = 10.0  # Max overall drawdown (FTMO: 10%)
MAX_RISK_PER_TRADE_PCT = 1.0   # Max risk per single trade
MAX_EXPOSURE_PCT = 5.0         # Max total open exposure (higher for dual-agent)
MAX_CONCURRENT_TRADES = 6      # Max simultaneous positions (3 per agent)

# ─── Safety Buffers (stay away from FTMO limits) ──────────────
DAILY_LOSS_BUFFER_PCT = 0.5    # Stop trading at 4.5% daily loss
TOTAL_DD_BUFFER_PCT = 1.0      # Stop trading at 9% total drawdown

# ─── Instruments ───────────────────────────────────────────────
# Verify symbol names in your broker's MT5 Market Watch — they vary by broker
# (e.g., "EURUSD" vs "EURUSD." vs "EURUSDm")
FOREX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "NZDUSD", "USDCAD",
    "EURGBP", "EURJPY", "GBPJPY",
]

GOLD = ["XAUUSD"]

INDICES = ["US30", "NAS100", "SPX500", "GER40"]

FUTURES = []  # OANDA doesn't offer futures

# All tradeable instruments
INSTRUMENTS = FOREX_PAIRS + GOLD + INDICES + FUTURES

# ─── Timeframes ────────────────────────────────────────────────
# Scalping agent timeframes
SCALP_ENTRY_TF = "M5"
SCALP_CONFIRM_TF = "M1"
SCALP_STRUCTURE_TF = "M15"

# Swing agent timeframes
SWING_ENTRY_TF = "H1"
SWING_CONFIRM_TF = "M15"
SWING_STRUCTURE_TF = "H4"

# Overseer regime detection timeframe
REGIME_TF = "H1"
REGIME_HTF = "D1"

# ─── SMC Parameters ───────────────────────────────────────────
# Structure detection
STRUCTURE_LOOKBACK = 50         # Candles to look back for swing points
SWING_STRENGTH = 3              # Min candles on each side of a swing high/low

# Order Blocks
OB_MAX_AGE_CANDLES = 30         # Max age of an OB before it's stale
OB_MAX_BODY_RATIO = 0.7        # Max body-to-range ratio for valid OB candle

# Fair Value Gaps
FVG_MIN_GAP_PIPS = 5           # Minimum gap size to be considered valid
FVG_MAX_AGE_CANDLES = 20       # Max age of an FVG

# Liquidity
LIQ_SWEEP_THRESHOLD_PIPS = 2   # How far past a level counts as a sweep
LIQ_EQUAL_HIGHS_TOLERANCE = 3  # Pip tolerance for "equal highs/lows"

# ─── Regime Detection Parameters ──────────────────────────────
ADX_PERIOD = 14
ADX_TRENDING_THRESHOLD = 25    # ADX above this = trending
ADX_WEAK_THRESHOLD = 15        # ADX below this = low volatility
ATR_PERIOD = 14
ATR_HIGH_VOL_MULTIPLIER = 1.5  # ATR > 1.5x average = high vol
ATR_LOW_VOL_MULTIPLIER = 0.6   # ATR < 0.6x average = low vol
REGIME_LOOKBACK = 100           # Candles for regime baseline

# ─── Trade Management ─────────────────────────────────────────
# Scalping
SCALP_DEFAULT_SL_PIPS = 15
SCALP_MIN_RR = 2.0             # Minimum risk:reward ratio
SCALP_MAX_HOLD_MINUTES = 120   # Force close after 2 hours

# Swing
SWING_DEFAULT_SL_PIPS = 50
SWING_MIN_RR = 3.0             # Minimum risk:reward ratio
SWING_MAX_HOLD_HOURS = 72      # Force close after 3 days

# Trailing stop
TRAIL_ACTIVATION_RR = 1.5      # Activate trailing stop at 1.5R
TRAIL_STEP_PIPS = 5            # Trail step size

# ─── Session Times (UTC) ──────────────────────────────────────
LONDON_OPEN = "07:00"
LONDON_CLOSE = "16:00"
NY_OPEN = "12:00"
NY_CLOSE = "21:00"
TOKYO_OPEN = "23:00"
TOKYO_CLOSE = "08:00"

# Preferred trading sessions
SCALP_SESSIONS = ["london_open", "ny_open"]  # High-vol sessions
SWING_SESSIONS = ["any"]                      # Swing trades any time

# ─── Cycle Timing ─────────────────────────────────────────────
OVERSEER_CYCLE_SECONDS = 30    # How often the overseer checks markets
HEARTBEAT_SECONDS = 300        # Log a heartbeat every 5 min

# ─── Logging ───────────────────────────────────────────────────
LOG_DIR = "logs"
LOG_LEVEL = "INFO"
LOG_MAX_SIZE_MB = 50
LOG_BACKUP_COUNT = 5
