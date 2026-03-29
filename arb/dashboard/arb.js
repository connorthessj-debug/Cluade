// RENDER Trading Bot Dashboard
const API_BASE = window.location.origin;
let pollInterval = null;

// --- API Calls ---

async function api(method, path, body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    try {
        const resp = await fetch(API_BASE + path, opts);
        return await resp.json();
    } catch (e) {
        console.error(`API error: ${path}`, e);
        return null;
    }
}

async function startBot() {
    const data = await api('POST', '/api/start');
    if (data) updateButtons(true);
}

async function stopBot() {
    const data = await api('POST', '/api/stop');
    if (data) updateButtons(false);
}

async function emergencySell() {
    if (confirm('EMERGENCY SELL all RENDER at market price?')) {
        await api('POST', '/api/emergency_sell');
    }
}

async function saveConfig() {
    const config = {
        dip_entry_pct: parseFloat(document.getElementById('cfg-dip').value),
        take_profit_pct: parseFloat(document.getElementById('cfg-tp').value),
        stop_loss_pct: parseFloat(document.getElementById('cfg-sl').value),
        lookback_hours: parseInt(document.getElementById('cfg-lookback').value),
        poll_seconds: parseFloat(document.getElementById('cfg-poll').value),
        max_trades_per_day: parseInt(document.getElementById('cfg-maxdaily').value),
    };
    await api('POST', '/api/config', config);
    alert('Settings saved!');
}

function toggleConfig() {
    const fields = document.getElementById('config-fields');
    const arrow = document.getElementById('config-arrow');
    if (fields.style.display === 'none') {
        fields.style.display = 'block';
        arrow.innerHTML = '&#9652;';
    } else {
        fields.style.display = 'none';
        arrow.innerHTML = '&#9662;';
    }
}

// --- UI Updates ---

function updateButtons(running) {
    document.getElementById('btn-start').disabled = running;
    document.getElementById('btn-stop').disabled = !running;
}

function formatPrice(p) {
    if (!p || p === 0) return '--';
    return '$' + p.toFixed(3);
}

function formatPnl(pnl) {
    const sign = pnl >= 0 ? '+' : '';
    return sign + '$' + pnl.toFixed(2);
}

function formatTime(isoStr) {
    if (!isoStr) return '--';
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function updateDashboard(data) {
    if (!data) return;

    // Status badge
    const badge = document.getElementById('status-badge');
    if (data.running) {
        badge.textContent = data.position ? 'IN TRADE' : 'WATCHING';
        badge.className = 'badge running';
    } else {
        badge.textContent = 'STOPPED';
        badge.className = 'badge';
    }
    updateButtons(data.running);

    // Price
    document.getElementById('current-price').textContent = formatPrice(data.price);
    document.getElementById('bid').textContent = formatPrice(data.bid);
    document.getElementById('ask').textContent = formatPrice(data.ask);
    document.getElementById('recent-high').textContent = formatPrice(data.recent_high);

    // Dip indicator
    const dipEl = document.getElementById('dip-indicator');
    if (data.dip_from_high_pct > 0) {
        dipEl.innerHTML = `<span class="${data.dip_from_high_pct >= data.config.dip_entry_pct ? 'dip' : 'waiting'}">-${data.dip_from_high_pct.toFixed(1)}% from high</span>`;
    } else {
        dipEl.textContent = 'At/near high';
    }

    // Total P&L
    const pnlEl = document.getElementById('total-pnl');
    pnlEl.textContent = formatPnl(data.total_pnl);
    pnlEl.className = 'pnl ' + (data.total_pnl >= 0 ? 'positive' : 'negative');

    // Balances
    document.getElementById('usd-bal').textContent = '$' + data.usd_balance.toFixed(2);
    document.getElementById('render-bal').textContent = data.render_balance.toFixed(2);

    // Position
    const posPanel = document.getElementById('position-panel');
    if (data.position) {
        posPanel.style.display = 'block';
        document.getElementById('pos-entry').textContent = formatPrice(data.position.buy_price);
        document.getElementById('pos-size').textContent = data.position.buy_size.toFixed(2) + ' RENDER';
        document.getElementById('pos-tp').textContent = formatPrice(data.position.take_profit);
        document.getElementById('pos-sl').textContent = formatPrice(data.position.stop_loss);

        const posPnl = document.getElementById('pos-pnl');
        const upnl = data.position.unrealized_pnl;
        const upct = data.position.unrealized_pct;
        posPnl.textContent = `${formatPnl(upnl)} (${upct >= 0 ? '+' : ''}${upct.toFixed(1)}%)`;
        posPnl.className = 'position-pnl ' + (upnl >= 0 ? 'green' : 'red');
    } else {
        posPanel.style.display = 'none';
    }

    // Status message
    document.getElementById('status-msg').textContent = data.status_message || '--';

    // Stats
    document.getElementById('daily-trades').textContent = data.daily_trades;
    document.getElementById('total-trades').textContent = data.total_trades;
    const statPnl = document.getElementById('stat-pnl');
    statPnl.textContent = formatPnl(data.total_pnl);
    statPnl.className = data.total_pnl >= 0 ? 'green' : 'red';

    // Config fields (don't overwrite if user is editing)
    if (!document.activeElement || document.activeElement.tagName !== 'INPUT') {
        document.getElementById('cfg-dip').value = data.config.dip_entry_pct;
        document.getElementById('cfg-tp').value = data.config.take_profit_pct;
        document.getElementById('cfg-sl').value = data.config.stop_loss_pct;
        document.getElementById('cfg-lookback').value = data.config.lookback_hours;
        document.getElementById('cfg-poll').value = data.config.poll_seconds;
        document.getElementById('cfg-maxdaily').value = data.config.max_trades_per_day;
    }

    // Trade log
    const tradeList = document.getElementById('trade-list');
    const trades = data.recent_trades || [];
    if (trades.length === 0) {
        tradeList.innerHTML = '<div class="trade-empty">No trades yet</div>';
    } else {
        tradeList.innerHTML = trades.reverse().map(t => {
            const pnlHtml = t.pnl !== 0
                ? `<span class="trade-pnl ${t.pnl >= 0 ? 'green' : 'red'}">${formatPnl(t.pnl)}</span>`
                : '';
            return `
                <div class="trade-item">
                    <div>
                        <span class="trade-action ${t.action}">${t.action}</span>
                        <span class="trade-price">${formatPrice(t.price)}</span>
                        ${pnlHtml}
                    </div>
                    <div>
                        <span class="trade-time">${formatTime(t.timestamp)}</span>
                    </div>
                </div>
            `;
        }).join('');
    }
}

// --- Polling ---

async function poll() {
    const data = await api('GET', '/api/status');
    updateDashboard(data);
}

// Start polling on load
document.addEventListener('DOMContentLoaded', () => {
    poll();
    pollInterval = setInterval(poll, 2000); // Poll every 2 seconds
});
