/* ==========================================================================
   Settings Panel Component
   ========================================================================== */

var SettingsPanel = (function () {
  'use strict';

  var initialized = false;

  /**
   * Initialize the settings panel.
   * @param {HTMLElement} container - #settings-panel-container
   */
  function init(container) {
    container.innerHTML = '';

    var html =
      '<div class="settings-grid">' +
        // Kill Switch
        '<div class="settings-section" style="grid-column: 1 / -1; text-align: center;">' +
          '<h3>Emergency Controls</h3>' +
          '<p style="color: var(--text-muted); margin-bottom: 16px; font-size: 0.82rem;">Stop all bots immediately and cancel open orders</p>' +
          '<button id="kill-switch" class="kill-switch-btn">KILL SWITCH</button>' +
        '</div>' +

        // Bot Controls
        '<div class="settings-section">' +
          '<h3>Bot Controls</h3>' +
          '<div id="bot-toggles-list">' +
            '<p class="empty-state" style="padding: 12px 0;">Loading bots...</p>' +
          '</div>' +
        '</div>' +

        // Risk Parameters
        '<div class="settings-section">' +
          '<h3>Risk Parameters</h3>' +
          '<div id="risk-params-form">' +
            renderSettingRow('Risk Per Trade (%)', 'risk-pct', '1.0', 'Percentage of account per trade') +
            renderSettingRow('Min Confluence', 'min-confluence', '3', 'Minimum signals required') +
            renderSettingRow('Min R:R Ratio', 'min-rr', '2.0', 'Minimum reward-to-risk ratio') +
            renderSettingRow('Max Open Positions', 'max-positions', '5', 'Maximum simultaneous positions') +
            renderSettingRow('Max Daily Loss ($)', 'max-daily-loss', '500', 'Daily loss limit before auto-stop') +
          '</div>' +
          '<div style="padding: 14px 0 0; text-align: right;">' +
            '<button id="save-risk-params" class="btn btn-primary">Save Parameters</button>' +
          '</div>' +
        '</div>' +

        // Exchange Status
        '<div class="settings-section">' +
          '<h3>Exchange Connections</h3>' +
          '<div id="exchange-status-list">' +
            renderExchangeRow('Binance', false) +
            renderExchangeRow('Coinbase', false) +
            renderExchangeRow('Kraken', false) +
          '</div>' +
        '</div>' +

        // Learning Engine
        '<div class="settings-section">' +
          '<h3>Learning Engine</h3>' +
          '<div id="learning-stats">' +
            '<div class="learning-stat">' +
              '<span class="learning-stat-label">Patterns Discovered</span>' +
              '<span class="learning-stat-value" id="learning-patterns">--</span>' +
            '</div>' +
            '<div class="learning-stat">' +
              '<span class="learning-stat-label">Last Optimization</span>' +
              '<span class="learning-stat-value" id="learning-last-opt">--</span>' +
            '</div>' +
          '</div>' +
          '<div id="learning-recommendations" style="margin-top: 12px;"></div>' +
        '</div>' +
      '</div>';

    container.innerHTML = html;
    initialized = true;

    // Bind kill switch
    var killBtn = document.getElementById('kill-switch');
    killBtn.addEventListener('click', function () {
      if (!killBtn.classList.contains('engaged')) {
        if (!confirm('Are you sure you want to activate the KILL SWITCH? This will stop ALL bots immediately.')) return;
        killBtn.classList.add('engaged');
        killBtn.textContent = 'ENGAGED - ALL BOTS STOPPING';
        killAllBots();
      } else {
        killBtn.classList.remove('engaged');
        killBtn.textContent = 'KILL SWITCH';
      }
    });

    // Bind save params
    var saveBtn = document.getElementById('save-risk-params');
    saveBtn.addEventListener('click', function () {
      saveRiskParams();
    });

    // Load data
    loadBotToggles();
    loadLearningStats();
  }

  /**
   * Render a single setting row with label, input, and description.
   */
  function renderSettingRow(label, id, defaultVal, desc) {
    return '' +
      '<div class="setting-row">' +
        '<div>' +
          '<div class="setting-label">' + label + '</div>' +
          '<div class="setting-desc">' + desc + '</div>' +
        '</div>' +
        '<input type="number" step="any" id="setting-' + id + '" class="form-input setting-input" value="' + defaultVal + '">' +
      '</div>';
  }

  /**
   * Render an exchange status row.
   */
  function renderExchangeRow(name, connected) {
    var dotClass = connected ? 'connected' : 'disconnected';
    var statusText = connected ? 'Connected' : 'Disconnected';
    return '' +
      '<div class="exchange-status">' +
        '<span class="exchange-dot ' + dotClass + '"></span>' +
        '<span style="flex:1">' + name + '</span>' +
        '<span style="font-size:0.78rem; color: var(--text-muted)">' + statusText + '</span>' +
      '</div>';
  }

  /**
   * Load bot toggles from API.
   */
  function loadBotToggles() {
    var container = document.getElementById('bot-toggles-list');
    if (!container) return;

    Utils.fetchJSON('/api/bots')
      .then(function (bots) {
        if (!bots.length) {
          container.innerHTML = '<p class="empty-state" style="padding: 12px 0;">No bots configured</p>';
          return;
        }
        container.innerHTML = '';
        bots.forEach(function (bot) {
          var row = document.createElement('div');
          row.className = 'setting-row';
          var isRunning = bot.status === 'running';
          row.innerHTML =
            '<div>' +
              '<div class="setting-label">' + escapeHtml(bot.name) + '</div>' +
              '<div class="setting-desc">Status: ' + (bot.status || 'unknown') + '</div>' +
            '</div>' +
            '<button class="btn-toggle' + (isRunning ? ' active' : '') + '" data-bot="' + escapeHtml(bot.name) + '"></button>';
          container.appendChild(row);

          var toggle = row.querySelector('.btn-toggle');
          toggle.addEventListener('click', function () {
            Utils.postJSON('/api/bots/' + encodeURIComponent(bot.name) + '/toggle')
              .then(function (updated) {
                var nowRunning = updated.status === 'running';
                toggle.classList.toggle('active', nowRunning);
                row.querySelector('.setting-desc').textContent = 'Status: ' + updated.status;
              })
              .catch(function (err) {
                console.error('Toggle failed:', err);
              });
          });
        });
      })
      .catch(function (err) {
        container.innerHTML = '<p class="empty-state" style="padding: 12px 0;">Failed to load bots</p>';
      });
  }

  /**
   * Load learning engine stats.
   */
  function loadLearningStats() {
    Utils.fetchJSON('/api/learning')
      .then(function (stats) {
        var patternsEl = document.getElementById('learning-patterns');
        var lastOptEl = document.getElementById('learning-last-opt');
        var recsContainer = document.getElementById('learning-recommendations');

        if (patternsEl) patternsEl.textContent = stats.patternsCount || 0;
        if (lastOptEl) lastOptEl.textContent = stats.lastOptimization ? Utils.formatDateTime(stats.lastOptimization) : 'Never';

        if (recsContainer && stats.recommendations && stats.recommendations.length) {
          recsContainer.innerHTML = '<div style="font-size:0.78rem; color:var(--text-muted); margin-bottom:8px;">Recent Recommendations</div>';
          stats.recommendations.forEach(function (rec) {
            var div = document.createElement('div');
            div.className = 'recommendation-item';
            div.textContent = rec.message || rec.recommendation || JSON.stringify(rec);
            recsContainer.appendChild(div);
          });
        }
      })
      .catch(function () {
        // Learning tables may not exist
      });
  }

  /**
   * Kill all bots.
   */
  function killAllBots() {
    Utils.fetchJSON('/api/bots')
      .then(function (bots) {
        var promises = bots
          .filter(function (b) { return b.status === 'running'; })
          .map(function (b) {
            return Utils.postJSON('/api/bots/' + encodeURIComponent(b.name) + '/toggle');
          });
        return Promise.all(promises);
      })
      .then(function () {
        loadBotToggles();
      })
      .catch(function (err) {
        console.error('Kill switch error:', err);
      });
  }

  /**
   * Save risk parameters (POST to first bot's settings for now).
   */
  function saveRiskParams() {
    var params = {
      risk_pct: parseFloat(document.getElementById('setting-risk-pct').value) || 1.0,
      min_confluence: parseInt(document.getElementById('setting-min-confluence').value, 10) || 3,
      min_rr: parseFloat(document.getElementById('setting-min-rr').value) || 2.0,
      max_positions: parseInt(document.getElementById('setting-max-positions').value, 10) || 5,
      max_daily_loss: parseFloat(document.getElementById('setting-max-daily-loss').value) || 500
    };

    // Save to all bots
    Utils.fetchJSON('/api/bots')
      .then(function (bots) {
        var promises = bots.map(function (b) {
          return Utils.postJSON('/api/bots/' + encodeURIComponent(b.name) + '/settings', params);
        });
        return Promise.all(promises);
      })
      .then(function () {
        var btn = document.getElementById('save-risk-params');
        btn.textContent = 'Saved!';
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-success');
        setTimeout(function () {
          btn.textContent = 'Save Parameters';
          btn.classList.remove('btn-success');
          btn.classList.add('btn-primary');
        }, 2000);
      })
      .catch(function (err) {
        console.error('Save failed:', err);
        alert('Failed to save parameters: ' + err.message);
      });
  }

  /**
   * Refresh the settings panel data.
   */
  function refresh(container) {
    if (!initialized) return;
    loadBotToggles();
    loadLearningStats();
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  return {
    init: init,
    refresh: refresh
  };
})();
