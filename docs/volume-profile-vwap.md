# Volume Profile & VWAP — Methodology

> READ-ONLY. Do not edit during scans. Propose changes via self-improvement audit only.

## Volume Profile

### What It Is
Volume Profile shows how much volume traded at each price level over a period, rather than over time. It reveals where institutions accumulated or distributed — the "true" support and resistance.

### Key Levels

**POC — Point of Control**
- The price with the highest traded volume in the period
- Acts as a price magnet: price tends to return to POC
- Above POC = bullish; below POC = bearish
- When approaching from below, POC is first resistance; from above, first support

**VAH — Value Area High**
- Upper boundary of the zone containing 70% of all volume
- Strong resistance on first approach from below
- Once broken and held, flips to support

**VAL — Value Area Low**
- Lower boundary of the 70% volume zone
- Strong support on first approach from above
- Once broken and held, flips to resistance

**HVN — High Volume Node**
- A cluster of significant volume at a specific price
- Acts like a mini-POC: price slows down here, expects consolidation
- Good entry zone for continuation trades

**LVN — Low Volume Node**
- A price zone with minimal traded volume
- Price accelerates through LVNs (no supply or demand)
- Use as targets — price will move quickly through them
- Also useful as stops if the trade goes against you (fast moves = fast losses)

### Calculation (scripts/fetch_equity.py)

```
1. Take 252 trading days of OHLCV data
2. Bin the full price range into 50 equal buckets
3. For each candle: distribute its volume across the buckets it overlaps
   (approximation: uniform distribution across OHLC range)
4. POC = bucket with highest volume
5. Value Area: starting from POC, add adjacent high-volume buckets until
   cumulative volume ≥ 70% of total → VAH and VAL are the boundaries
6. HVNs: buckets with volume > 1.5× average
7. LVNs: buckets with volume < 0.5× average
```

### How to Use in Scans

**Entry zones:** VAL (for longs), VAH (for shorts), any HVN retest with trend
**Stop zones:** Just below VAL (for longs), just above VAH (for shorts), beyond nearest LVN
**Target zones:** POC → VAH → HVN above VAH → 52W high (for longs)

---

## VWAP — Volume-Weighted Average Price

### What It Is
VWAP is the average price weighted by volume. Institutions use it as a benchmark — they're buying/selling relative to VWAP to minimize market impact.

```
VWAP = Σ(price × volume) ÷ Σ(volume)
```

### Standard VWAP (Intraday)
- Resets each day at open
- Price above VWAP = buyers in control (intraday)
- Price below VWAP = sellers in control
- Used by day traders and algo systems for order execution

### Anchored VWAP (Key for swing/position trading)
VWAP anchored to a significant event — gives the average cost basis since that event.

**Common anchors:**
- **Earnings release**: Institutional cost basis since last earnings — above = distribution hasn't started; below = trapped longs
- **52-week low**: Institutional accumulation basis — above = profitable for everyone who bought the lows
- **Major breakout**: Cost basis for momentum buyers
- **IPO/Secondary offering**: Lock-up basis for insiders

**Scoring signals:**
| Condition | Bias |
|-----------|------|
| Price above all anchored VWAPs | BULL — institutions in profit |
| Price above earnings VWAP but below 52W-low VWAP | MIXED |
| Price below earnings VWAP | BEAR — institutions underwater |

### VWAP Bands
Standard deviation bands around VWAP (±1σ, ±2σ) act as dynamic support/resistance. Mean reversion strategies: fade extensions beyond ±2σ. Trend continuation: enter on pullbacks to ±1σ band.

---

## ASCII Price Ladder Construction

The price ladder in the verdict is built as follows:

1. Collect all levels: 52W high, 52W low, POC, VAH, VAL, all HVNs/LVNs, current price, anchored VWAPs
2. Sort descending by price
3. Remove levels within 0.3% of each other (de-duplicate)
4. For each level, draw a bar of 1–10 `█` chars proportional to relative volume (POC = 10, VAL/VAH = 7–8, HVNs = 5–7, LVNs = 1–2)
5. Label each row with its type and value
6. Mark current price row with `◄ CURRENT`

**Example output:**
```
$195.00  ░░░░░░░░░░  ── 52W High
$192.40  ███████░░░  ── HVN
$189.20  ████████░░  ── VAH
$187.50  ██░░░░░░░░  ── LVN (fast travel)
$185.00  ██████████  ── POC (max volume)
$183.20  ██████████  ── CURRENT ◄
$182.30  ████████░░  ── HVN
$180.10  ██████░░░░  ── aVWAP (earnings anchor)
$178.50  ████████░░  ── VAL
$175.00  ░░░░░░░░░░  ── 52W Low
```
