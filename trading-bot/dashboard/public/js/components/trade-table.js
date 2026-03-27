/* ==========================================================================
   Trade Table Component
   ========================================================================== */

var TradeTable = (function () {
  'use strict';

  var PAGE_SIZE = 20;

  /**
   * Create the trade table UI (filters + table + pagination).
   * @param {HTMLElement} container - Parent container
   * @param {Array} trades - Initial trade data
   * @param {Array} bots - List of bot names for filter
   */
  function createTradeTable(container, trades, bots) {
    container.innerHTML = '';

    var state = {
      trades: trades || [],
      filtered: trades || [],
      page: 0,
      botFilter: '',
      symbolFilter: '',
      resultFilter: '' // 'win' | 'loss' | ''
    };

    // Card wrapper
    var card = Utils.createElement('div', 'card');

    // Filter bar
    var filterBar = Utils.createElement('div', 'filter-bar');
    filterBar.innerHTML =
      '<label>Bot</label>' +
      '<select class="form-select filter-bot">' +
        '<option value="">All Bots</option>' +
        buildBotOptions(bots) +
      '</select>' +
      '<label>Symbol</label>' +
      '<input type="text" class="form-input filter-symbol" placeholder="e.g. BTC/USDT" style="width:130px">' +
      '<label>Result</label>' +
      '<select class="form-select filter-result">' +
        '<option value="">All</option>' +
        '<option value="win">Wins</option>' +
        '<option value="loss">Losses</option>' +
      '</select>';
    card.appendChild(filterBar);

    // Table
    var tableWrapper = Utils.createElement('div', 'data-table-wrapper');
    var table = Utils.createElement('table', 'data-table');
    table.innerHTML =
      '<thead><tr>' +
        '<th>Time</th>' +
        '<th>Bot</th>' +
        '<th>Symbol</th>' +
        '<th>Side</th>' +
        '<th>Entry</th>' +
        '<th>Exit</th>' +
        '<th>P&L</th>' +
        '<th>R Multiple</th>' +
        '<th>Setup</th>' +
      '</tr></thead>' +
      '<tbody></tbody>';
    tableWrapper.appendChild(table);
    card.appendChild(tableWrapper);

    // Pagination
    var pagination = Utils.createElement('div', 'pagination');
    pagination.innerHTML =
      '<button class="pagination-btn page-prev" disabled>&laquo; Prev</button>' +
      '<span class="pagination-info page-info">0 trades</span>' +
      '<button class="pagination-btn page-next" disabled>Next &raquo;</button>';
    card.appendChild(pagination);

    container.appendChild(card);

    // Bind filter events
    var botSelect = filterBar.querySelector('.filter-bot');
    var symbolInput = filterBar.querySelector('.filter-symbol');
    var resultSelect = filterBar.querySelector('.filter-result');
    var prevBtn = pagination.querySelector('.page-prev');
    var nextBtn = pagination.querySelector('.page-next');
    var pageInfo = pagination.querySelector('.page-info');
    var tbody = table.querySelector('tbody');

    function applyFilters() {
      state.botFilter = botSelect.value;
      state.symbolFilter = symbolInput.value.trim().toUpperCase();
      state.resultFilter = resultSelect.value;
      state.page = 0;

      state.filtered = state.trades.filter(function (t) {
        if (state.botFilter && t.bot !== state.botFilter) return false;
        if (state.symbolFilter && (t.symbol || '').toUpperCase().indexOf(state.symbolFilter) === -1) return false;
        if (state.resultFilter === 'win' && parseFloat(t.pnl) <= 0) return false;
        if (state.resultFilter === 'loss' && parseFloat(t.pnl) > 0) return false;
        return true;
      });

      renderPage();
    }

    function renderPage() {
      var start = state.page * PAGE_SIZE;
      var end = start + PAGE_SIZE;
      var pageData = state.filtered.slice(start, end);
      var totalPages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));

      tbody.innerHTML = '';

      if (pageData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No trades found</td></tr>';
      } else {
        pageData.forEach(function (trade) {
          tbody.innerHTML += renderTradeRow(trade);
        });
      }

      pageInfo.textContent = state.filtered.length + ' trades | Page ' + (state.page + 1) + ' / ' + totalPages;
      prevBtn.disabled = state.page === 0;
      nextBtn.disabled = end >= state.filtered.length;
    }

    botSelect.addEventListener('change', applyFilters);
    symbolInput.addEventListener('input', debounce(applyFilters, 300));
    resultSelect.addEventListener('change', applyFilters);
    prevBtn.addEventListener('click', function () { state.page--; renderPage(); });
    nextBtn.addEventListener('click', function () { state.page++; renderPage(); });

    // Store references for external updates
    container._tradeState = state;
    container._applyFilters = applyFilters;
    container._renderPage = renderPage;
    container._tbody = tbody;
    container._botSelect = botSelect;

    renderPage();
  }

  /**
   * Update the trade table with a fresh list of trades.
   */
  function updateTradeTable(container, trades) {
    var state = container._tradeState;
    if (!state) return;
    state.trades = trades || [];
    container._applyFilters();
  }

  /**
   * Append a single new trade to the top.
   */
  function appendTrade(container, trade) {
    var state = container._tradeState;
    if (!state) return;
    state.trades.unshift(trade);
    container._applyFilters();
  }

  /**
   * Update the bot filter dropdown with available bots.
   */
  function updateBotFilter(container, bots) {
    var sel = container._botSelect;
    if (!sel) return;
    var current = sel.value;
    sel.innerHTML = '<option value="">All Bots</option>' + buildBotOptions(bots);
    sel.value = current;
  }

  // Helpers

  function renderTradeRow(t) {
    var pnl = parseFloat(t.pnl || 0);
    var pnlClass = pnl >= 0 ? 'cell-positive' : 'cell-negative';
    var side = (t.side || '').toUpperCase();
    var sideClass = side === 'BUY' || side === 'LONG' ? 'cell-positive' : 'cell-negative';

    return '<tr>' +
      '<td>' + Utils.formatDateTime(t.close_time || t.open_time) + '</td>' +
      '<td>' + escapeHtml(t.bot || '') + '</td>' +
      '<td class="cell-mono">' + escapeHtml(t.symbol || '') + '</td>' +
      '<td class="' + sideClass + '">' + side + '</td>' +
      '<td class="cell-mono">' + formatPrice(t.entry_price) + '</td>' +
      '<td class="cell-mono">' + formatPrice(t.exit_price) + '</td>' +
      '<td class="cell-mono ' + pnlClass + '">' + Utils.formatCurrencyPlain(pnl) + '</td>' +
      '<td class="cell-mono">' + formatR(t.r_multiple) + '</td>' +
      '<td>' + escapeHtml(t.setup || '--') + '</td>' +
    '</tr>';
  }

  function formatPrice(val) {
    if (val === null || val === undefined) return '--';
    var n = parseFloat(val);
    if (isNaN(n)) return '--';
    return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
  }

  function formatR(val) {
    if (val === null || val === undefined) return '--';
    var n = parseFloat(val);
    if (isNaN(n)) return '--';
    return (n >= 0 ? '+' : '') + n.toFixed(2) + 'R';
  }

  function buildBotOptions(bots) {
    if (!bots || !bots.length) return '';
    return bots.map(function (b) {
      var name = typeof b === 'string' ? b : b.name;
      return '<option value="' + escapeHtml(name) + '">' + escapeHtml(name) + '</option>';
    }).join('');
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  function debounce(fn, ms) {
    var timer;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, ms);
    };
  }

  return {
    createTradeTable: createTradeTable,
    updateTradeTable: updateTradeTable,
    appendTrade: appendTrade,
    updateBotFilter: updateBotFilter
  };
})();
