"""Asset class detection — mirrors the rules in .claude/commands/scan.md exactly."""

CRYPTO_BASES = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE",
                "DOT", "LINK", "LTC", "MATIC", "ATOM", "NEAR", "ARB", "OP"}
CRYPTO_SUFFIXES = ("USDT", "BUSD", "USDC")
INDEX_SYMBOLS = {"SPX", "SPY", "QQQ", "NDX", "IWM", "DIA", "VIX", "ES", "NQ", "RUT", "DJI"}
CURRENCY_CODES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "MXN",
                  "CNY", "HKD", "SGD", "SEK", "NOK", "ZAR", "TRY", "BRL", "INR"}


def detect(symbol: str) -> str:
    """Return one of: equity, crypto, index, forex."""
    if not symbol:
        return "equity"
    s = symbol.upper().strip()

    if s in CRYPTO_BASES:
        return "crypto"
    for suffix in CRYPTO_SUFFIXES:
        if s.endswith(suffix):
            base = s[: -len(suffix)]
            if base in CRYPTO_BASES or len(base) >= 3:
                return "crypto"

    if s in INDEX_SYMBOLS:
        return "index"

    if len(s) == 6:
        a, b = s[:3], s[3:]
        if a in CURRENCY_CODES and b in CURRENCY_CODES:
            return "forex"

    return "equity"
