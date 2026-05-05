# Mobile Deployment Guide

You want to use trading-ops on your phone from work (i.e., not on your home WiFi).
Three options, ranked by how much setup they need.

---

## Option 1 — Render (cloud, easiest, free)

Always-on URL like `https://trading-ops-xyz.onrender.com`. Works from any
network. Free tier sleeps after 15 min idle (first request after sleep takes
~30–60s to wake).

### Steps

1. Push this repo to GitHub (a private repo is fine).
2. Sign up at https://render.com (free, GitHub login).
3. Click **New → Blueprint**, point at your repo. Render reads `render.yaml`
   and provisions everything.
4. Set the secret env vars in the Render dashboard:
   - `FRED_API_KEY` = your free key from https://fred.stlouisfed.org/docs/api/api_key.html
   - `ACCESS_PASSWORD` = a strong password (HTTP Basic auth gate)
   - `ACCESS_USER` = pre-set to `trader` (change if you want)
5. Wait ~5 min for the first build.
6. Open the URL on your phone. Browser will prompt for username/password.
7. Tap **Share → Add to Home Screen** in Safari (iOS) or **Install app** in
   Chrome (Android). It installs as a PWA — full-screen, dark theme, looks
   native.

### Notes

- Render free tier = 750 hrs/month (enough for one always-on service)
- All scripts use public APIs (yfinance, CoinGecko, Binance, SEC EDGAR, CFTC,
  FRED, Google News RSS) — they work fine from a cloud IP.
- Scan results are saved to the container's `/app/scanned/` — they survive
  restarts on paid tiers but **not on Render free tier** (free tier disks are
  ephemeral). Add a Render Disk ($1/mo for 1GB) if you want persistent history.

---

## Option 2 — Fly.io (cloud, also free, persistent)

Better than Render free tier because the disk persists. Slightly more setup.

### Steps

```bash
# install flyctl
curl -L https://fly.io/install.sh | sh

# from repo root
fly auth signup            # or `fly auth login`
fly launch --copy-config --no-deploy   # uses fly.toml in this repo
fly volumes create scanned --size 1 --region iad   # 1GB persistent disk
fly secrets set FRED_API_KEY=your_key ACCESS_PASSWORD=your_password
fly deploy
```

Then open the URL Fly prints (e.g. `https://trading-ops.fly.dev`). Add to home
screen on your phone same as above.

To make `scanned/` persist, add this to `fly.toml`:

```toml
[mounts]
  source = "scanned"
  destination = "/app/scanned"
```

---

## Option 3 — Cloudflare Tunnel (your PC stays the backend, free)

Use this if you want the scripts to run on your PC (which you already trust),
not in the cloud. Cloudflare gives you a free public URL that tunnels to your
PC. No port forwarding, no router config, works behind any firewall.

### Steps

1. Install cloudflared:
   - Windows: `winget install --id Cloudflare.cloudflared`
   - macOS: `brew install cloudflared`
   - Linux: see https://pkg.cloudflare.com
2. Set `ACCESS_PASSWORD` in your `.env` (REQUIRED — this is now public
   internet-facing):
   ```
   FRED_API_KEY=your_key
   ACCESS_PASSWORD=a_strong_password
   ACCESS_USER=trader
   ```
3. Start the local server:
   ```
   ./web-start.sh        # or web-start.bat on Windows
   ```
4. In a separate terminal, start the tunnel:
   ```
   cloudflared tunnel --url http://localhost:8000
   ```
5. Cloudflared prints a URL like `https://abcd-1234-xyz.trycloudflare.com`.
   Open it on your phone. Browser prompts for the password you set.

### Caveats

- The free `trycloudflare.com` URL **changes every restart**. For a stable
  custom subdomain, run `cloudflared tunnel login` and follow Cloudflare's
  named-tunnel guide (also free, requires a domain on Cloudflare DNS).
- Your PC must be on for the URL to work.

---

## Option 4 — Tailscale (private VPN, no public URL)

Only you can reach the server. Most secure. Requires installing Tailscale on
both your phone and your PC.

```
# install Tailscale on PC and phone (free for personal: 100 devices)
# https://tailscale.com/download

# both devices: log in with the same account
# PC: start the server with web-start.sh
# Phone: open http://<your-pc-tailscale-ip>:8000
#        e.g. http://100.64.10.5:8000
# Tailscale Magic DNS: http://your-pc-name:8000
```

No public exposure, no Cloudflare, no auth needed (Tailscale handles it).

---

## Local-only (same WiFi at home)

If you just want to use it on your phone at home, you don't need any of the
above. Run `./web-start.sh` (or `web-start.bat`). The script prints your LAN
IP. Open `http://<your-pc-ip>:8000` on your phone connected to the same WiFi.

---

## Recommended path for "use it at work"

**Render (Option 1).** Push to GitHub → blueprint deploy → set 2 env vars →
done. ~5 min. You get a permanent HTTPS URL, password-protected, no PC
required, no port forwarding, works from any network. The 30s cold-start
after idle is the only annoyance and you can pay $7/mo to remove it.
