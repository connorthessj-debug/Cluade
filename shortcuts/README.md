# iOS Shortcuts Setup — trading-ops

Three shortcuts you can build in the iOS Shortcuts app and trigger via Siri,
widgets, or share sheet. All call your Render server — no local Python needed.

---

## Prerequisites

Your Render URL and password. These go into every shortcut once as a URL and
a "Base64 Encode" action for Basic auth.

**Your base URL:** `https://your-app.onrender.com`
**Username:** `trader` (or whatever ACCESS_USER is set to)
**Password:** whatever you set for ACCESS_PASSWORD

---

## Shortcut 1 — "Scan Stock"

**Trigger:** "Hey Siri, scan [symbol]" or tap from home screen widget.

### Build it in Shortcuts:

1. Open **Shortcuts** app → tap **+** (New Shortcut)
2. **Ask for Input**
   - Prompt: `Which symbol?`
   - Input type: Text
   - Store result in: `Symbol`

3. **Text** action → type:
   ```
   trader:YOUR_PASSWORD
   ```
   Store result in: `Credentials`

4. **Base64 Encode** action
   - Input: `Credentials`
   - Store result in: `EncodedAuth`

5. **Get Contents of URL**
   - URL: `https://your-app.onrender.com/api/siri/scan/` + `Symbol`
   - Method: GET
   - Headers: Add header
     - Key: `Authorization`
     - Value: `Basic ` + `EncodedAuth`
   - Store result in: `ScanResult`

6. **Show Result** → Input: `ScanResult`

7. *(Optional)* **Speak Text** → Input: `ScanResult`
   — Siri will read the conviction out loud

8. Name it **"Scan Stock"** → add to home screen or widget

---

## Shortcut 2 — "Market Regime"

**Trigger:** "Hey Siri, what's the market regime"

Same structure as above but simpler — no input needed.

1. New Shortcut → **Text** → `trader:YOUR_PASSWORD` → store as `Credentials`
2. **Base64 Encode** → store as `EncodedAuth`
3. **Get Contents of URL**
   - URL: `https://your-app.onrender.com/api/siri/macro`
   - Method: GET
   - Header: `Authorization: Basic ` + `EncodedAuth`
   - Store as: `MacroResult`
4. **Show Result** + **Speak Text** → `MacroResult`
5. Name: **"Market Regime"**

---

## Shortcut 3 — "Watchlist Summary"

**Trigger:** "Hey Siri, show watchlist" — reads out the conviction for your 8 most recent scans.

1. New Shortcut → **Text** → `trader:YOUR_PASSWORD` → `Credentials`
2. **Base64 Encode** → `EncodedAuth`
3. **Get Contents of URL**
   - URL: `https://your-app.onrender.com/api/siri/watchlist`
   - Method: GET
   - Header: `Authorization: Basic ` + `EncodedAuth`
   - Store as: `WatchlistResult`
4. **Show Result** + **Speak Text** → `WatchlistResult`
5. Name: **"Watchlist Summary"**

---

## Shortcut 4 — "Scan from Share Sheet"

Lets you tap a ticker symbol in any app (news article, brokerage, Safari)
→ Share → "Scan in trading-ops" → get result as notification.

1. New Shortcut → in settings enable **"Show in Share Sheet"** + set input type to **Text**
2. **Get Variable** → `Shortcut Input` → store as `Symbol`
3. **Uppercase** → `Symbol` → store as `Symbol`
4. *(same auth setup as above)*
5. **Get Contents of URL** → `…/api/siri/scan/` + `Symbol`
6. **Show Notification**
   - Title: `trading-ops: ` + `Symbol`
   - Body: `ScanResult`
7. Name: **"Scan in trading-ops"**

---

## Adding to the Home Screen

After building each shortcut:
1. Open the shortcut → tap `···` (top right)
2. **Add to Home Screen**
3. Pick an icon color + name

Or use the **Shortcuts widget** (long-press home screen → Widgets → Shortcuts)
to get a 4-shortcut widget on your home screen.

---

## Tips

- The first call after Render idles takes ~30–60s. Set up UptimeRobot
  (see DEPLOY.md) to keep it warm.
- Shortcut results are cached on the server for 15 min — second call
  for the same symbol is instant.
- To scan without Siri prompting for input, duplicate Shortcut 1 and
  hardcode a symbol in a **Text** action instead of **Ask for Input**.
