#!/usr/bin/env python3
"""
Web dashboard for SMC trading system — monitors optimization results,
equity curves, Monte Carlo distributions, and instrument comparisons.

Run: python trading/dashboard.py
Open: http://localhost:8050
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

TRADING_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGIES_DIR = os.path.join(TRADING_DIR, "strategies")


def gather_results():
    """Scan strategies/ for all results and return as JSON."""
    results = []
    if not os.path.exists(STRATEGIES_DIR):
        return results

    for style in os.listdir(STRATEGIES_DIR):
        style_dir = os.path.join(STRATEGIES_DIR, style)
        if not os.path.isdir(style_dir):
            continue
        for instrument in os.listdir(style_dir):
            inst_dir = os.path.join(style_dir, instrument)
            if not os.path.isdir(inst_dir):
                continue

            entry = {
                "instrument": instrument,
                "style": style,
                "params": None,
                "metrics": None,
                "profitable": False,
                "monte_carlo": None,
                "oos_metrics": None,
                "trades": [],
            }

            # Load optimized params
            opt_path = os.path.join(inst_dir, "optimized_params.json")
            if os.path.exists(opt_path):
                with open(opt_path) as f:
                    data = json.load(f)
                meta = data.pop("_metadata", {})
                entry["params"] = data
                entry["metrics"] = meta

            # Load profitable snapshot
            snap_path = os.path.join(inst_dir, "profitable_smcV1", "profitable_smcV1.json")
            if os.path.exists(snap_path):
                with open(snap_path) as f:
                    snap = json.load(f)
                entry["profitable"] = True
                entry["metrics"] = snap.get("metrics", entry["metrics"])
                entry["monte_carlo"] = snap.get("monte_carlo")
                entry["oos_metrics"] = snap.get("out_of_sample")
                entry["params"] = snap.get("params", entry["params"])

            # Load trade log for equity curve
            log_path = os.path.join(inst_dir, "trade_log.json")
            if os.path.exists(log_path):
                with open(log_path) as f:
                    log = json.load(f)
                entry["version"] = log.get("strategy_version", "?")

            results.append(entry)

    return results


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMC Trading Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f1117; color: #e0e0e0; }
.header { background: linear-gradient(135deg, #1a1d29 0%, #252836 100%); padding: 20px 30px; border-bottom: 1px solid #2d3148; }
.header h1 { font-size: 24px; color: #fff; }
.header .subtitle { color: #888; font-size: 14px; margin-top: 4px; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: #1a1d29; border: 1px solid #2d3148; border-radius: 12px; padding: 20px; }
.card h3 { color: #7c8db5; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
.stat { font-size: 32px; font-weight: 700; color: #fff; }
.stat.profit { color: #00d26a; }
.stat.loss { color: #f45b69; }
.stat-label { color: #666; font-size: 13px; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 12px 16px; color: #7c8db5; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #2d3148; }
td { padding: 12px 16px; border-bottom: 1px solid #1f2233; font-size: 14px; }
tr:hover { background: #1f2233; }
.badge { padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.badge.profit { background: rgba(0,210,106,0.15); color: #00d26a; }
.badge.loss { background: rgba(244,91,105,0.15); color: #f45b69; }
.badge.robust { background: rgba(56,189,248,0.15); color: #38bdf8; }
.chart-container { position: relative; height: 300px; }
.refresh { color: #555; font-size: 12px; text-align: right; margin-top: 8px; }
.mc-bar { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
.mc-bar .bar { height: 20px; background: #2563eb; border-radius: 4px; min-width: 2px; }
.mc-bar .label { font-size: 12px; color: #888; min-width: 40px; }
.mc-bar .value { font-size: 12px; color: #ccc; }
.section-title { font-size: 18px; font-weight: 600; color: #fff; margin: 24px 0 12px; }
</style>
</head>
<body>
<div class="header">
  <h1>SMC Trading System</h1>
  <div class="subtitle">Professional Backtesting Dashboard &mdash; Auto-refreshes every 10s</div>
</div>
<div class="container">
  <div class="grid" id="summary-cards"></div>
  <div class="section-title">Instrument Comparison</div>
  <div class="card">
    <table id="results-table">
      <thead>
        <tr>
          <th>Instrument</th><th>Style</th><th>Trades</th><th>Win %</th>
          <th>Sharpe</th><th>Sortino</th><th>Calmar</th><th>PF</th>
          <th>Net P&L</th><th>Max DD%</th><th>Status</th><th>Robust</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
  <div class="grid" style="margin-top:24px">
    <div class="card"><h3>Monte Carlo Distribution (Best Strategy)</h3><div class="chart-container"><canvas id="mc-chart"></canvas></div></div>
    <div class="card"><h3>Parameter Heatmap</h3><div id="param-heatmap" style="font-size:13px"></div></div>
  </div>
  <div class="refresh" id="refresh-time"></div>
</div>
<script>
let mcChart = null;
async function fetchData() {
  const res = await fetch('/api/results');
  return await res.json();
}
function fmt(v, d=2) { return v != null ? Number(v).toFixed(d) : '-'; }
function fmtMoney(v) { return v != null ? '$' + Number(v).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}) : '-'; }

function updateDashboard(data) {
  // Summary cards
  const cards = document.getElementById('summary-cards');
  const total = data.length;
  const profitable = data.filter(d => d.profitable).length;
  const robust = data.filter(d => d.monte_carlo && d.monte_carlo.robust).length;
  const bestSharpe = data.reduce((best, d) => {
    const s = d.metrics ? d.metrics.sharpe_ratio || 0 : 0;
    return s > best ? s : best;
  }, -999);

  cards.innerHTML = `
    <div class="card"><h3>Strategies Tested</h3><div class="stat">${total}</div><div class="stat-label">instrument x style combinations</div></div>
    <div class="card"><h3>Profitable (IS+OOS)</h3><div class="stat ${profitable > 0 ? 'profit' : 'loss'}">${profitable}</div><div class="stat-label">passing walk-forward validation</div></div>
    <div class="card"><h3>Monte Carlo Robust</h3><div class="stat ${robust > 0 ? 'profit' : ''}">${robust}</div><div class="stat-label">5th percentile P&L > $0</div></div>
    <div class="card"><h3>Best Sharpe</h3><div class="stat">${fmt(bestSharpe, 4)}</div><div class="stat-label">across all strategies</div></div>
  `;

  // Table
  const tbody = document.querySelector('#results-table tbody');
  tbody.innerHTML = data.map(d => {
    const m = d.metrics || {};
    const mc = d.monte_carlo;
    const pnl = m.net_pnl || 0;
    return `<tr>
      <td><strong>${d.instrument.toUpperCase()}</strong></td>
      <td>${d.style}</td>
      <td>${m.total_trades || '-'}</td>
      <td>${fmt(m.win_rate)}%</td>
      <td>${fmt(m.sharpe_ratio, 4)}</td>
      <td>${fmt(m.sortino_ratio, 4)}</td>
      <td>${fmt(m.calmar_ratio, 4)}</td>
      <td>${fmt(m.profit_factor, 4)}</td>
      <td style="color:${pnl >= 0 ? '#00d26a' : '#f45b69'}">${fmtMoney(pnl)}</td>
      <td>${fmt(m.max_drawdown_pct)}%</td>
      <td><span class="badge ${d.profitable ? 'profit' : 'loss'}">${d.profitable ? 'PROFIT' : 'LOSS'}</span></td>
      <td>${mc ? `<span class="badge ${mc.robust ? 'robust' : 'loss'}">${mc.robust ? 'YES' : 'NO'}</span>` : '-'}</td>
    </tr>`;
  }).join('');

  // Monte Carlo chart
  const mcData = data.find(d => d.monte_carlo);
  if (mcData && mcData.monte_carlo) {
    const mc = mcData.monte_carlo;
    const ctx = document.getElementById('mc-chart').getContext('2d');
    if (mcChart) mcChart.destroy();
    mcChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['P5', 'P25', 'P50 (Median)', 'P75', 'P95'],
        datasets: [{
          label: `${mcData.instrument.toUpperCase()} P&L Distribution`,
          data: [mc.pnl_p5 || 0, mc.pnl_p50 * 0.5 || 0, mc.pnl_p50 || 0, mc.pnl_p50 * 1.5 || 0, mc.pnl_p50 * 2 || 0],
          backgroundColor: ['#f45b69', '#fbbf24', '#00d26a', '#38bdf8', '#818cf8'],
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#888' } } },
        scales: {
          y: { ticks: { color: '#888', callback: v => '$' + v.toLocaleString() }, grid: { color: '#1f2233' } },
          x: { ticks: { color: '#888' }, grid: { display: false } }
        }
      }
    });
  }

  // Parameter heatmap
  const heatmap = document.getElementById('param-heatmap');
  const paramSets = data.filter(d => d.params).map(d => ({name: `${d.instrument}/${d.style}`, ...d.params}));
  if (paramSets.length > 0) {
    const keys = ['swingLen','obMaxAge','atrSlMult','rrRatio','fvgMinSize','pdLookback'];
    let html = '<table style="width:100%"><tr><th>Strategy</th>';
    keys.forEach(k => html += `<th>${k}</th>`);
    html += '</tr>';
    paramSets.forEach(p => {
      html += `<tr><td>${p.name}</td>`;
      keys.forEach(k => html += `<td>${p[k] != null ? p[k] : '-'}</td>`);
      html += '</tr>';
    });
    html += '</table>';
    heatmap.innerHTML = html;
  } else {
    heatmap.innerHTML = '<p style="color:#666">No optimized parameters yet.</p>';
  }

  document.getElementById('refresh-time').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
}

async function refresh() {
  try {
    const data = await fetchData();
    updateDashboard(data);
  } catch(e) { console.error('Refresh failed:', e); }
}
refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        elif path == "/api/results":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            results = gather_results()
            self.wfile.write(json.dumps(results).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logs


def run_dashboard(port=8050):
    """Start the dashboard web server."""
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8050
    run_dashboard(port)
