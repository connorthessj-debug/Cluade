/* ==========================================================================
   Bot Card Component
   ========================================================================== */

var BotCard = (function () {
  'use strict';

  /**
   * Create a bot status card DOM element.
   * @param {object} bot - Bot data from API
   * @returns {HTMLElement}
   */
  function createBotCard(bot) {
    var card = Utils.createElement('div', 'bot-card');
    card.setAttribute('data-bot-name', bot.name || '');
    card.innerHTML = renderInner(bot);
    bindEvents(card, bot);
    return card;
  }

  /**
   * Render the inner HTML for a bot card.
   */
  function renderInner(bot) {
    var name = bot.name || 'Unknown Bot';
    var status = bot.status || 'stopped';
    var pnl = parseFloat(bot.total_pnl || bot.pnl || 0);
    var openPositions = parseInt(bot.open_positions || 0, 10);
    var lastTrade = bot.last_trade_time || bot.updated_at || null;
    var signals = parseInt(bot.active_signals || 0, 10);
    var settings = {};
    try { settings = typeof bot.settings === 'string' ? JSON.parse(bot.settings) : (bot.settings || {}); } catch (_) {}

    var isRunning = status === 'running';
    var btnLabel = isRunning ? 'Stop' : 'Start';
    var btnClass = isRunning ? 'btn btn-sm btn-danger' : 'btn btn-sm btn-success';

    return '' +
      '<div class="bot-card-header">' +
        '<span class="bot-card-name">' + escapeHtml(name) + '</span>' +
        Utils.statusBadge(status) +
      '</div>' +
      '<div class="bot-card-stats">' +
        '<div class="bot-stat">' +
          '<span class="bot-stat-label">P&L</span>' +
          '<span class="bot-stat-value ' + (pnl >= 0 ? 'cell-positive' : 'cell-negative') + '">' +
            Utils.formatCurrencyPlain(pnl) +
          '</span>' +
        '</div>' +
        '<div class="bot-stat">' +
          '<span class="bot-stat-label">Open Positions</span>' +
          '<span class="bot-stat-value">' + openPositions + '</span>' +
        '</div>' +
        '<div class="bot-stat">' +
          '<span class="bot-stat-label">Active Signals</span>' +
          '<span class="bot-stat-value">' + signals + '</span>' +
        '</div>' +
        '<div class="bot-stat">' +
          '<span class="bot-stat-label">Last Trade</span>' +
          '<span class="bot-stat-value">' + Utils.formatTime(lastTrade) + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="bot-card-footer">' +
        '<span class="bot-card-time">Updated ' + Utils.formatTime(bot.updated_at) + '</span>' +
        '<button class="' + btnClass + ' bot-toggle-btn" data-bot="' + escapeHtml(name) + '">' + btnLabel + '</button>' +
      '</div>';
  }

  /**
   * Update an existing card element with new bot data.
   */
  function updateBotCard(cardEl, bot) {
    cardEl.innerHTML = renderInner(bot);
    bindEvents(cardEl, bot);
    Utils.flashElement(cardEl);
  }

  /**
   * Bind button events to a card.
   */
  function bindEvents(cardEl, bot) {
    var btn = cardEl.querySelector('.bot-toggle-btn');
    if (btn) {
      btn.addEventListener('click', function () {
        btn.disabled = true;
        btn.textContent = '...';
        Utils.postJSON('/api/bots/' + encodeURIComponent(bot.name) + '/toggle')
          .then(function (updated) {
            updateBotCard(cardEl, updated);
          })
          .catch(function (err) {
            console.error('Toggle failed:', err);
            btn.disabled = false;
            btn.textContent = bot.status === 'running' ? 'Stop' : 'Start';
          });
      });
    }
  }

  /**
   * Render all bot cards into a container.
   */
  function renderBotCards(container, bots) {
    container.innerHTML = '';
    if (!bots || bots.length === 0) {
      container.innerHTML = '<p class="empty-state">No bots configured</p>';
      return;
    }
    bots.forEach(function (bot) {
      container.appendChild(createBotCard(bot));
    });
  }

  /**
   * Find and update a single bot card or append if new.
   */
  function upsertBotCard(container, bot) {
    var existing = container.querySelector('[data-bot-name="' + bot.name + '"]');
    if (existing) {
      updateBotCard(existing, bot);
    } else {
      // Remove empty state if present
      var empty = container.querySelector('.empty-state');
      if (empty) empty.remove();
      container.appendChild(createBotCard(bot));
    }
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  return {
    createBotCard: createBotCard,
    updateBotCard: updateBotCard,
    renderBotCards: renderBotCards,
    upsertBotCard: upsertBotCard
  };
})();
